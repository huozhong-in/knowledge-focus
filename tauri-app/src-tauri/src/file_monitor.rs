//! # 文件管理协调器 (File Management Coordinator)
//!
//! 该模块负责文件监控的管理和协调工作，包括：
//! - 配置管理（获取、缓存、刷新API配置）
//! - 监控基础设施和生命周期管理
//! - API通信接口和数据同步
//! - 批处理和队列管理
//! - 监控状态和统计信息维护
//!
//! 注意：尽管模块名为"monitor"，但它实际上是整个文件处理系统的协调中心，
//! 负责调用file_scanner模块来执行具体的文件操作，同时管理整个系统的配置和状态。

use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue; // For extra_data in FileFilterRuleRust
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::Emitter;
use tokio::fs;
use tokio::sync::mpsc::{self, Receiver, Sender};
use tokio::time::sleep;
use walkdir::WalkDir;

// --- Blacklist Trie for Hierarchical Blacklisting ---
#[derive(Debug, Default, Clone)]
struct BlacklistTrieNode {
    children: std::collections::HashMap<String, BlacklistTrieNode>,
    is_blacklisted_here: bool, // True if the path ending at this node is explicitly blacklisted
}

impl BlacklistTrieNode {
    // Inserts a path into the Trie.
    // Paths are expected to be absolute and components UTF-8.
    fn insert(&mut self, path: &Path) {
        let mut current_node = self;
        // Handle the case where the root "/" itself is blacklisted.
        if path.components().count() == 1 && path.has_root() {
            if let Some(std::path::Component::RootDir) = path.components().next() {
                current_node.is_blacklisted_here = true;
                return;
            }
        }

        for component in path.components() {
            match component {
                std::path::Component::Normal(os_str) => {
                    if let Some(name) = os_str.to_str() {
                        current_node = current_node.children.entry(name.to_string()).or_default();
                    } else {
                        eprintln!(
                            "[BLACKLIST_TRIE] Non-UTF8 path component in blacklist path: {:?}",
                            path
                        );
                        return; // Skip this path
                    }
                }
                std::path::Component::RootDir => {
                    // RootDir is the starting point, handled by `current_node` being `self`.
                    // If the root node itself needs to be marked (for path "/"),
                    // it's handled if "/" is explicitly passed and has only RootDir.
                }
                _ => { /* Ignore CurDir, ParentDir, Prefix for trie structure */ }
            }
        }
        current_node.is_blacklisted_here = true; // Mark the end of this path as blacklisted
    }

    // Checks if the given path or any of its ancestors are in the Trie and marked as blacklisted.
    // Path is assumed to be absolute.
    fn is_path_or_ancestor_blacklisted(&self, path: &Path) -> bool {
        let mut current_node = self;

        // Check if the root of the trie itself is blacklisted (e.g., if "/" was inserted).
        if current_node.is_blacklisted_here {
            return true;
        }

        for component in path.components() {
            match component {
                std::path::Component::Normal(os_str) => {
                    if let Some(name) = os_str.to_str() {
                        if let Some(next_node) = current_node.children.get(name) {
                            if next_node.is_blacklisted_here {
                                return true; // This path component or an ancestor forms a blacklisted path.
                            }
                            current_node = next_node;
                        } else {
                            // Component not found, so path is not blacklisted via this Trie.
                            return false;
                        }
                    } else {
                        eprintln!(
                            "[BLACKLIST_TRIE] Non-UTF8 path component in path to check: {:?}",
                            path
                        );
                        return false; // Treat as not blacklisted
                    }
                }
                std::path::Component::RootDir => {
                    // Already handled by initial check on `self.is_blacklisted_here`
                    // and `current_node` starting at `self`.
                }
                _ => { /* Ignore CurDir, ParentDir, Prefix */ }
            }
        }
        // If the loop completes, it means the full path exists in the Trie.
        // The check `next_node.is_blacklisted_here` inside the loop covers if the path itself
        // or any of its prefixes matches a blacklisted entry.
        // If the path itself is blacklisted, the last `next_node.is_blacklisted_here` would have been true.
        false
    }
}
// --- End of Blacklist Trie ---

// 文件监控统计信息
#[derive(Debug, Default, Clone, Serialize)]
pub struct MonitorStats {
    pub processed_files: u64,  // 处理的文件数量
    pub filtered_files: u64,   // 被过滤的文件数量
    pub filtered_bundles: u64, // 处理的macOS包数量（改为只计数，不过滤）
    pub error_count: u64,      // 处理错误次数
}

// 批处理器统计信息
#[derive(Debug, Default)]
struct BatchProcessorStats {
    received_files: u64,              // 接收到的文件总数
    hidden_files_skipped: u64,        // 跳过的隐藏文件
    rule_excluded_files_skipped: u64, // 被规则排除的文件
    invalid_extension_skipped: u64,   // 扩展名不在白名单的文件
    ds_store_skipped: u64,            // 跳过的 .DS_Store 文件
    directory_skipped: u64,           // 跳过的目录
    bundle_skipped: u64,              // 跳过的macOS bundle文件
    processed_files: u64,             // 实际处理的文件数
}

// --- New Configuration Structs ---
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileCategoryRust {
    pub id: i32,
    pub name: String,
    pub description: Option<String>,
    pub icon: Option<String>,
    // created_at and updated_at are not strictly needed for Rust's logic
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum RuleTypeRust {
    #[serde(alias = "extension")]
    Extension,
    #[serde(alias = "filename")]
    Filename,
    #[serde(alias = "folder")]
    Folder,
    #[serde(alias = "structure")]
    Structure,
    #[serde(alias = "os_bundle")]
    OSBundle,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum RulePriorityRust {
    #[serde(alias = "low")]
    Low,
    #[serde(alias = "medium")]
    Medium,
    #[serde(alias = "high")]
    High,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum RuleActionRust {
    #[serde(alias = "include")]
    Include,
    #[serde(alias = "exclude")]
    Exclude,
    #[serde(alias = "label")]
    Label,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileFilterRuleRust {
    pub id: i32,
    pub name: String,
    pub description: Option<String>,
    pub rule_type: RuleTypeRust,
    pub category_id: Option<i32>,
    pub priority: RulePriorityRust,
    pub action: RuleActionRust,
    pub enabled: bool,
    pub is_system: bool, // May not be used by Rust client directly but good to have
    pub pattern: String,
    pub pattern_type: String, // "regex", "glob", "keyword"
    pub extra_data: Option<JsonValue>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileExtensionMapRust {
    pub id: i32,
    pub extension: String, // Should be without dot, lowercase
    pub category_id: i32,
    pub description: Option<String>,
    pub priority: RulePriorityRust,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AllConfigurations {
    pub file_categories: Vec<FileCategoryRust>,
    pub file_filter_rules: Vec<FileFilterRuleRust>,
    pub file_extension_maps: Vec<FileExtensionMapRust>,
    pub monitored_folders: Vec<MonitoredDirectory>, // Already defined as MonitoredDirectory
    #[serde(default)]
    pub full_disk_access: bool, // 是否有完全磁盘访问权限，特别是macOS
    #[serde(default)]
    pub bundle_extensions: Vec<String>, // 直接可用的 bundle 扩展名列表
}

// 简化的文件扫描配置结构（用于新的API端点）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileScanningConfig {
    pub extension_mappings: std::collections::HashMap<String, i32>, // 扩展名到分类ID的映射
    pub bundle_extensions: Vec<String>,                             // Bundle扩展名列表
    pub ignore_patterns: Vec<String>,                               // 忽略规则模式
    pub file_categories: Vec<FileCategoryRust>,                     // 文件分类信息
    #[serde(default)]
    pub error_message: Option<String>,         // 错误信息
}
// --- End of New Configuration Structs ---

// 文件元数据结构，与Python端数据库匹配
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileMetadata {
    pub file_path: String,
    pub file_name: String,
    pub extension: Option<String>,
    pub file_size: u64,
    pub created_time: u64,
    pub modified_time: u64,
    pub is_dir: bool,
    pub is_hidden: bool,
    #[serde(rename = "file_hash")] // 重命名为Python API期望的字段名
    pub hash_value: Option<String>, // 简单哈希值，例如前几KB的内容哈希
    pub category_id: Option<i32>,    // 初步分类ID
    pub labels: Option<Vec<String>>, // 初步标牌
    #[serde(rename = "matched_rules")] // 重命名为Python API期望的字段名
    pub initial_rule_matches: Option<Vec<String>>, // 匹配的初步规则
    #[serde(rename = "extra_metadata", skip_serializing_if = "Option::is_none")]
    pub extra_metadata: Option<serde_json::Value>, // 额外元数据
    #[serde(skip_serializing_if = "Option::is_none")]
    pub is_os_bundle: Option<bool>, // 是否是macOS bundle
}

// API响应结构
#[derive(Debug, Deserialize)]
#[allow(dead_code)]
pub struct ApiResponse {
    pub success: bool,
    pub message: Option<String>,
    pub data: Option<serde_json::Value>,
}

// 目录监控状态
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MonitoredDirectory {
    pub id: Option<i32>,
    pub path: String,
    pub alias: Option<String>,
    pub is_blacklist: bool,
    pub created_at: Option<String>, // Added field
    pub updated_at: Option<String>, // Added field
}

// 初始化文件监控器
#[derive(Clone)]
pub struct FileMonitor {
    // 监控目录列表（用于监控）
    monitored_dirs: Arc<Mutex<Vec<MonitoredDirectory>>>,
    // 黑名单目录列表（仅用于检查路径是否在黑名单中）
    blacklist_dirs: Arc<Mutex<Vec<MonitoredDirectory>>>,
    // 配置缓存（包含所有配置信息，如Bundle扩展名等）
    config_cache: Arc<Mutex<Option<AllConfigurations>>>,
    // API主机和端口
    api_host: String,
    api_port: u16,
    // HTTP 客户端
    client: reqwest::Client,
    // 元数据发送通道 - 公开以供防抖动监控器使用
    metadata_tx: Option<Sender<FileMetadata>>,
    // 批处理大小
    batch_size: usize,
    // 批处理间隔
    batch_interval: Duration,
    // 监控统计数据
    stats: Arc<Mutex<MonitorStats>>,
    // New field for hierarchical blacklist
    blacklist_trie: Arc<Mutex<BlacklistTrieNode>>,
    // 添加状态标志位，防止重复处理
    is_batch_processor_running: Arc<Mutex<bool>>,
    is_initial_scan_running: Arc<Mutex<bool>>,
}

impl FileMonitor {
    // 创建新的文件监控器实例
    pub fn new(api_host: String, api_port: u16) -> FileMonitor {
        FileMonitor {
            monitored_dirs: Arc::new(Mutex::new(Vec::new())),
            blacklist_dirs: Arc::new(Mutex::new(Vec::new())), // Still keep this for other potential uses or direct listing
            config_cache: Arc::new(Mutex::new(None)),
            api_host,
            api_port,
            client: reqwest::Client::builder()
                .timeout(Duration::from_secs(30))
                .build()
                .expect("Failed to create HTTP client"),
            stats: Arc::new(Mutex::new(MonitorStats::default())),
            metadata_tx: None,
            batch_size: 50,
            batch_interval: Duration::from_secs(10),
            blacklist_trie: Arc::new(Mutex::new(BlacklistTrieNode::default())), // Initialize Trie
            // 初始化状态标志位
            is_batch_processor_running: Arc::new(Mutex::new(false)),
            is_initial_scan_running: Arc::new(Mutex::new(false)),
        }
    }

    // --- fetch all configurations ---
    async fn fetch_and_store_all_config(&self) -> Result<(), String> {
        let url = format!("http://{}:{}/config/all", self.api_host, self.api_port);
        println!(
            "[CONFIG_FETCH] Fetching all configurations from URL: {}",
            url
        );

        // 添加重试机制
        let max_retries = 3;
        let mut retry_count = 0;
        let mut last_error = String::new();

        while retry_count < max_retries {
            if retry_count > 0 {
                println!(
                    "[CONFIG_FETCH] 重试获取配置 ({}/{})",
                    retry_count, max_retries
                );
                // 重试前短暂等待，等待时间随重试次数增加
                tokio::time::sleep(Duration::from_millis(500 * retry_count)).await;
            }

            // 使用客户端原本的超时设置（30秒），不额外设置
            match self.client.get(&url).send().await {
                Ok(response) => {
                    if response.status().is_success() {
                        match response.json::<AllConfigurations>().await {
                            Ok(config_data) => {
                                println!("[CONFIG_FETCH] Successfully parsed AllConfigurations. Categories: {}, FilterRules: {}, ExtMaps: {}, MonitoredFolders: {}",
                                    config_data.file_categories.len(),
                                    config_data.file_filter_rules.len(),
                                    config_data.file_extension_maps.len(),
                                    config_data.monitored_folders.len()
                                );
                                let mut cache = self.config_cache.lock().unwrap();
                                *cache = Some(config_data.clone()); // Store all fetched config

                                // 更新监控目录和黑名单目录列表
                                let mut monitored_dirs_lock = self.monitored_dirs.lock().unwrap();
                                let mut blacklist_dirs_lock = self.blacklist_dirs.lock().unwrap(); // 同时获取黑名单锁

                                // 清空黑名单目录列表，准备重新填充
                                blacklist_dirs_lock.clear();

                                // --- Build Blacklist Trie ---
                                let mut new_blacklist_trie = BlacklistTrieNode::default();
                                // --- End of Build Blacklist Trie ---

                                // 根据完全磁盘访问权限状态分类文件夹
                                let mut authorized_folders = Vec::new();

                                for dir in &config_data.monitored_folders {
                                    // 如果是黑名单文件夹，则添加到黑名单列表中
                                    if dir.is_blacklist {
                                        blacklist_dirs_lock.push(dir.clone());
                                        // Add to Trie
                                        let blacklist_path = PathBuf::from(&dir.path);
                                        // TODO: Ensure blacklist_path is absolute and normalized before inserting.
                                        // Assuming paths from API are suitable for now.
                                        new_blacklist_trie.insert(&blacklist_path);
                                        println!(
                                            "[CONFIG_FETCH] Added to blacklist (Vec & Trie): {}",
                                            dir.path
                                        );
                                        continue; // 黑名单文件夹不添加到监控列表
                                    }

                                    // 对于非黑名单文件夹，直接添加到监控列表
                                    let should_monitor = if config_data.full_disk_access {
                                        true // 有完全访问权限时监控所有非黑名单文件夹
                                    } else {
                                        true // 现在不再检查授权状态，所有非黑名单文件夹都监控
                                    };

                                    if should_monitor {
                                        authorized_folders.push(dir.clone());
                                    }
                                }

                                *monitored_dirs_lock = authorized_folders;

                                // Update the shared blacklist_trie
                                *self.blacklist_trie.lock().unwrap() = new_blacklist_trie;
                                println!("[CONFIG_FETCH] Blacklist Trie rebuilt.");

                                println!("[CONFIG_FETCH] Updated monitored_dirs with {} entries and blacklist_dirs with {} entries from /config/all. (Full disk access: {})",
                                    monitored_dirs_lock.len(), blacklist_dirs_lock.len(), config_data.full_disk_access);
                                return Ok(());
                            }
                            Err(e) => {
                                last_error = format!(
                                    "[CONFIG_FETCH] Failed to parse AllConfigurations JSON: {}",
                                    e
                                );
                                eprintln!("{}", last_error);
                            }
                        }
                    } else {
                        let status = response.status();
                        let err_text = response
                            .text()
                            .await
                            .unwrap_or_else(|_| "Failed to read error response text".to_string());
                        last_error = format!("[CONFIG_FETCH] API request for /config/all failed with status: {}. Body: {}", status, err_text);
                        eprintln!("{}", last_error);
                    }
                }
                Err(e) => {
                    last_error = format!("[CONFIG_FETCH] Failed to send request to {}: {}", url, e);
                    eprintln!("{}", last_error);
                }
            }

            retry_count += 1;
        }

        // 如果所有重试都失败，返回最后一个错误
        Err(last_error)
    }

    // 获取简化的文件扫描配置
    pub async fn fetch_file_scanning_config(&self) -> Result<FileScanningConfig, String> {
        let url = format!(
            "http://{}:{}/file-scanning-config",
            self.api_host, self.api_port
        );
        println!(
            "[CONFIG_FETCH] Fetching simplified file scanning config from URL: {}",
            url
        );

        match self.client.get(&url).send().await {
            Ok(response) => {
                if response.status().is_success() {
                    match response.json::<FileScanningConfig>().await {
                        Ok(config) => {
                            if let Some(error) = &config.error_message {
                                println!("[CONFIG_FETCH] API returned error: {}", error);
                                Err(format!("API error: {}", error))
                            } else {
                                println!("[CONFIG_FETCH] Successfully parsed FileScanningConfig. Extensions: {}, Bundles: {}, Ignore patterns: {}, Categories: {}",
                                    config.extension_mappings.len(),
                                    config.bundle_extensions.len(),
                                    config.ignore_patterns.len(),
                                    config.file_categories.len()
                                );
                                Ok(config)
                            }
                        }
                        Err(e) => {
                            let error_msg =
                                format!("Failed to parse file scanning config JSON: {}", e);
                            println!("[CONFIG_FETCH] {}", error_msg);
                            Err(error_msg)
                        }
                    }
                } else {
                    let error_msg =
                        format!("API request failed with status: {}", response.status());
                    println!("[CONFIG_FETCH] {}", error_msg);
                    Err(error_msg)
                }
            }
            Err(e) => {
                let error_msg = format!("Failed to send request: {}", e);
                println!("[CONFIG_FETCH] {}", error_msg);
                Err(error_msg)
            }
        }
    }
    // --- End of new method ---

    // 获取当前配置
    pub fn get_configurations(&self) -> Option<AllConfigurations> {
        let config_guard = self.config_cache.lock().unwrap();
        config_guard.clone()
    }

    // 添加监控目录
    // pub fn add_monitored_directory(&self, directory: MonitoredDirectory) {
    //     let mut dirs = self.monitored_dirs.lock().unwrap();
    //     dirs.push(directory);
    // }

    // 获取监控目录列表
    pub fn get_monitored_directories(&self) -> Vec<MonitoredDirectory> {
        let dirs = self.monitored_dirs.lock().unwrap();
        dirs.clone()
    }

    /// 获取当前监控的目录列表
    pub fn get_monitored_dirs(&self) -> Vec<String> {
        // 获取监控目录锁
        let monitored_dirs_guard = self.monitored_dirs.lock().unwrap();
        // 转换MonitoredDirectory为String路径
        monitored_dirs_guard
            .iter()
            .map(|dir| dir.path.clone())
            .collect()
    }

    // 获取元数据发送通道
    pub fn get_metadata_sender(&self) -> Option<Sender<FileMetadata>> {
        // 克隆当前的metadata_tx通道（如果存在）
        self.metadata_tx.clone()
    }

    // 获取API主机地址
    pub fn get_api_host(&self) -> &str {
        &self.api_host
    }

    // 获取API端口
    pub fn get_api_port(&self) -> u16 {
        self.api_port
    }

    // --- Bundle扩展名处理机制 ---

    /// 从当前配置中提取Bundle扩展名列表
    pub fn extract_bundle_extensions(&self) -> Vec<String> {
        let fallback_extensions = vec![
            ".app".to_string(),
            ".bundle".to_string(),
            ".framework".to_string(),
            ".fcpbundle".to_string(),
            ".photoslibrary".to_string(),
            ".imovielibrary".to_string(),
            ".tvlibrary".to_string(),
            ".theater".to_string(),
            ".plugin".to_string(),
            ".component".to_string(),
            ".colorSync".to_string(),
            ".mdimporter".to_string(),
            ".qlgenerator".to_string(),
            ".saver".to_string(),
            ".service".to_string(),
            ".wdgt".to_string(),
            ".xpc".to_string(),
        ];

        // 尝试从配置缓存中获取bundle扩展名
        let config_guard = self.config_cache.lock().unwrap();
        if let Some(config) = config_guard.as_ref() {
            // 1. 优先使用直接提供的 bundle_extensions 列表
            if !config.bundle_extensions.is_empty() {
                // println!("[BUNDLE_EXT] 使用/config/all中直接提供的 {} 个Bundle扩展名", config.bundle_extensions.len());
                return config.bundle_extensions.clone();
            }

            // 2. 如果直接列表为空，从规则中提取（兼容旧版API）
            let bundle_extensions: Vec<String> = config
                .file_filter_rules
                .iter()
                .filter(|rule| rule.rule_type == RuleTypeRust::OSBundle && rule.enabled)
                .filter_map(|rule| {
                    // 确保pattern是以点开头的扩展名格式
                    let pattern = &rule.pattern;
                    if pattern.starts_with('.') {
                        Some(pattern.to_string())
                    } else {
                        None
                    }
                })
                .collect();

            if !bundle_extensions.is_empty() {
                println!(
                    "[BUNDLE_EXT] 从规则配置中提取了 {} 个Bundle扩展名",
                    bundle_extensions.len()
                );
                return bundle_extensions;
            }
        }

        // 如果没有从配置中获取到，使用默认列表
        println!(
            "[BUNDLE_EXT] 使用默认Bundle扩展名列表，共 {} 项",
            fallback_extensions.len()
        );
        fallback_extensions
    }

    // --- End of Bundle扩展名处理机制 ---

    // --- 配置刷新机制 ---

    /// 刷新文件夹配置（重新获取监控目录和黑名单）
    pub async fn refresh_folder_configuration(&self) -> Result<bool, String> {
        println!("[FILE_MONITOR] 开始刷新文件夹配置...");

        // 保存当前配置的快照
        let current_monitored_dirs = self.get_monitored_dirs();
        let current_blacklist_dirs = {
            let blacklist_guard = self.blacklist_dirs.lock().unwrap();
            blacklist_guard.clone()
        };

        // 从API重新获取配置
        if let Err(e) = self.fetch_and_store_all_config().await {
            return Err(format!("刷新配置失败: {}", e));
        }

        // 检查配置是否变化
        let new_monitored_dirs = self.get_monitored_dirs();
        let new_blacklist_dirs = {
            let blacklist_guard = self.blacklist_dirs.lock().unwrap();
            blacklist_guard.clone()
        };

        // 对比变化
        let monitored_changed = current_monitored_dirs.len() != new_monitored_dirs.len()
            || current_monitored_dirs
                .iter()
                .any(|dir| !new_monitored_dirs.contains(dir));

        let blacklist_changed = current_blacklist_dirs.len() != new_blacklist_dirs.len()
            || current_blacklist_dirs
                .iter()
                .any(|dir| !new_blacklist_dirs.contains(dir));

        let config_changed = monitored_changed || blacklist_changed;

        if config_changed {
            println!("[FILE_MONITOR] 文件夹配置已更新:");
            if monitored_changed {
                println!(
                    "[FILE_MONITOR]   - 监控目录: {} -> {}",
                    current_monitored_dirs.len(),
                    new_monitored_dirs.len()
                );
            }
            if blacklist_changed {
                println!(
                    "[FILE_MONITOR]   - 黑名单目录: {} -> {}",
                    current_blacklist_dirs.len(),
                    new_blacklist_dirs.len()
                );
            }
            Ok(true)
        } else {
            println!("[FILE_MONITOR] 文件夹配置未变化");
            Ok(false)
        }
    }

    /// 刷新所有配置（通过单一API调用获取所有配置）
    pub async fn refresh_all_configurations(&self) -> Result<(), String> {
        println!("[CONFIG_REFRESH_ALL] 开始刷新所有配置...");

        // 刷新文件夹配置（包含所有配置数据，包括Bundle扩展名）
        if let Err(e) = self.refresh_folder_configuration().await {
            eprintln!("[CONFIG_REFRESH_ALL] 配置刷新失败: {}", e);
            return Err(e);
        }

        println!("[CONFIG_REFRESH_ALL] 所有配置刷新成功");

        // 配置刷新完成后，触发配置更新事件通知所有监听器
        self.notify_config_updated();
        Ok(())
    }

    /// 通知配置已更新（配置变更完成后的通知）
    fn notify_config_updated(&self) {
        // 这里可以实现实际的配置更新通知机制
        // 目前只是记录日志，将来可以添加实际的通知逻辑
        println!("[CONFIG_NOTIFY] 配置已成功更新，后续扫描将使用新配置");
    }

    /// 获取当前配置状态摘要
    pub fn get_configuration_summary(&self) -> serde_json::Value {
        let config_guard = self.config_cache.lock().unwrap();
        let monitored_dirs = self.monitored_dirs.lock().unwrap();
        let blacklist_dirs = self.blacklist_dirs.lock().unwrap();

        // 从配置中提取Bundle扩展名数量
        let bundle_extensions_count = config_guard
            .as_ref()
            .map(|c| {
                c.file_filter_rules
                    .iter()
                    .filter(|rule| rule.rule_type == RuleTypeRust::OSBundle && rule.enabled)
                    .count()
            })
            .unwrap_or(0);

        // 获取当前时间，用于显示配置时间戳
        let current_timestamp = SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        serde_json::json!({
            "has_config_cache": config_guard.is_some(),
            "config_categories_count": config_guard.as_ref().map(|c| c.file_categories.len()).unwrap_or(0),
            "config_filter_rules_count": config_guard.as_ref().map(|c| c.file_filter_rules.len()).unwrap_or(0),
            "config_extension_maps_count": config_guard.as_ref().map(|c| c.file_extension_maps.len()).unwrap_or(0),
            "full_disk_access": config_guard.as_ref().map(|c| c.full_disk_access).unwrap_or(false),
            "monitored_dirs_count": monitored_dirs.len(),
            "blacklist_dirs_count": blacklist_dirs.len(),
            "bundle_extensions_count": bundle_extensions_count,
            "timestamp": current_timestamp
        })
    }

    // --- End of 配置刷新机制 ---

    // 计算简单文件哈希（使用文件前4KB内容）
    async fn calculate_simple_hash(path: &Path, max_bytes: usize) -> Option<String> {
        match fs::File::open(path).await {
            Ok(mut file) => {
                use tokio::io::AsyncReadExt;
                let mut buffer = vec![0u8; max_bytes.min(4096)]; // 最多读4KB
                match file.read(&mut buffer).await {
                    Ok(n) => {
                        buffer.truncate(n);
                        if n > 0 {
                            use sha2::{Digest, Sha256};
                            let mut hasher = Sha256::new();
                            hasher.update(&buffer);
                            let result = hasher.finalize();
                            Some(format!("{:x}", result))
                        } else {
                            None
                        }
                    }
                    Err(_) => None,
                }
            }
            Err(_) => None,
        }
    }

    // 提取文件扩展名
    fn extract_extension(path: &Path) -> Option<String> {
        path.extension()
            .and_then(|ext| ext.to_str())
            .map(|s| s.to_lowercase())
    }

    // 检查文件是否隐藏
    fn is_hidden_file(path: &Path) -> bool {
        // 先检查文件/文件夹名本身是否以.开头
        let is_name_hidden = path
            .file_name()
            .and_then(|name| name.to_str())
            .map(|name| name.starts_with("."))
            .unwrap_or(false);

        if is_name_hidden {
            return true;
        }

        // 检查路径中是否有任何部分是隐藏文件夹（以.开头）
        if let Some(path_str) = path.to_str() {
            // 分割路径并检查每个部分
            for part in path_str.split('/') {
                if !part.is_empty() && part.starts_with(".") && part != "." && part != ".." {
                    return true;
                }
            }
        }

        false
    }

    // 检查是否为macOS bundle文件夹
    /// 静态方法：检查是否为macOS bundle文件夹（使用默认扩展名列表）
    pub fn is_macos_bundle_folder(path: &Path) -> bool {
        // 首先处理可能为null的情况
        if path.as_os_str().is_empty() {
            return false;
        }

        // 默认bundle扩展名列表（用于静态调用）
        let default_bundle_extensions = [
            ".app",
            ".bundle",
            ".framework",
            ".fcpbundle",
            ".photoslibrary",
            ".imovielibrary",
            ".tvlibrary",
            ".theater",
        ];

        // 1. 检查文件/目录名是否以已知的bundle扩展名结尾
        if let Some(file_name) = path.file_name().and_then(|n| n.to_str()) {
            let lowercase_name = file_name.to_lowercase();

            // 检查文件名是否匹配bundle扩展名
            if default_bundle_extensions
                .iter()
                .any(|ext| lowercase_name.ends_with(ext))
            {
                return true;
            }
        }

        // 添加实例方法，使用配置中的扩展名列表
        Self::is_macos_bundle_folder_with_extensions(path, &default_bundle_extensions)
    }

    /// 实例方法：检查是否为macOS bundle文件夹（使用配置中的扩展名列表）
    pub fn check_if_macos_bundle(&self, path: &Path) -> bool {
        // 首先处理可能为null的情况
        if path.as_os_str().is_empty() {
            return false;
        }

        // 从配置中获取bundle扩展名
        let bundle_extensions = self.extract_bundle_extensions();

        // 创建引用切片
        let bundle_extension_refs: Vec<&str> =
            bundle_extensions.iter().map(AsRef::as_ref).collect();

        // 使用共享的检查逻辑
        Self::is_macos_bundle_folder_with_extensions(path, &bundle_extension_refs)
    }

    /// 辅助方法：使用指定扩展名列表检查是否为macOS bundle
    fn is_macos_bundle_folder_with_extensions(path: &Path, bundle_extensions: &[&str]) -> bool {
        // 1. 检查文件/目录名是否以已知的bundle扩展名结尾
        if let Some(file_name) = path.file_name().and_then(|n| n.to_str()) {
            let lowercase_name = file_name.to_lowercase();

            // 检查文件名是否匹配bundle扩展名
            if bundle_extensions
                .iter()
                .any(|ext| lowercase_name.ends_with(ext))
            {
                return true;
            }
        }

        // 2. 检查路径中的任何部分是否包含bundle
        if let Some(path_str) = path.to_str() {
            let path_components: Vec<&str> = path_str.split('/').collect();

            for component in path_components {
                let lowercase_component = component.to_lowercase();
                if bundle_extensions.iter().any(|ext| {
                    // 检查组件是否以bundle扩展名结尾
                    lowercase_component.ends_with(ext)
                }) {
                    return true;
                }
            }
        }

        // 3. 如果是目录，检查是否有典型的macOS bundle目录结构
        if path.is_dir() && cfg!(target_os = "macos") {
            // 检查常见的bundle内部目录结构
            let contents_dir = path.join("Contents");
            if contents_dir.exists() && contents_dir.is_dir() {
                let info_plist = contents_dir.join("Info.plist");
                let macos_dir = contents_dir.join("MacOS");
                let resources_dir = contents_dir.join("Resources");

                // 如果存在Info.plist或典型的bundle子目录，很可能是一个bundle
                if info_plist.exists() || macos_dir.exists() || resources_dir.exists() {
                    return true;
                }
            }
        }

        // 如果以上检查都未通过，则不是bundle
        false
    }

    // 检查文件是否在macOS bundle内部，如果是则返回bundle路径
    pub fn is_inside_macos_bundle(path: &Path) -> Option<PathBuf> {
        if let Some(path_str) = path.to_str() {
            // 检查常见bundle扩展
            let bundle_extensions = [
                ".app/",
                ".bundle/",
                ".framework/",
                ".fcpbundle/",
                ".photoslibrary/",
                ".imovielibrary/",
                ".tvlibrary/",
                ".theater/",
            ];
            for ext in bundle_extensions.iter() {
                if path_str.contains(ext) {
                    // 找到包含该扩展名的部分，并构建bundle路径
                    if let Some(bundle_end_idx) = path_str.find(ext) {
                        let bundle_path_str = &path_str[..bundle_end_idx + ext.len() - 1]; // -1 是为了去掉末尾的斜杠
                        return Some(PathBuf::from(bundle_path_str));
                    }
                    // 如果无法解析路径，至少返回true的等价物
                    return Some(path.to_path_buf());
                }
            }
        }
        None // 不在bundle内部
    }

    // 检查路径是否在黑名单内 (New implementation using Trie)
    fn is_in_blacklist(&self, path: &Path) -> bool {
        // Ensure path is absolute for consistent Trie checking.
        // Paths from notify events are typically absolute.
        // If path might be relative, it needs normalization first.
        // For now, assume `path` is absolute as it comes from file system events.
        let path_to_check = if path.is_absolute() {
            path.to_path_buf()
        } else {
            // Attempt to make it absolute based on current dir, though this might not be ideal
            // if the context of `path` is different.
            // Best if `path` is always absolute.
            // For file system events, they are.
            // If called from elsewhere, ensure it's absolute.
            // std::env::current_dir().unwrap_or_default().join(path)
            // This part is tricky if path is not guaranteed absolute.
            // Let's assume path is absolute for now.
            path.to_path_buf()
        };

        let trie_guard = self.blacklist_trie.lock().unwrap();
        let result = trie_guard.is_path_or_ancestor_blacklisted(&path_to_check);

        // if result {
        //     println!("[BLACKLIST_TRIE_CHECK] Path {:?} IS IN BLACKLIST", path_to_check);
        // } else {
        //     println!("[BLACKLIST_TRIE_CHECK] Path {:?} is NOT in blacklist", path_to_check);
        // }
        result
    }

    // 初步应用规则进行分类
    async fn apply_initial_rules(&self, metadata: &mut FileMetadata) {
        let config_guard = self.config_cache.lock().unwrap();
        if config_guard.is_none() {
            eprintln!("[APPLY_RULES] Configuration cache is empty. Cannot apply rules.");
            return;
        }
        let config = config_guard.as_ref().unwrap();

        // 更新处理文件计数器
        if let Ok(mut stats) = self.stats.lock() {
            stats.processed_files += 1;
        }

        // 创建额外元数据对象
        let mut extra_data = serde_json::Map::new();

        // 强制标记隐藏文件为排除
        if metadata.is_hidden {
            extra_data.insert(
                "excluded_by_rule_id".to_string(),
                serde_json::Value::Number(serde_json::Number::from(9999)),
            );
            extra_data.insert(
                "excluded_by_rule_name".to_string(),
                serde_json::Value::String("隐藏文件自动排除".to_string()),
            );
            // println!("[APPLY_RULES] 隐藏文件将被自动排除: {}", metadata.file_name);
        }

        // 根据扩展名进行初步分类
        if let Some(ext) = &metadata.extension {
            // 从API获取规则
            for ext_map_rule in &config.file_extension_maps {
                if ext_map_rule.extension == *ext {
                    metadata.category_id = Some(ext_map_rule.category_id);
                    // Find category name for extra_data (optional, but nice for debugging)
                    let category_name = config
                        .file_categories
                        .iter()
                        .find(|cat| cat.id == ext_map_rule.category_id)
                        .map_or("unknown_category_id".to_string(), |cat| cat.name.clone());
                    extra_data.insert(
                        "file_type_from_ext_map".to_string(),
                        serde_json::Value::String(category_name),
                    );
                    // println!("[APPLY_RULES] Applied category {} from extension map for ext: {}", ext_map_rule.category_id, ext);
                    break; // Assuming first match is enough, or consider priority
                }
            }

            // 添加基于扩展名的标牌
            if metadata.labels.is_none() {
                metadata.labels = Some(Vec::new());
            }
            if let Some(labels) = &mut metadata.labels {
                labels.push(format!("ext:{}", ext));
            }

            // 记录扩展名到额外元数据
            extra_data.insert(
                "extension".to_string(),
                serde_json::Value::String(ext.clone()),
            );
        }

        // 根据文件名应用初步规则
        let filename = metadata.file_name.to_lowercase();
        let mut rule_matches = metadata.initial_rule_matches.clone().unwrap_or_default(); // Preserve existing if any

        // 检查是否是macOS bundle文件
        let mut is_bundle_file = metadata.is_os_bundle.unwrap_or(false);

        // Apply FileFilterRuleRust
        for filter_rule in &config.file_filter_rules {
            if !filter_rule.enabled {
                continue;
            }

            // 实现正则表达式、关键字和通配符匹配逻辑
            let mut matched_this_rule = false;

            match filter_rule.rule_type {
                RuleTypeRust::Filename => {
                    if filter_rule.pattern_type == "keyword" {
                        // 关键字匹配 - 检查文件名是否包含关键字
                        if filename.contains(&filter_rule.pattern.to_lowercase()) {
                            matched_this_rule = true;
                            // println!("[APPLY_RULES] Matched filename keyword rule '{}' for: {}", filter_rule.name, filename);
                        }
                    } else if filter_rule.pattern_type == "regex" {
                        // 正则表达式匹配
                        match regex::Regex::new(&filter_rule.pattern) {
                            Ok(regex) => {
                                if regex.is_match(&filename) {
                                    matched_this_rule = true;
                                    // println!("[APPLY_RULES] Matched filename regex rule '{}' for: {}", filter_rule.name, filename);
                                }
                            }
                            Err(e) => {
                                eprintln!(
                                    "[APPLY_RULES] Invalid regex pattern in rule '{}': {}",
                                    filter_rule.name, e
                                );
                            }
                        }
                    }
                }
                RuleTypeRust::OSBundle => {
                    // 检查文件名是否匹配macOS Bundle模式
                    if filter_rule.pattern_type == "regex" {
                        match regex::Regex::new(&filter_rule.pattern) {
                            Ok(regex) => {
                                if regex.is_match(&filename) {
                                    matched_this_rule = true;
                                    println!(
                                        "[APPLY_RULES] Matched OS_BUNDLE regex rule '{}' for: {}",
                                        filter_rule.name, filename
                                    );

                                    // 对于OSBundle类型，标记为bundle而不是排除
                                    is_bundle_file = true;

                                    // 记录bundle规则信息
                                    extra_data.insert(
                                        "macos_bundle_rule_id".to_string(),
                                        serde_json::Value::Number(serde_json::Number::from(
                                            filter_rule.id,
                                        )),
                                    );
                                    extra_data.insert(
                                        "macos_bundle_rule_name".to_string(),
                                        serde_json::Value::String(filter_rule.name.clone()),
                                    );
                                    extra_data.insert(
                                        "is_macos_bundle".to_string(),
                                        serde_json::Value::Bool(true),
                                    );

                                    // 将bundle文件添加到标牌中
                                    if metadata.labels.is_none() {
                                        metadata.labels = Some(Vec::new());
                                    }
                                    if let Some(labels) = &mut metadata.labels {
                                        if !labels.contains(&filter_rule.name) {
                                            labels.push(filter_rule.name.clone());
                                        }
                                        if !labels.contains(&"macos_bundle".to_string()) {
                                            labels.push("macos_bundle".to_string());
                                        }
                                    }
                                }
                            }
                            Err(e) => {
                                eprintln!(
                                    "[APPLY_RULES] Invalid regex pattern in rule '{}': {}",
                                    filter_rule.name, e
                                );
                            }
                        }
                    }
                }
                RuleTypeRust::Extension => {
                    if let Some(ext_val) = &metadata.extension {
                        if filter_rule.pattern_type == "keyword"
                            && ext_val.to_lowercase() == filter_rule.pattern.to_lowercase()
                        {
                            matched_this_rule = true;
                            // println!("[APPLY_RULES] Matched extension rule '{}' for: {}", filter_rule.name, ext_val);
                        } else if filter_rule.pattern_type == "regex" {
                            // 扩展名的正则表达式匹配
                            match regex::Regex::new(&filter_rule.pattern) {
                                Ok(regex) => {
                                    if regex.is_match(ext_val) {
                                        matched_this_rule = true;
                                        // println!("[APPLY_RULES] Matched extension regex rule '{}' for: {}", filter_rule.name, ext_val);
                                    }
                                }
                                Err(e) => {
                                    eprintln!(
                                        "[APPLY_RULES] Invalid regex pattern in rule '{}': {}",
                                        filter_rule.name, e
                                    );
                                }
                            }
                        }
                    }
                }
                // Folder and Structure rules might need more context than a single FileMetadata
                _ => {}
            }

            if matched_this_rule {
                rule_matches.push(filter_rule.name.clone());

                // 只为非OSBundle类型的规则应用排除逻辑
                if filter_rule.rule_type != RuleTypeRust::OSBundle {
                    match filter_rule.action {
                        RuleActionRust::Label => {
                            if metadata.labels.is_none() {
                                metadata.labels = Some(Vec::new());
                            }
                            if let Some(labels) = &mut metadata.labels {
                                // Avoid duplicate labels from the same rule, or use a Set
                                if !labels.contains(&filter_rule.name) {
                                    // Simple check
                                    labels.push(filter_rule.name.clone());
                                }
                                // If rule has a specific label in extra_data, use that
                                if let Some(JsonValue::String(label_value)) = filter_rule
                                    .extra_data
                                    .as_ref()
                                    .and_then(|ed| ed.get("label_value"))
                                {
                                    if !labels.contains(label_value) {
                                        labels.push(label_value.clone());
                                    }
                                }
                            }
                        }
                        RuleActionRust::Exclude => {
                            // 只有非bundle文件才能被排除
                            if !is_bundle_file {
                                extra_data.insert(
                                    "excluded_by_rule_id".to_string(),
                                    JsonValue::Number(serde_json::Number::from(filter_rule.id)),
                                );
                                extra_data.insert(
                                    "excluded_by_rule_name".to_string(),
                                    JsonValue::String(filter_rule.name.clone()),
                                );

                                // 更新被过滤的文件统计
                                if let Ok(mut stats) = self.stats.lock() {
                                    stats.filtered_files += 1;
                                }
                            }
                        }
                        RuleActionRust::Include => {
                            // Default behavior, no specific action needed
                        }
                    }
                }

                // 设置分类ID（如果规则有定义）
                if let Some(cat_id) = filter_rule.category_id {
                    metadata.category_id = Some(cat_id);
                }
            }
        }

        // 更新元数据中的bundle标记
        metadata.is_os_bundle = Some(is_bundle_file);

        // 设置规则匹配记录
        if !rule_matches.is_empty() {
            metadata.initial_rule_matches = Some(rule_matches);
        }

        // 设置额外元数据
        if !extra_data.is_empty() {
            metadata.extra_metadata = Some(serde_json::Value::Object(extra_data));
        }
    }

    // 获取文件元数据
    async fn get_file_metadata(path: &Path) -> Option<FileMetadata> {
        match fs::metadata(path).await {
            Ok(metadata) => {
                let file_name = path.file_name()?.to_str()?.to_string();
                let is_dir = metadata.is_dir();
                let extension = if !is_dir {
                    Self::extract_extension(path)
                } else {
                    None
                };

                // 获取时间戳，如果出错则使用当前时间
                let created = metadata
                    .created()
                    .map(|time| {
                        time.duration_since(UNIX_EPOCH)
                            .map(|d| d.as_secs())
                            .unwrap_or_else(|_| {
                                SystemTime::now()
                                    .duration_since(UNIX_EPOCH)
                                    .unwrap()
                                    .as_secs()
                            })
                    })
                    .unwrap_or_else(|_| {
                        SystemTime::now()
                            .duration_since(UNIX_EPOCH)
                            .unwrap()
                            .as_secs()
                    });

                let modified = metadata
                    .modified()
                    .map(|time| {
                        time.duration_since(UNIX_EPOCH)
                            .map(|d| d.as_secs())
                            .unwrap_or_else(|_| {
                                SystemTime::now()
                                    .duration_since(UNIX_EPOCH)
                                    .unwrap()
                                    .as_secs()
                            })
                    })
                    .unwrap_or_else(|_| {
                        SystemTime::now()
                            .duration_since(UNIX_EPOCH)
                            .unwrap()
                            .as_secs()
                    });

                // 检查是否为macOS bundle
                let is_bundle = Self::is_macos_bundle_folder(path);

                Some(FileMetadata {
                    file_path: path.to_str()?.to_string(),
                    file_name,
                    extension,
                    file_size: if is_dir { 0 } else { metadata.len() },
                    created_time: created,
                    modified_time: modified,
                    is_dir,
                    is_hidden: Self::is_hidden_file(path),
                    hash_value: None, // 哈希值稍后计算
                    category_id: None,
                    labels: None,
                    initial_rule_matches: None,
                    extra_metadata: None,
                    is_os_bundle: Some(is_bundle), // 标记是否为macOS bundle
                })
            }
            Err(_) => None,
        }
    }

    // 批量发送文件元数据到API
    async fn send_batch_metadata_to_api(
        &self,
        metadata_batch: Vec<FileMetadata>,
    ) -> Result<ApiResponse, String> {
        if metadata_batch.is_empty() {
            println!("[TEST_DEBUG] send_batch_metadata_to_api: Batch is empty, nothing to send.");
            // 根据你的逻辑，这里可能需要返回一个表示成功的默认 ApiResponse
            return Ok(ApiResponse {
                success: true,
                message: Some("No data to send".to_string()),
                data: None,
            });
        }

        let url = format!(
            "http://{}:{}/file-screening/batch", // Corrected endpoint for batch screening
            self.api_host, self.api_port
        );
        // println!("[TEST_DEBUG] send_batch_metadata_to_api: Sending batch of {} items to URL: {}", metadata_batch.len(), url);

        // 构建请求体，包含文件元数据和自动创建任务标志
        let mut request_body = serde_json::Map::new();
        request_body.insert(
            "data_list".to_string(), // Changed key from "metadata_batch" to "data_list"
            serde_json::to_value(&metadata_batch)
                .map_err(|e| format!("Failed to serialize metadata batch: {}", e))?,
        );
        request_body.insert(
            "auto_create_tasks".to_string(),
            serde_json::Value::Bool(true),
        );

        // 打印 request_body 的键
        // let keys: Vec<String> = request_body.keys().cloned().collect();
        // println!("[TEST_DEBUG] send_batch_metadata_to_api: Request body for batch keys: {:?}", keys);

        match self.client.post(&url).json(&request_body).send().await {
            Ok(response) => {
                let status = response.status();
                // println!("[TEST_DEBUG] send_batch_metadata_to_api: Received response with status: {}", status);

                if status.is_success() {
                    let response_text = response
                        .text()
                        .await
                        .unwrap_or_else(|_| "Failed to read response text".to_string());
                    match serde_json::from_str::<ApiResponse>(&response_text) {
                        Ok(api_resp) => {
                            //  println!("[TEST_DEBUG] send_batch_metadata_to_api: Successfully parsed API response: {:?}", api_resp);
                            Ok(api_resp)
                        }
                        Err(e) => {
                            eprintln!("[TEST_DEBUG] send_batch_metadata_to_api: Failed to parse successful response body: {}. Raw body snippet: {}", e, &response_text[..std::cmp::min(response_text.len(), 200)]);
                            Err(format!("Failed to parse API response from successful request: {}. Body snippet: {}", e, &response_text[..std::cmp::min(response_text.len(), 200)]))
                        }
                    }
                } else {
                    let err_text = response
                        .text()
                        .await
                        .unwrap_or_else(|_| "Failed to read error response text".to_string());
                    eprintln!("[TEST_DEBUG] send_batch_metadata_to_api: API request failed with status: {}. Body snippet: {}", status, &err_text[..std::cmp::min(err_text.len(), 200)]);
                    Err(format!(
                        "API request failed with status {}: {}",
                        status,
                        &err_text[..std::cmp::min(err_text.len(), 200)]
                    ))
                }
            }
            Err(e) => {
                eprintln!(
                    "[TEST_DEBUG] send_batch_metadata_to_api: Failed to send batch data to API: {}",
                    e
                );
                Err(format!("Failed to send batch data to API: {}", e))
            }
        }
    }

    // 处理文件变化事件 - 公开给防抖动监控器使用
    pub async fn process_file_event(
        &self,
        path: PathBuf,
        event_kind: notify::EventKind,
        app_handle: &tauri::AppHandle,
    ) -> Option<FileMetadata> {
        // println!("[PROCESS_EVENT] Processing event {:?} for path {:?}", event_kind, path);

        // 对于删除事件进行特殊处理 - 调用API删除相应的记录
        if let notify::EventKind::Remove(_) = event_kind {
            println!(
                "[PROCESS_EVENT] 检测到文件删除: {:?}. 正在从粗筛结果表中删除记录...",
                path
            );

            // 构建API请求URL
            let path_str = path.to_string_lossy().to_string();
            let url = format!(
                "http://{}:{}/screening/delete-by-path",
                self.api_host, self.api_port
            );

            // 构建请求体
            let request_body = serde_json::json!({
                "file_path": path_str
            });

            // 发送删除请求到API
            match self.client.post(&url).json(&request_body).send().await {
                Ok(response) => {
                    let status = response.status();
                    if status.is_success() {
                        println!("[PROCESS_EVENT] 成功删除文件 {:?} 的粗筛记录", path);
                        // 发射 screening-result-updated 事件
                        let payload = serde_json::json!({
                            "message": "文件筛选成功",
                            "timestamp": chrono::Utc::now().to_rfc3339()
                        });

                        if let Err(e) = app_handle.emit("screening-result-updated", &payload) {
                            eprintln!("[防抖监控] 发射screening-result-updated事件失败: {}", e);
                        } else {
                            println!("[防抖监控] 发射screening-result-updated事件: 文件筛选成功 - 删除文件");
                        }
                    } else {
                        let err_text = response
                            .text()
                            .await
                            .unwrap_or_else(|_| "Failed to read error response text".to_string());
                        eprintln!(
                            "[PROCESS_EVENT] 删除粗筛记录失败，状态码: {}. 错误信息: {}",
                            status,
                            &err_text[..std::cmp::min(err_text.len(), 200)]
                        );
                    }
                }
                Err(e) => {
                    eprintln!("[PROCESS_EVENT] 发送删除请求失败: {}", e);
                }
            }

            return None;
        }

        // 检查路径是否属于当前监控目录，忽略已删除目录的事件
        let path_str = path.to_string_lossy().to_string();
        let belongs_to_monitored_dir = {
            let dirs = self.monitored_dirs.lock().unwrap();
            // println!("[DEBUG] 检查路径 {:?} 是否属于监控目录", path_str);
            // println!("[DEBUG] 当前监控目录列表:");
            // for (i, dir) in dirs.iter().enumerate() {
            //     // 展开波浪号路径
            //     let expanded_path = if dir.path.starts_with("~/") {
            //         if let Some(home) = std::env::var("HOME").ok() {
            //             dir.path.replace("~", &home)
            //         } else {
            //             dir.path.clone()
            //         }
            //     } else {
            //         dir.path.clone()
            //     };
            //     println!("[DEBUG]   {}. 路径: {:?} (展开后: {:?}), 黑名单: {}", i+1, dir.path, expanded_path, dir.is_blacklist);
            // }
            let belongs = dirs.iter().any(|dir| {
                if dir.is_blacklist {
                    return false;
                }
                // 展开波浪号路径
                let expanded_path = if dir.path.starts_with("~/") {
                    if let Some(home) = std::env::var("HOME").ok() {
                        dir.path.replace("~", &home)
                    } else {
                        dir.path.clone()
                    }
                } else {
                    dir.path.clone()
                };
                path_str.starts_with(&expanded_path)
            });
            // println!("[DEBUG] 匹配结果: {}", belongs);
            belongs
        };

        if !belongs_to_monitored_dir {
            // println!("[PROCESS_EVENT] Path {:?} 不属于任何当前监控的目录，忽略事件", path);
            return None;
        }

        // 强制检查配置缓存是否存在 - 确保API已就绪
        if self.config_cache.lock().unwrap().is_none() {
            eprintln!("[PROCESS_EVENT] Config cache is not populated. Cannot process file event for {:?}. Attempting to fetch.", path);
            match self.fetch_and_store_all_config().await {
                Ok(_) => println!(
                    "[PROCESS_EVENT] Config fetched successfully. Processing for {:?}",
                    path
                ),
                Err(e) => {
                    eprintln!(
                        "[PROCESS_EVENT] Failed to fetch config: {}. Aborting processing for {:?}",
                        e, path
                    );
                    return None;
                }
            }
        }

        // 忽略不存在或无法访问的文件 - 最先检查这个以避免后续无用操作
        if !path.exists() {
            // println!("[PROCESS_EVENT] Path {:?} does not exist or is inaccessible. Ignoring.", path);
            return None;
        }

        // 忽略系统隐藏文件，如 .DS_Store - 次优先检查
        if Self::is_hidden_file(&path) {
            println!(
                "[PROCESS_EVENT] Path {:?} is a hidden file. Ignoring.",
                path
            );
            return None;
        }

        // 首先检查是否为macOS bundle文件
        let mut is_bundle = self.check_if_macos_bundle(&path);

        // 根据扩展名快速过滤不在白名单中的文件类型（但bundle文件例外）
        if path.is_file() && !is_bundle {
            // 添加 !is_bundle 条件，让bundle文件跳过白名单检查
            // 获取配置中的有效扩展名集合
            let valid_extensions: std::collections::HashSet<String> = {
                let config_guard = self.config_cache.lock().unwrap();
                if let Some(config) = config_guard.as_ref() {
                    config
                        .file_extension_maps
                        .iter()
                        .map(|map| map.extension.to_lowercase())
                        .collect()
                } else {
                    std::collections::HashSet::new()
                }
            };

            // 如果有效扩展名集合不为空，进行扩展名检查（不检查bundle文件）
            if !valid_extensions.is_empty() {
                if let Some(ext) = Self::extract_extension(&path) {
                    let ext_lower = ext.to_lowercase();
                    if !valid_extensions.contains(&ext_lower) {
                        println!("[PROCESS_EVENT] File {:?} has extension '{}' which is not in our whitelist. Ignoring.", path, ext_lower);
                        if let Ok(mut stats) = self.stats.lock() {
                            stats.filtered_files += 1;
                        }
                        return None;
                    }
                } else if path.is_file() {
                    // 没有扩展名的文件
                    // 如果是文件且没有扩展名，也进行过滤（可选，取决于是否要处理无扩展名文件）
                    println!(
                        "[PROCESS_EVENT] File {:?} has no extension. Ignoring.",
                        path
                    );
                    if let Ok(mut stats) = self.stats.lock() {
                        stats.filtered_files += 1;
                    }
                    return None;
                }
            }
        }

        // 检查是否位于bundle内部 - 如果是bundle内部的文件，将事件转发到bundle本身
        if let Some(bundle_path) = Self::is_inside_macos_bundle(&path) {
            if !is_bundle {
                // 如果是bundle内部文件，但自身不是bundle
                println!("[PROCESS_EVENT] Path {:?} is inside bundle {:?}. Redirecting event to the bundle.", path, bundle_path);
                // 使用 Box::pin 处理递归调用，避免无限大的 Future
                return Box::pin(self.process_file_event(bundle_path, event_kind, app_handle))
                    .await;
            }
        }

        // 其次，针对macOS，如果是目录，检查是否有隐藏的Info.plist文件，这是典型的macOS bundle标志
        let mut is_bundle_by_plist = false;
        if path.is_dir() && cfg!(target_os = "macos") {
            let info_plist = path.join("Contents/Info.plist");
            if info_plist.exists() {
                println!(
                    "[PROCESS_EVENT] Path {:?} is a macOS bundle folder (by Info.plist).",
                    path
                );
                is_bundle_by_plist = true;
                is_bundle = true; // 更新bundle标志
                                  // 不再return None，而是继续处理，但标记为bundle
            }

            // 额外检查：如果目录里有许多以"."开头的文件，可能是macOS包文件的典型特征
            if !is_bundle && !is_bundle_by_plist {
                // 如果还没被确定为bundle
                let dot_files_count = std::fs::read_dir(path.clone())
                    .map(|entries| {
                        entries
                            .filter_map(Result::ok)
                            .filter(|entry| entry.file_name().to_string_lossy().starts_with("."))
                            .count()
                    })
                    .unwrap_or(0);

                if dot_files_count > 5 {
                    // 如果有超过5个隐藏文件，可能是一个macOS包
                    println!("[PROCESS_EVENT] Path {:?} contains many hidden files ({}). Likely a macOS bundle.", path, dot_files_count);
                    is_bundle = true; // 标记为bundle，但继续处理
                }
            }
        }

        // 忽略黑名单中的路径 - 需要在bundle检查之后执行，但在获取元数据前执行
        // 这样可以避免对黑名单中的路径进行不必要的文件元数据操作
        if self.is_in_blacklist(&path) {
            println!("[PROCESS_EVENT] Path {:?} is in blacklist. Ignoring.", path);
            if let Ok(mut stats) = self.stats.lock() {
                stats.filtered_files += 1;
            }
            return None;
        }
        // println!("[TEST_DEBUG] process_file_event: Path {:?} exists.", path);

        // 获取基本文件元数据
        // println!("[TEST_DEBUG] process_file_event: Getting metadata for path {:?}", path);
        let mut metadata = match Self::get_file_metadata(&path).await {
            Some(meta) => {
                // println!("[TEST_DEBUG] process_file_event: Initial metadata for {:?}: {:?}", path, meta);
                meta
            }
            None => {
                // println!("[TEST_DEBUG] process_file_event: Failed to get metadata for path {:?}. Ignoring.", path);
                return None;
            }
        };

        // 如果是macOS bundle文件，在元数据中标记
        if is_bundle || is_bundle_by_plist {
            println!("[PROCESS_EVENT] Marking path {:?} as macOS bundle.", path);
            metadata.is_os_bundle = Some(true);

            // 在统计中记录bundle数量
            if let Ok(mut stats) = self.stats.lock() {
                stats.filtered_bundles += 1; // 虽然不过滤，我们仍然计数
            }
        }

        // 仅为文件计算哈希，不为目录计算
        if !metadata.is_dir {
            metadata.hash_value = Self::calculate_simple_hash(&path, 4096).await;
        }

        // println!("[TEST_DEBUG] process_file_event: Metadata BEFORE applying rules for {:?}: {:?}", path, metadata);

        // 应用初步规则进行分类
        // println!("[TEST_DEBUG] process_file_event: Applying initial rules for metadata of {:?}", path);
        self.apply_initial_rules(&mut metadata).await;

        // 检查文件是否被规则排除（但bundle文件例外）
        if !metadata.is_os_bundle.unwrap_or(false) {
            // 只有非bundle文件才检查排除标记
            if let Some(extra_meta) = &metadata.extra_metadata {
                if extra_meta.get("excluded_by_rule_id").is_some() {
                    println!("[PROCESS_EVENT] File {:?} was excluded by rule: {:?}. Not processing further.", metadata.file_path, extra_meta.get("excluded_by_rule_name"));
                    // 如果文件被标记为排除，直接返回None，不进行进一步处理
                    return None;
                }
            }
        }

        // println!("[TEST_DEBUG] process_file_event: Metadata AFTER applying rules for {:?}: {:?}", path, metadata); // "粗筛"结果

        Some(metadata)
    }

    // 批处理文件元数据发送
    async fn batch_processor(
        &self,
        mut rx: Receiver<FileMetadata>,
        batch_size: usize,
        batch_interval: Duration,
    ) {
        // 检查批处理器是否已经在运行
        {
            let mut is_running = self.is_batch_processor_running.lock().unwrap();
            if *is_running {
                println!("[BATCH_PROC] 批处理器已在运行，跳过重复启动");
                return;
            }
            *is_running = true;
        }

        // 使用scopeguard确保函数结束时重置运行状态
        let _is_running_guard = scopeguard::guard(&self.is_batch_processor_running, |guard| {
            if let Ok(mut is_running) = guard.lock() {
                *is_running = false;
            }
        });

        // 统计信息
        let mut stats = BatchProcessorStats {
            received_files: 0,
            hidden_files_skipped: 0,
            rule_excluded_files_skipped: 0,
            invalid_extension_skipped: 0,
            ds_store_skipped: 0,
            directory_skipped: 0,
            bundle_skipped: 0,
            processed_files: 0,
        };

        println!(
            "[BATCH_PROC] 启动批处理器，批量大小={}, 间隔={:?}",
            batch_size, batch_interval
        );
        let mut batch = Vec::with_capacity(batch_size);
        let mut last_send = tokio::time::Instant::now();

        loop {
            tokio::select! {
                maybe_metadata = rx.recv() => {
                    if let Some(metadata) = maybe_metadata {
                        stats.received_files += 1;

                        // 跳过隐藏文件 - 高优先级过滤条件
                        if metadata.is_hidden {
                            stats.hidden_files_skipped += 1;
                            println!("[BATCH_PROC] 跳过隐藏文件: {:?}", metadata.file_path);
                            continue;
                        }

                        // 检查是否为macOS bundle文件
                        // 现在我们不再跳过bundle文件，而是将其作为单个文件处理
                        if metadata.is_os_bundle.unwrap_or(false) {
                            println!("[BATCH_PROC] 处理macOS bundle文件: {:?}", metadata.file_path);
                            // 仍然计数，但是不跳过
                            //stats.bundle_skipped += 1;
                            //continue;
                        }

                        // 检查文件是否被规则排除（来自apply_initial_rules的结果）
                        if let Some(extra) = &metadata.extra_metadata {
                            if extra.get("excluded_by_rule_id").is_some() {
                                stats.rule_excluded_files_skipped += 1;
                                println!("[BATCH_PROC] 跳过已排除的文件: {:?} (规则: {:?})", metadata.file_path, extra.get("excluded_by_rule_name"));
                                continue;
                            }
                        }

                        // 白名单扩展名检查（双重保险）- 但是bundle文件例外
                        if !metadata.is_dir && !metadata.is_os_bundle.unwrap_or(false) {  // 添加对bundle文件的例外
                            // 获取配置中的有效扩展名集合
                            let valid_extensions: std::collections::HashSet<String> = {
                                let config_guard = self.config_cache.lock().unwrap();
                                if let Some(config) = config_guard.as_ref() {
                                    config.file_extension_maps.iter()
                                        .map(|map| map.extension.to_lowercase())
                                        .collect()
                                } else {
                                    std::collections::HashSet::new()
                                }
                            };

                            if !valid_extensions.is_empty() {
                                if let Some(ext) = &metadata.extension {
                                    let ext_lower = ext.to_lowercase();
                                    if !valid_extensions.contains(&ext_lower) {
                                        stats.invalid_extension_skipped += 1;
                                        println!("[BATCH_PROC] 跳过非白名单扩展名的文件: {:?} (扩展名: {})", metadata.file_path, ext_lower);
                                        continue;
                                    }
                                } else {
                                    stats.invalid_extension_skipped += 1;
                                    println!("[BATCH_PROC] 跳过无扩展名文件: {:?}", metadata.file_path);
                                    continue;
                                }
                            }
                        }

                        // 检查文件名是否包含 .DS_Store (额外检查)
                        if metadata.file_name.contains(".DS_Store") {
                            stats.ds_store_skipped += 1;
                            println!("[BATCH_PROC] 跳过 .DS_Store 文件: {:?}", metadata.file_path);
                            continue;
                        }

                        // 跳过目录，只处理文件
                        if metadata.is_dir {
                            stats.directory_skipped += 1;
                            // println!("[BATCH_PROC] 跳过目录: {:?}", metadata.file_path);
                            continue;
                        }

                        stats.processed_files += 1;

                        batch.push(metadata);
                        if batch.len() >= batch_size {
                            // println!("[BATCH_PROC] 批处理达到大小限制 ({} 项)，正在发送到API", batch.len());

                            // 发送数据到API
                            if let Err(e) = self.send_batch_metadata_to_api(batch.clone()).await {
                                eprintln!("[BATCH_PROC] 批量发送错误: {}", e);
                            }

                            batch.clear();
                            last_send = tokio::time::Instant::now();

                            // 每次发送后输出统计信息
                            println!("[BATCH_STATS] 接收: {}, 处理: {}, 跳过: {} (隐藏: {}, 规则排除: {}, 无效扩展名: {}, .DS_Store: {}, 目录: {}, Bundle: {})",
                                stats.received_files,
                                stats.processed_files,
                                stats.received_files - stats.processed_files,
                                stats.hidden_files_skipped,
                                stats.rule_excluded_files_skipped,
                                stats.invalid_extension_skipped,
                                stats.ds_store_skipped,
                                stats.directory_skipped,
                                stats.bundle_skipped
                            );
                        }
                    } else {
                        // 通道关闭
                        if !batch.is_empty() {
                            println!("[BATCH_PROC] 通道关闭，正在发送剩余批处理 ({} 项)", batch.len());

                            // 发送剩余数据到API
                            if let Err(e) = self.send_batch_metadata_to_api(batch.clone()).await {
                                eprintln!("[BATCH_PROC] 最终批量发送错误: {}", e);
                            }
                            batch.clear();
                        }

                        // 输出最终统计信息
                        println!("[BATCH_PROC] 最终统计: 接收: {}, 处理: {}, 跳过: {} (隐藏: {}, 规则排除: {}, 无效扩展名: {}, .DS_Store: {}, 目录: {}, Bundle: {})",
                            stats.received_files,
                            stats.processed_files,
                            stats.received_files - stats.processed_files,
                            stats.hidden_files_skipped,
                            stats.rule_excluded_files_skipped,
                            stats.invalid_extension_skipped,
                            stats.ds_store_skipped,
                            stats.directory_skipped,
                            stats.bundle_skipped
                        );

                        println!("[BATCH_PROC] 元数据通道关闭。退出批处理器。");
                        return;
                    }
                },
                _ = sleep(batch_interval) => {
                    if !batch.is_empty() && tokio::time::Instant::now().duration_since(last_send) >= batch_interval {
                                        println!("[BATCH_PROC] 达到批处理间隔，正在发送批处理 ({} 项)", batch.len());

                        // 发送数据到API
                        if let Err(e) = self.send_batch_metadata_to_api(batch.clone()).await {
                            eprintln!("[BATCH_PROC] 批量发送错误: {}", e);
                        }
                        batch.clear();
                        last_send = tokio::time::Instant::now();

                        // 每次发送后输出统计信息
                        println!("[BATCH_STATS] 接收: {}, 处理: {}, 跳过: {} (隐藏: {}, 规则排除: {}, 无效扩展名: {}, .DS_Store: {}, 目录: {}, Bundle: {})",
                            stats.received_files,
                            stats.processed_files,
                            stats.received_files - stats.processed_files,
                            stats.hidden_files_skipped,
                            stats.rule_excluded_files_skipped,
                            stats.invalid_extension_skipped,
                            stats.ds_store_skipped,
                            stats.directory_skipped,
                            stats.bundle_skipped
                        );
                    }
                }
            }
        }
    }

    // 执行初始扫描
    async fn perform_initial_scan(
        &self,
        tx_metadata: &Sender<FileMetadata>,
        app_handle: &tauri::AppHandle,
    ) -> Result<(), String> {
        // Guard to prevent multiple initial scans for the same FileMonitor instance
        // This flag indicates that the initial scan process has been started.
        {
            let mut is_running_guard = self.is_initial_scan_running.lock().unwrap();
            if *is_running_guard {
                println!("[INITIAL_SCAN] Initial scan has already been initiated or completed for this monitor instance. Skipping.");
                return Ok(());
            }
            *is_running_guard = true; // Mark as initiated
        }

        let directories = self.monitored_dirs.lock().unwrap().clone();

        // 获取完全磁盘访问权限状态
        let full_disk_access = {
            let cache_guard = self.config_cache.lock().unwrap();
            cache_guard
                .as_ref()
                .map_or(false, |config| config.full_disk_access)
        };

        println!(
            "[INITIAL_SCAN] Full disk access status: {}",
            full_disk_access
        );

        for dir in directories {
            // 使用与 start_monitoring 相同的逻辑来决定是否扫描目录
            // 所有非黑名单目录都扫描
            let should_scan = !dir.is_blacklist;

            if !should_scan {
                println!("[INITIAL_SCAN] 跳过目录: {}", dir.path);
                continue;
            }

            println!("[INITIAL_SCAN] 扫描目录: {}", dir.path);
            let path = PathBuf::from(&dir.path);
            if !path.exists() {
                println!("[INITIAL_SCAN] 目录不存在: {}", dir.path);
                continue;
            }

            // 使用 WalkDir 执行递归扫描
            // 由于WalkDir不允许动态跳过目录，我们需要使用不同的方法
            // 首先，创建一个过滤条件来检查路径是否应该被扫描
            let mut total_files = 0;
            let mut skipped_files = 0;
            let mut processed_files = 0;
            let mut skipped_bundles = 0;

            println!("[INITIAL_SCAN] 开始递归扫描目录: {}", dir.path);

            // 修改扫描方法，使用过滤器来排除不需要处理的路径
            let walker = WalkDir::new(&path).into_iter().filter_entry(|e| {
                // 不扫描隐藏文件
                if Self::is_hidden_file(e.path()) {
                    return false;
                }

                // 优先检查黑名单路径 - 将检查移到这里可以更早过滤掉不需要的路径
                if self.is_in_blacklist(e.path()) {
                    // println!("[INITIAL_SCAN] 跳过黑名单路径: {:?}", e.path());
                    return false;
                }

                // 不扫描macOS bundle以及其内部的所有文件
                if Self::is_macos_bundle_folder(e.path()) {
                    // 只增加bundle计数如果是顶层的bundle（不是bundle内部的文件）
                    let segments = e.path().to_string_lossy().matches('/').count();
                    if segments <= 1 {
                        // 顶层目录
                        skipped_bundles += 1; // 注意：这是线程安全的，因为在同一线程中
                                              // 不能在这里更新stats，因为这是在过滤器闭包中
                    }
                    println!("[INITIAL_SCAN] 跳过Bundle: {:?}", e.path());
                    return false;
                }

                // 检查路径中的任何部分是否包含macOS bundle扩展名
                // 这样可以确保bundle内部的所有文件也被跳过
                if let Some(bundle_path) = Self::is_inside_macos_bundle(e.path()) {
                    println!(
                        "[INITIAL_SCAN] 跳过Bundle内部文件: {:?}，属于Bundle: {:?}",
                        e.path(),
                        bundle_path
                    );
                    return false;
                }

                // 不扫描包含Info.plist的macOS应用目录
                if e.path().is_dir() && cfg!(target_os = "macos") {
                    let info_plist = e.path().join("Contents/Info.plist");
                    if info_plist.exists() {
                        skipped_bundles += 1;
                        return false;
                    }
                }

                // 如果是文件，检查扩展名是否在白名单中
                if e.path().is_file() {
                    // 获取配置中的有效扩展名集合
                    let valid_extensions: std::collections::HashSet<String> = {
                        let config_guard = self.config_cache.lock().unwrap();
                        if let Some(config) = config_guard.as_ref() {
                            config
                                .file_extension_maps
                                .iter()
                                .map(|map| map.extension.to_lowercase())
                                .collect()
                        } else {
                            std::collections::HashSet::new()
                        }
                    };

                    if !valid_extensions.is_empty() {
                        if let Some(ext) = Self::extract_extension(e.path()) {
                            let ext_lower = ext.to_lowercase();
                            if !valid_extensions.contains(&ext_lower) {
                                // 扩展名不在白名单中，跳过
                                return false;
                            }
                        } else {
                            // 没有扩展名的文件，也跳过
                            return false;
                        }
                    }
                }

                // 如果通过了所有检查，允许扫描
                true
            });

            // 正常处理剩下的文件
            let mut files_processed_count = 0;
            for entry_result in walker {
                // 忽略错误条目
                let entry = match entry_result {
                    Ok(e) => e,
                    Err(_) => continue,
                };

                total_files += 1;
                let entry_path = entry.path().to_path_buf();

                // 每处理1000个文件时重新检查黑名单配置（防止配置更新后继续扫描已加入黑名单的路径）
                files_processed_count += 1;
                if files_processed_count % 1000 == 0 {
                    // 动态检查路径是否现在在黑名单中（配置可能已更新）
                    if self.is_in_blacklist(&entry_path) {
                        println!(
                            "[INITIAL_SCAN] 检测到配置更新，跳过新加入黑名单的路径: {:?}",
                            entry_path
                        );
                        skipped_files += 1;
                        continue;
                    }
                }

                // 处理文件事件
                if let Some(metadata) = self
                    .process_file_event(
                        entry_path,
                        notify::EventKind::Create(notify::event::CreateKind::Any),
                        app_handle,
                    )
                    .await
                {
                    let _ = tx_metadata.send(metadata).await;
                    processed_files += 1;
                } else {
                    skipped_files += 1;
                }
            }

            println!("[INITIAL_SCAN] 目录 {} 扫描完成: 总文件数 {}, 处理文件数 {}, 跳过文件数 {} (其中macOS包数量: {})", 
                     dir.path, total_files, processed_files, skipped_files, skipped_bundles);

            // 更新全局统计信息
            if let Ok(mut stats) = self.stats.lock() {
                stats.processed_files += processed_files as u64;
                stats.filtered_files += skipped_files as u64;
                stats.filtered_bundles += skipped_bundles as u64;
            }
        }

        Ok(())
    }

    // 启动文件夹监控
    pub async fn start_monitoring_setup_and_initial_scan(
        &mut self,
        app_handle: tauri::AppHandle,
    ) -> Result<(), String> {
        // 确保API就绪 - 重试机制
        println!("[START_MONITORING] 正在等待API服务就绪...");

        // 最多尝试30次，每次等待1秒，共计最多等待30秒
        let max_retries = 30;
        let mut retries = 0;
        let mut config_fetched = false;

        while !config_fetched && retries < max_retries {
            match self.fetch_and_store_all_config().await {
                Ok(_) => {
                    println!("[START_MONITORING] 成功连接到API服务并获取配置！");
                    config_fetched = true;
                }
                Err(e) => {
                    if retries % 5 == 0 {
                        // 每5次尝试输出一次日志，避免日志过多
                        println!(
                            "[START_MONITORING] API服务未就绪，正在重试 ({}/{}): {}",
                            retries, max_retries, e
                        );
                    }
                    retries += 1;
                    tokio::time::sleep(Duration::from_secs(1)).await;
                }
            }
        }

        if !config_fetched {
            return Err("无法连接到API服务或获取配置，已达到最大重试次数".to_string());
        }

        let (metadata_tx, metadata_rx) = mpsc::channel::<FileMetadata>(100);
        self.metadata_tx = Some(metadata_tx.clone());

        // 启动批处理器
        let batch_size = self.batch_size;
        let batch_interval = self.batch_interval;
        let self_clone_for_batch = self.clone();
        tokio::spawn(async move {
            self_clone_for_batch
                .batch_processor(metadata_rx, batch_size, batch_interval)
                .await;
        });

        // 准备初始扫描
        let self_clone_for_scan = self.clone();
        let metadata_tx_for_scan = metadata_tx; // Pass ownership of this clone
        let app_handle_for_scan = app_handle.clone();
        tokio::spawn(async move {
            if let Err(e) = self_clone_for_scan
                .perform_initial_scan(&metadata_tx_for_scan, &app_handle_for_scan)
                .await
            {
                eprintln!("[INITIAL_SCAN] Error: {}", e);
            }

            // 初始扫描后批处理器会自动发送数据到API
            println!("[INITIAL_SCAN] Initial scan process completed.");
        });

        Ok(())
    }

    // 扫描单个目录
    pub async fn scan_single_directory(
        &self,
        path: &str,
        app_handle: Option<&tauri::AppHandle>,
    ) -> Result<(), String> {
        println!("[SINGLE_SCAN] 开始扫描单个目录: {}", path);

        // 检查配置缓存是否存在
        if self.config_cache.lock().unwrap().is_none() {
            eprintln!("[SINGLE_SCAN] 配置缓存为空，尝试获取配置");
            self.fetch_and_store_all_config().await?;
        }

        // 获取完全磁盘访问权限状态
        let _full_disk_access = {
            let cache_guard = self.config_cache.lock().unwrap();
            cache_guard
                .as_ref()
                .map_or(false, |config| config.full_disk_access)
        };

        // 检查目录是否在黑名单中
        if self.is_in_blacklist(Path::new(path)) {
            println!("[SINGLE_SCAN] 目录在黑名单中，跳过扫描: {}", path);
            return Ok(());
        }

        // 创建metadata发送通道
        let (metadata_tx, metadata_rx) = mpsc::channel::<FileMetadata>(100);

        // 启动批处理器
        let batch_size = self.batch_size;
        let batch_interval = self.batch_interval;
        let self_clone_for_batch = self.clone();
        tokio::spawn(async move {
            self_clone_for_batch
                .batch_processor(metadata_rx, batch_size, batch_interval)
                .await;
        });

        // 扫描目录
        println!("[SINGLE_SCAN] 开始扫描目录: {}", path);
        let path_buf = PathBuf::from(path);
        if !path_buf.exists() {
            return Err(format!("目录不存在: {}", path));
        }

        let mut total_files = 0;
        let mut skipped_files = 0;
        let mut processed_files = 0;
        let mut skipped_bundles = 0;

        // 使用 WalkDir 执行递归扫描
        let walker = WalkDir::new(&path_buf).into_iter().filter_entry(|e| {
            // 不扫描隐藏文件
            if Self::is_hidden_file(e.path()) {
                return false;
            }

            // 不扫描macOS bundle以及其内部的所有文件
            if Self::is_macos_bundle_folder(e.path()) {
                skipped_bundles += 1;
                println!("[SINGLE_SCAN] 跳过Bundle: {:?}", e.path());
                return false;
            }

            // 检查路径中的任何部分是否包含macOS bundle扩展名
            if let Some(bundle_path) = Self::is_inside_macos_bundle(e.path()) {
                println!(
                    "[SINGLE_SCAN] 跳过Bundle内部文件: {:?}，属于Bundle: {:?}",
                    e.path(),
                    bundle_path
                );
                return false;
            }

            true
        });

        for entry in walker {
            match entry {
                Ok(entry) => {
                    total_files += 1;

                    if total_files % 100 == 0 {
                        println!("[SINGLE_SCAN] 扫描进度: {} 个文件", total_files);
                    }

                    if !entry.file_type().is_file() {
                        continue; // 仅处理文件，跳过目录
                    }

                    // 处理单个文件 - 复用现有的 process_file_event 方法
                    if let Some(app_handle) = app_handle {
                        if let Some(metadata) = self
                            .process_file_event(
                                entry.path().to_path_buf(),
                                notify::EventKind::Create(notify::event::CreateKind::Any),
                                app_handle,
                            )
                            .await
                        {
                            if metadata_tx.send(metadata).await.is_err() {
                                eprintln!("[SINGLE_SCAN] 无法发送元数据到批处理器，通道可能已关闭");
                            }
                            processed_files += 1;
                        } else {
                            skipped_files += 1;
                        }
                    } else {
                        // 如果没有 app_handle，跳过此文件或使用备用处理逻辑
                        eprintln!(
                            "[SINGLE_SCAN] 跳过文件，因为没有提供 app_handle: {:?}",
                            entry.path()
                        );
                        skipped_files += 1;
                    }
                }
                Err(e) => {
                    eprintln!("[SINGLE_SCAN] 无法访问项目: {}", e);
                    skipped_files += 1;
                }
            }
        }

        println!("[SINGLE_SCAN] 目录 {} 扫描完成: 总文件数 {}, 处理文件数 {}, 跳过文件数 {} (其中macOS包数量: {})", 
            path, total_files, processed_files, skipped_files, skipped_bundles);

        // 更新统计信息
        if let Ok(mut stats) = self.stats.lock() {
            stats.processed_files += processed_files as u64;
            stats.filtered_files += skipped_files as u64;
            stats.filtered_bundles += skipped_bundles as u64;
        }

        Ok(())
    }
}
