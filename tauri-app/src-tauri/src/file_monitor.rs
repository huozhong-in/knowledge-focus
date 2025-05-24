use futures::stream::{FuturesUnordered, StreamExt};
use notify::{Config, RecommendedWatcher, RecursiveMode, Watcher};
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue; // For extra_data in FileFilterRuleRust
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::fs;
use tokio::sync::mpsc::{self, Receiver, Sender};
use tokio::time::sleep;
use walkdir::WalkDir;

// 文件监控统计信息
#[derive(Debug, Default, Clone, Serialize)]
pub struct MonitorStats {
    pub processed_files: u64,     // 处理的文件数量
    pub filtered_files: u64,      // 被过滤的文件数量
    pub filtered_bundles: u64,    // 被过滤的macOS包数量
    pub error_count: u64,         // 处理错误次数
}

// 批处理器统计信息
#[derive(Debug, Default)]
struct BatchProcessorStats {
    received_files: u64,           // 接收到的文件总数
    hidden_files_skipped: u64,     // 跳过的隐藏文件
    rule_excluded_files_skipped: u64, // 被规则排除的文件
    invalid_extension_skipped: u64, // 扩展名不在白名单的文件
    ds_store_skipped: u64,         // 跳过的 .DS_Store 文件
    directory_skipped: u64,        // 跳过的目录
    bundle_skipped: u64,           // 跳过的macOS bundle文件
    processed_files: u64,          // 实际处理的文件数
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
    #[serde(alias = "tag")]
    Tag,
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectRecognitionRuleRust {
    pub id: i32,
    pub name: String,
    pub description: Option<String>,
    pub rule_type: String, // e.g., "name_pattern", "structure", "metadata"
    pub pattern: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AllConfigurations {
    pub file_categories: Vec<FileCategoryRust>,
    pub file_filter_rules: Vec<FileFilterRuleRust>,
    pub file_extension_maps: Vec<FileExtensionMapRust>,
    pub project_recognition_rules: Vec<ProjectRecognitionRuleRust>,
    pub monitored_folders: Vec<MonitoredDirectory>, // Already defined as MonitoredDirectory
    #[serde(default)]
    pub full_disk_access: bool, // 是否有完全磁盘访问权限，特别是macOS
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
    #[serde(rename = "file_hash")]  // 重命名为Python API期望的字段名
    pub hash_value: Option<String>, // 简单哈希值，例如前几KB的内容哈希
    pub category_id: Option<i32>,  // 初步分类ID
    pub tags: Option<Vec<String>>, // 初步标签
    #[serde(rename = "matched_rules")] // 重命名为Python API期望的字段名
    pub initial_rule_matches: Option<Vec<String>>, // 匹配的初步规则
    #[serde(rename = "extra_metadata", skip_serializing_if = "Option::is_none")]
    pub extra_metadata: Option<serde_json::Value>, // 额外元数据
    #[serde(skip_serializing_if = "Option::is_none")]
    pub is_os_bundle: Option<bool>,  // 是否是macOS bundle
}

// API响应结构
#[derive(Debug, Deserialize)]
pub struct ApiResponse {
    pub success: bool,
    pub message: Option<String>,
    pub data: Option<serde_json::Value>,
}

// 目录监控状态
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum DirectoryAuthStatus {
    #[serde(alias = "pending")] // Add alias for "pending"
    Pending,
    #[serde(alias = "authorized")] // Add alias for "authorized"
    Authorized,
    #[serde(alias = "unauthorized")] // Add alias for "unauthorized"
    Unauthorized,
}

// 监控目录信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MonitoredDirectory {
    pub id: Option<i32>,
    pub path: String,
    pub alias: Option<String>,
    pub is_blacklist: bool,
    pub auth_status: DirectoryAuthStatus,
    pub created_at: Option<String>, // Added field
    pub updated_at: Option<String>, // Added field
}

// New struct for the API response from /directories
#[derive(Debug, Deserialize)]
struct DirectoryApiResponse {
    status: String, // Or use an enum if you have fixed status values
    full_disk_access: bool, // Added
    data: Vec<MonitoredDirectory>,
}

// 初始化文件监控器
#[derive(Clone)]
pub struct FileMonitor {
    // 监控目录列表（用于监控）
    monitored_dirs: Arc<Mutex<Vec<MonitoredDirectory>>>,
    // 黑名单目录列表（仅用于检查路径是否在黑名单中）
    blacklist_dirs: Arc<Mutex<Vec<MonitoredDirectory>>>,
    // 配置缓存
    config_cache: Arc<Mutex<Option<AllConfigurations>>>,
    // API主机和端口
    api_host: String,
    api_port: u16,
    // HTTP 客户端
    client: reqwest::Client,
    // 事件发送通道
    event_tx: Option<Sender<(PathBuf, notify::EventKind)>>,
    // 批处理大小
    batch_size: usize,
    // 批处理间隔
    batch_interval: Duration,
    // 监控统计数据
    stats: Arc<Mutex<MonitorStats>>,
}

impl FileMonitor {
    // 创建新的文件监控器实例
    pub fn new(api_host: String, api_port: u16) -> FileMonitor {
        FileMonitor {
            monitored_dirs: Arc::new(Mutex::new(Vec::new())),
            blacklist_dirs: Arc::new(Mutex::new(Vec::new())),
            config_cache: Arc::new(Mutex::new(None)), // Initialize config cache
            api_host,
            api_port,
            client: reqwest::Client::builder()
                .timeout(Duration::from_secs(30))
                .build()
                .expect("Failed to create HTTP client"),
            stats: Arc::new(Mutex::new(MonitorStats::default())),
            event_tx: None,
            batch_size: 50,
            batch_interval: Duration::from_secs(5),
        }
    }

    // --- New method to fetch all configurations ---
    async fn fetch_and_store_all_config(&self) -> Result<(), String> {
        let url = format!("http://{}:{}/config/all", self.api_host, self.api_port);
        println!("[CONFIG_FETCH] Fetching all configurations from URL: {}", url);

        match self.client.get(&url).send().await {
            Ok(response) => {
                if response.status().is_success() {
                    match response.json::<AllConfigurations>().await {
                        Ok(config_data) => {
                            println!("[CONFIG_FETCH] Successfully parsed AllConfigurations. Categories: {}, FilterRules: {}, ExtMaps: {}, ProjRules: {}, MonitoredFolders: {}",
                                config_data.file_categories.len(),
                                config_data.file_filter_rules.len(),
                                config_data.file_extension_maps.len(),
                                config_data.project_recognition_rules.len(),
                                config_data.monitored_folders.len()
                            );
                            let mut cache = self.config_cache.lock().unwrap();
                            *cache = Some(config_data.clone()); // Store all fetched config

                            // 更新监控目录和黑名单目录列表
                            let mut monitored_dirs_lock = self.monitored_dirs.lock().unwrap();
                            let mut blacklist_dirs_lock = self.blacklist_dirs.lock().unwrap(); // 同时获取黑名单锁
                            
                            // 清空黑名单目录列表，准备重新填充
                            blacklist_dirs_lock.clear();
                            
                            // 根据完全磁盘访问权限状态分类文件夹
                            let mut authorized_folders = Vec::new();
                            
                            for dir in &config_data.monitored_folders {
                                // 如果是黑名单文件夹，则添加到黑名单列表中
                                if dir.is_blacklist {
                                    blacklist_dirs_lock.push(dir.clone());
                                    println!("[CONFIG_FETCH] Added blacklist directory: {}", dir.path);
                                    continue; // 黑名单文件夹不添加到监控列表
                                }
                                
                                // 对于非黑名单文件夹，根据授权状态决定是否监控
                                let should_monitor = if config_data.full_disk_access {
                                    true // 有完全访问权限时监控所有非黑名单文件夹
                                } else {
                                    dir.auth_status == DirectoryAuthStatus::Authorized // 否则仅监控已授权文件夹
                                };
                                
                                if should_monitor {
                                    authorized_folders.push(dir.clone());
                                }
                            }
                            
                            *monitored_dirs_lock = authorized_folders;
                            
                            println!("[CONFIG_FETCH] Updated monitored_dirs with {} entries and blacklist_dirs with {} entries from /config/all. (Full disk access: {})",
                                monitored_dirs_lock.len(), blacklist_dirs_lock.len(), config_data.full_disk_access);
                            Ok(())
                        }
                        Err(e) => {
                            let err_msg = format!("[CONFIG_FETCH] Failed to parse AllConfigurations JSON: {}", e);
                            eprintln!("{}", err_msg);
                            Err(err_msg)
                        }
                    }
                } else {
                    let status = response.status();
                    let err_text = response.text().await.unwrap_or_else(|_| "Failed to read error response text".to_string());
                    let err_msg = format!("[CONFIG_FETCH] API request for /config/all failed with status: {}. Body: {}", status, err_text);
                    eprintln!("{}", err_msg);
                    Err(err_msg)
                }
            }
            Err(e) => {
                let err_msg = format!("[CONFIG_FETCH] Failed to send request to {}: {}", url, e);
                eprintln!("{}", err_msg);
                Err(err_msg)
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
    pub fn add_monitored_directory(&self, directory: MonitoredDirectory) {
        let mut dirs = self.monitored_dirs.lock().unwrap();
        dirs.push(directory);
    }

    // 获取监控目录列表
    pub fn get_monitored_directories(&self) -> Vec<MonitoredDirectory> {
        let dirs = self.monitored_dirs.lock().unwrap();
        dirs.clone()
    }

    // 更新监控目录状态
    pub fn update_directory_status(&self, path: &str, status: DirectoryAuthStatus) {
        let mut dirs = self.monitored_dirs.lock().unwrap();
        for dir in dirs.iter_mut() {
            if dir.path == path {
                dir.auth_status = status;
                break;
            }
        }
    }

    // 从API获取已授权的目录
    pub async fn fetch_authorized_directories(&self) -> Result<Vec<MonitoredDirectory>, String> {
        let url = format!("http://{}:{}/directories", self.api_host, self.api_port);
        println!("[TEST_DEBUG] fetch_authorized_directories: Fetching from URL: {}", url);

        match self.client.get(&url).send().await {
            Ok(response) => {
                if response.status().is_success() {
                    println!("[TEST_DEBUG] fetch_authorized_directories: Received successful response status: {}", response.status());
                    // Parse the entire response into DirectoryApiResponse
                    match response.json::<DirectoryApiResponse>().await {
                        Ok(api_response) => {
                            println!("[TEST_DEBUG] fetch_authorized_directories: Successfully parsed DirectoryApiResponse. Status: {}, Data items: {}", api_response.status, api_response.data.len());
                            let mut result = Vec::new();
                            for dir in api_response.data {
                                // Filter for authorized and not blacklisted directories
                                let should_monitor = if api_response.full_disk_access {
                                    !dir.is_blacklist
                                } else {
                                    dir.auth_status == DirectoryAuthStatus::Authorized && !dir.is_blacklist
                                };
                                if !should_monitor {
                                    println!("[TEST_DEBUG] fetch_authorized_directories: Skipping directory {:?} (auth_status: {:?}, is_blacklist: {})", dir.path, dir.auth_status, dir.is_blacklist);
                                } else {
                                    println!("[TEST_DEBUG] fetch_authorized_directories: Adding authorized directory: {:?}", dir.path);
                                    result.push(dir);
                                }
                            }
                            Ok(result)
                        }
                        Err(e) => {
                            // It's helpful to see the raw response text when parsing fails
                            // let response_text = response.text().await.unwrap_or_else(|_| "Failed to read response text".to_string());
                            // eprintln!("[TEST_DEBUG] fetch_authorized_directories: Failed to parse DirectoryApiResponse JSON: {}. Raw response snippet: {}", e, &response_text[..std::cmp::min(response_text.len(), 500)]);
                            // For now, just log the parsing error. The above can be uncommented if more detail is needed.
                            eprintln!("[TEST_DEBUG] fetch_authorized_directories: Failed to parse DirectoryApiResponse JSON: {}", e);
                            Err(format!("Failed to parse directory list response: {}", e))
                        }
                    }
                } else {
                    let status = response.status();
                    let err_text = response.text().await.unwrap_or_else(|_| "Failed to read error response text".to_string());
                    eprintln!("[TEST_DEBUG] fetch_authorized_directories: API request failed with status: {}. Body: {}", status, err_text);
                    Err(format!("API request for directories failed with status {}: {}", status, err_text))
                }
            }
            Err(e) => {
                eprintln!("[TEST_DEBUG] fetch_authorized_directories: Failed to send request to {}: {}", url, e);
                Err(format!("Failed to send request to {}: {}", url, e))
            },
        }
    }

    // 更新监控目录列表
    pub async fn update_monitored_directories(&self) -> Result<(), String> {
        // This function might become less critical if /config/all is the primary source
        // For now, let's keep its existing logic but also ensure config is fetched.
        // Alternatively, this could just call fetch_and_store_all_config if that's preferred.
        // For simplicity, let's assume fetch_and_store_all_config is called at start_monitoring
        // and potentially periodically. If a more immediate update is needed, this could trigger it.
        
        // Let's try to fetch from the old /directories endpoint first, then merge or prioritize.
        // Or, even better, rely on /config/all to be the single source of truth for monitored_folders.
        // The fetch_and_store_all_config already updates self.monitored_dirs.
        // So, this function could potentially just call that, or be deprecated if /config/all is sufficient.

        // For now, let's make it also call fetch_and_store_all_config to ensure configs are fresh
        // if this method is called independently.
        println!("[DEBUG] update_monitored_directories called. It will now attempt to refresh all config.");
        self.fetch_and_store_all_config().await?; // This will update self.monitored_dirs

        // The original logic of fetching from /directories is now redundant if /config/all provides monitored_folders
        // match self.fetch_authorized_directories().await {
        //     Ok(dirs) => {
        //         let mut current_dirs = self.monitored_dirs.lock().unwrap();
        //         *current_dirs = dirs; // This would be overwritten by fetch_and_store_all_config
        //         Ok(())
        //     }
        //     Err(e) => Err(e),
        // }
        Ok(())
    }

    // 计算简单文件哈希（使用文件前几KB内容）
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
        path.extension().and_then(|ext| ext.to_str()).map(|s| s.to_lowercase())
    }

    // 检查文件是否隐藏
    fn is_hidden_file(path: &Path) -> bool {
        path.file_name()
            .and_then(|name| name.to_str())
            .map(|name| name.starts_with("."))
            .unwrap_or(false)
    }
    
    // 检查是否为macOS bundle文件夹
    pub fn is_macos_bundle_folder(path: &Path) -> bool {
        // 首先处理可能为null的情况
        if path.as_os_str().is_empty() {
            return false;
        }
        
        // 设置常用的bundle扩展名，仅作为备选检测方式
        // 注意：主要检测逻辑应该基于从API获取的规则
        // 这里保留最基本的几种作为异常情况下的安全网
        let fallback_bundle_extensions = [
            ".app", ".bundle", ".framework", ".fcpbundle", ".photoslibrary", 
            ".imovielibrary", ".tvlibrary", ".theater"
        ];
        
        // 1. 检查文件/目录名是否以已知的bundle扩展名结尾
        if let Some(file_name) = path.file_name().and_then(|n| n.to_str()) {
            let lowercase_name = file_name.to_lowercase();
            
            // 检查文件名是否匹配bundle扩展名
            if fallback_bundle_extensions.iter().any(|ext| lowercase_name.ends_with(ext)) {
                return true;
            }
        }
        
        // 2. 检查路径中的任何部分是否包含bundle
        if let Some(path_str) = path.to_str() {
            let path_components: Vec<&str> = path_str.split('/').collect();
            
            for component in path_components {
                let lowercase_component = component.to_lowercase();
                if fallback_bundle_extensions.iter().any(|ext| {
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

    // 检查文件是否在macOS bundle内部
    pub fn is_inside_macos_bundle(path: &Path) -> bool {
        if let Some(path_str) = path.to_str() {
            // 检查常见bundle扩展
            let bundle_extensions = [".app/", ".bundle/", ".framework/", ".fcpbundle/", 
                                    ".photoslibrary/", ".imovielibrary/", ".tvlibrary/", ".theater/"];
            for ext in bundle_extensions.iter() {
                if path_str.contains(ext) {
                    return true;
                }
            }
        }
        false
    }

    // 检查路径是否在黑名单内
    fn is_in_blacklist(&self, path: &Path) -> bool {
        // 现在从blacklist_dirs而不是monitored_dirs中获取黑名单文件夹
        let dirs = self.blacklist_dirs.lock().unwrap();
        
        // 获取当前路径的规范化字符串表示
        let path_str = path.to_string_lossy().to_string();
        
        // 打印当前检查的路径（调试信息）
        // println!("[BLACKLIST_CHECK] 正在检查路径: {:?}", path_str);
        
        // 打印所有黑名单文件夹（调试信息）
        // println!("[BLACKLIST_DEBUG] 当前黑名单文件夹列表:");
        let mut has_blacklist = false;
        for (i, dir) in dirs.iter().enumerate() {
            // 不需要再检查is_blacklist，因为blacklist_dirs中的所有文件夹都是黑名单文件夹
            has_blacklist = true;
            // println!("[BLACKLIST_DEBUG] 黑名单 #{}: {}", i, dir.path);
        }
        
        if !has_blacklist {
            // println!("[BLACKLIST_DEBUG] 警告：没有找到任何黑名单文件夹!");
        }
        
        // 检查路径是否在任何黑名单文件夹内
        for dir in dirs.iter() {
            // 获取规范化的黑名单路径字符串用于比较
            let mut blacklist_path = dir.path.trim_end_matches('/').to_string();
            
            // 确保路径以斜杠结尾便于目录比较
            if !blacklist_path.ends_with('/') {
                blacklist_path.push('/');
            }
            
            // println!("[BLACKLIST_COMPARE] 比较 - 路径: '{}', 黑名单: '{}'", path_str, blacklist_path);
            
            // 方法1：检查路径是否以黑名单路径开头（目录匹配）
            if path_str.starts_with(&blacklist_path) {
                // println!("[BLACKLIST] 路径 {:?} 在黑名单目录内: {}", path, dir.path);
                return true;
            }
            
            // 方法2：检查路径是否与黑名单路径完全匹配（文件匹配）
            let trimmed_blacklist = dir.path.trim_end_matches('/');
            if path_str == trimmed_blacklist {
                // println!("[BLACKLIST] 路径 {:?} 与黑名单路径完全匹配: {}", path, dir.path);
                return true;
            }
            
            // 方法3：规范化路径后进行比较
            if let Ok(canonical_path) = std::fs::canonicalize(path) {
                let canonical_str = canonical_path.to_string_lossy().to_string();
                // println!("[BLACKLIST_CANONICAL] 规范化路径比较 - 路径: '{}', 黑名单: '{}'", canonical_str, blacklist_path);
                
                if canonical_str.starts_with(&blacklist_path) || canonical_str == trimmed_blacklist {
                    // println!("[BLACKLIST] 规范化路径 {:?} 在黑名单内: {}", canonical_str, dir.path);
                    return true;
                }
            }
        }
        // println!("[BLACKLIST_RESULT] 路径 {} 不在任何黑名单中", path_str);
        false
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
            extra_data.insert("excluded_by_rule_id".to_string(), serde_json::Value::Number(serde_json::Number::from(9999)));
            extra_data.insert("excluded_by_rule_name".to_string(), serde_json::Value::String("隐藏文件自动排除".to_string()));
            println!("[APPLY_RULES] 隐藏文件将被自动排除: {}", metadata.file_name);
        }
        
        // 根据扩展名进行初步分类
        if let Some(ext) = &metadata.extension {
            // 从API获取规则
            for ext_map_rule in &config.file_extension_maps {
                if ext_map_rule.extension == *ext {
                    metadata.category_id = Some(ext_map_rule.category_id);
                    // Find category name for extra_data (optional, but nice for debugging)
                    let category_name = config.file_categories.iter()
                        .find(|cat| cat.id == ext_map_rule.category_id)
                        .map_or("unknown_category_id".to_string(), |cat| cat.name.clone());
                    extra_data.insert("file_type_from_ext_map".to_string(), serde_json::Value::String(category_name));
                    // println!("[APPLY_RULES] Applied category {} from extension map for ext: {}", ext_map_rule.category_id, ext);
                    break; // Assuming first match is enough, or consider priority
                }
            }

            // 添加基于扩展名的标签
            if metadata.tags.is_none() {
                metadata.tags = Some(Vec::new());
            }
            if let Some(tags) = &mut metadata.tags {
                tags.push(format!("ext:{}", ext));
            }
            
            // 记录扩展名到额外元数据
            extra_data.insert("extension".to_string(), serde_json::Value::String(ext.clone()));
        }

        // 根据文件名应用初步规则
        let filename = metadata.file_name.to_lowercase();
        let mut rule_matches = metadata.initial_rule_matches.clone().unwrap_or_default(); // Preserve existing if any

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
                            println!("[APPLY_RULES] Matched filename keyword rule '{}' for: {}", filter_rule.name, filename);
                        }
                    } else if filter_rule.pattern_type == "regex" {
                        // 正则表达式匹配
                        match regex::Regex::new(&filter_rule.pattern) {
                            Ok(regex) => {
                                if regex.is_match(&filename) {
                                    matched_this_rule = true;
                                    println!("[APPLY_RULES] Matched filename regex rule '{}' for: {}", filter_rule.name, filename);
                                }
                            },
                            Err(e) => {
                                eprintln!("[APPLY_RULES] Invalid regex pattern in rule '{}': {}", filter_rule.name, e);
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
                                    println!("[APPLY_RULES] Matched OS_BUNDLE regex rule '{}' for: {}", filter_rule.name, filename);
                                    // 对于OS_BUNDLE类型，我们可以将其标记为排除
                                    extra_data.insert("excluded_by_rule_id".to_string(), serde_json::Value::Number(serde_json::Number::from(filter_rule.id)));
                                    extra_data.insert("excluded_by_rule_name".to_string(), serde_json::Value::String(filter_rule.name.clone()));
                                    extra_data.insert("is_macos_bundle".to_string(), serde_json::Value::Bool(true));
                                }
                            },
                            Err(e) => {
                                eprintln!("[APPLY_RULES] Invalid regex pattern in rule '{}': {}", filter_rule.name, e);
                            }
                        }
                    }
                }
                RuleTypeRust::Extension => {
                    if let Some(ext_val) = &metadata.extension {
                        if filter_rule.pattern_type == "keyword" && ext_val.to_lowercase() == filter_rule.pattern.to_lowercase() {
                            matched_this_rule = true;
                            println!("[APPLY_RULES] Matched extension rule '{}' for: {}", filter_rule.name, ext_val);
                        } else if filter_rule.pattern_type == "regex" {
                            // 扩展名的正则表达式匹配
                            match regex::Regex::new(&filter_rule.pattern) {
                                Ok(regex) => {
                                    if regex.is_match(ext_val) {
                                        matched_this_rule = true;
                                        println!("[APPLY_RULES] Matched extension regex rule '{}' for: {}", filter_rule.name, ext_val);
                                    }
                                },
                                Err(e) => {
                                    eprintln!("[APPLY_RULES] Invalid regex pattern in rule '{}': {}", filter_rule.name, e);
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
                match filter_rule.action {
                    RuleActionRust::Tag => {
                        if metadata.tags.is_none() {
                            metadata.tags = Some(Vec::new());
                        }
                        if let Some(tags) = &mut metadata.tags {
                            // Avoid duplicate tags from the same rule, or use a Set
                            if !tags.contains(&filter_rule.name) { // Simple check
                                tags.push(filter_rule.name.clone());
                            }
                            // If rule has a specific tag in extra_data, use that
                            if let Some(JsonValue::String(tag_value)) = filter_rule.extra_data.as_ref().and_then(|ed| ed.get("tag_value")) {
                                if !tags.contains(tag_value) {
                                    tags.push(tag_value.clone());
                                }
                            }
                        }
                         println!("[APPLY_RULES] Action TAG for rule '{}'", filter_rule.name);
                    }
                    RuleActionRust::Exclude => {
                        extra_data.insert("excluded_by_rule_id".to_string(), JsonValue::Number(serde_json::Number::from(filter_rule.id)));
                        extra_data.insert("excluded_by_rule_name".to_string(), JsonValue::String(filter_rule.name.clone()));
                        println!("[APPLY_RULES] Action EXCLUDE for rule '{}'. File will be marked.", filter_rule.name);
                        
                        // 更新被过滤的文件统计
                        if let Ok(mut stats) = self.stats.lock() {
                            stats.filtered_files += 1;
                        }
                        
                        // The caller (process_file_event) will need to check this extra_data field.
                    }
                    RuleActionRust::Include => {
                         println!("[APPLY_RULES] Action INCLUDE for rule '{}'", filter_rule.name);
                        // Default behavior, no specific action needed here unless it overrides an exclude
                    }
                }
                if let Some(cat_id) = filter_rule.category_id {
                    // Consider rule priority if multiple rules assign category
                    metadata.category_id = Some(cat_id);
                    println!("[APPLY_RULES] Rule '{}' assigned category_id: {}", filter_rule.name, cat_id);
                }
            }
        }

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
                    tags: None,
                    initial_rule_matches: None,
                    extra_metadata: None, // 新增字段
                    is_os_bundle: Some(is_bundle), // 标记是否为macOS bundle
                })
            }
            Err(_) => None,
        }
    }

    // 发送文件元数据到API
    async fn send_metadata_to_api(&self, metadata: &FileMetadata) -> Result<bool, String> {
        let url = format!(
            "http://{}:{}/file-screening",
            self.api_host, self.api_port
        );

        match self.client.post(&url).json(metadata).send().await {
            Ok(response) => {
                if response.status().is_success() {
                    Ok(true)
                } else {
                    let status = response.status();
                    let error_text = response.text().await.unwrap_or_else(|_| "Unknown error".to_string());
                    Err(format!("API request failed with status: {}, error: {}", status, error_text))
                }
            }
            Err(e) => Err(format!("Failed to send data to API: {}", e)),
        }
    }

    // 批量发送文件元数据到API
    async fn send_batch_metadata_to_api(&self, metadata_batch: Vec<FileMetadata>) -> Result<ApiResponse, String> {
        if metadata_batch.is_empty() {
            println!("[TEST_DEBUG] send_batch_metadata_to_api: Batch is empty, nothing to send.");
            // 根据你的逻辑，这里可能需要返回一个表示成功的默认 ApiResponse
            return Ok(ApiResponse { success: true, message: Some("No data to send".to_string()), data: None });
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
            serde_json::to_value(&metadata_batch).map_err(|e| format!("Failed to serialize metadata batch: {}", e))?
        );
        request_body.insert("auto_create_tasks".to_string(), serde_json::Value::Bool(true));
        
        // 打印 request_body 的键
        let keys: Vec<String> = request_body.keys().cloned().collect();
        // println!("[TEST_DEBUG] send_batch_metadata_to_api: Request body for batch keys: {:?}", keys);

        match self.client.post(&url).json(&request_body).send().await {
            Ok(response) => {
                let status = response.status();
                // println!("[TEST_DEBUG] send_batch_metadata_to_api: Received response with status: {}", status);

                if status.is_success() {
                    let response_text = response.text().await.unwrap_or_else(|_| "Failed to read response text".to_string());
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
                     let err_text = response.text().await.unwrap_or_else(|_| "Failed to read error response text".to_string());
                     eprintln!("[TEST_DEBUG] send_batch_metadata_to_api: API request failed with status: {}. Body snippet: {}", status, &err_text[..std::cmp::min(err_text.len(), 200)]);
                     Err(format!("API request failed with status {}: {}", status, &err_text[..std::cmp::min(err_text.len(), 200)]))
                }
            }
            Err(e) => {
                eprintln!("[TEST_DEBUG] send_batch_metadata_to_api: Failed to send batch data to API: {}", e);
                Err(format!("Failed to send batch data to API: {}", e))
            }
        }
    }

    // 处理文件变化事件
    async fn process_file_event(&self, path: PathBuf, event_kind: notify::EventKind) -> Option<FileMetadata> {
        // println!("[PROCESS_EVENT] Processing event {:?} for path {:?}", event_kind, path);

        // 对于删除事件进行特殊处理 - 现在只能记录不能处理
        if let notify::EventKind::Remove(_) = event_kind {
            println!("[PROCESS_EVENT] File removal detected for {:?}. Cannot process removed files directly.", path);
            // 未来可以考虑查询数据库删除相关记录
            return None;
        }

        // 强制检查配置缓存是否存在 - 确保API已就绪
        if self.config_cache.lock().unwrap().is_none() {
            eprintln!("[PROCESS_EVENT] Config cache is not populated. Cannot process file event for {:?}. Attempting to fetch.", path);
            match self.fetch_and_store_all_config().await {
                Ok(_) => println!("[PROCESS_EVENT] Config fetched successfully. Processing for {:?}", path),
                Err(e) => {
                    eprintln!("[PROCESS_EVENT] Failed to fetch config: {}. Aborting processing for {:?}", e, path);
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
            println!("[PROCESS_EVENT] Path {:?} is a hidden file. Ignoring.", path);
            return None;
        }
        
        // 根据扩展名快速过滤不在白名单中的文件类型
        if path.is_file() {
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
            
            // 如果有效扩展名集合不为空，进行扩展名检查
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
                } else if path.is_file() { // 没有扩展名的文件
                    // 如果是文件且没有扩展名，也进行过滤（可选，取决于是否要处理无扩展名文件）
                    println!("[PROCESS_EVENT] File {:?} has no extension. Ignoring.", path);
                    if let Ok(mut stats) = self.stats.lock() {
                        stats.filtered_files += 1;
                    }
                    return None;
                }
            }
        }
        
        // 检查macOS bundle文件夹 - 这是高优先级过滤，应该在黑名单检查前执行
        if Self::is_macos_bundle_folder(&path) {
            println!("[PROCESS_EVENT] Path {:?} is a macOS bundle folder (by extension). Ignoring.", path);
            // 增加统计计数器，记录过滤掉的bundle数量
            if let Ok(mut stats) = self.stats.lock() {
                stats.filtered_bundles += 1;
            }
            return None;
        }
        
        // 检查是否位于bundle内部
        if Self::is_inside_macos_bundle(&path) {
            println!("[PROCESS_EVENT] Path {:?} is inside a macOS bundle. Ignoring.", path);
            if let Ok(mut stats) = self.stats.lock() {
                stats.filtered_files += 1;
            }
            return None;
        }
        
        // 其次，针对macOS，如果是目录，检查是否有隐藏的Info.plist文件，这是典型的macOS bundle标志
        if path.is_dir() && cfg!(target_os = "macos") {
            let info_plist = path.join("Contents/Info.plist");
            if info_plist.exists() {
                println!("[PROCESS_EVENT] Path {:?} is a macOS bundle folder (by Info.plist). Ignoring.", path);
                if let Ok(mut stats) = self.stats.lock() {
                    stats.filtered_bundles += 1;
                }
                return None;
            }
            
            // 额外检查：如果目录里有许多以"."开头的文件，可能是macOS包文件的典型特征
            let dot_files_count = std::fs::read_dir(path.clone())
                .map(|entries| {
                    entries.filter_map(Result::ok)
                           .filter(|entry| 
                               entry.file_name().to_string_lossy().starts_with(".")
                           ).count()
                })
                .unwrap_or(0);
                
            if dot_files_count > 5 {  // 如果有超过5个隐藏文件，可能是一个macOS包
                println!("[PROCESS_EVENT] Path {:?} contains many hidden files ({}). Likely a macOS bundle. Ignoring.", path, dot_files_count);
                if let Ok(mut stats) = self.stats.lock() {
                    stats.filtered_bundles += 1;
                }
                return None;
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

        // 仅为文件计算哈希，不为目录计算
        if !metadata.is_dir {
            // println!("[TEST_DEBUG] process_file_event: Calculating hash for file {:?}", path);
            metadata.hash_value = Self::calculate_simple_hash(&path, 4096).await;
            // println!("[TEST_DEBUG] process_file_event: Calculated hash for {:?}: {:?}", path, metadata.hash_value.as_deref().unwrap_or("N/A"));
        } else {
            // println!("[TEST_DEBUG] process_file_event: Path {:?} is a directory, skipping hash calculation.", path);
        }
        
        // println!("[TEST_DEBUG] process_file_event: Metadata BEFORE applying rules for {:?}: {:?}", path, metadata);

        // 应用初步规则进行分类
        // println!("[TEST_DEBUG] process_file_event: Applying initial rules for metadata of {:?}", path);
        self.apply_initial_rules(&mut metadata).await; 
        
        // Check if the file was marked for exclusion by rules
        if let Some(extra_meta) = &metadata.extra_metadata {
            if extra_meta.get("excluded_by_rule_id").is_some() {
                println!("[PROCESS_EVENT] File {:?} was excluded by rule: {:?}. Not processing further.", metadata.file_path, extra_meta.get("excluded_by_rule_name"));
                // 如果文件被标记为排除，直接返回None，不进行进一步处理
                return None;
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
        batch_interval: Duration
    ) {
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
        
        println!("[BATCH_PROC] 启动批处理器，批量大小={}, 间隔={:?}", batch_size, batch_interval);
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
                        
                        // 检查是否为bundle或bundle内部文件（应该在process_file_event中已过滤，这里是双重保证）
                        if metadata.is_os_bundle.unwrap_or(false) {
                            stats.bundle_skipped += 1;
                            println!("[BATCH_PROC] 跳过macOS bundle文件: {:?}", metadata.file_path);
                            continue;
                        }
                        
                        // 检查文件是否被规则排除（来自apply_initial_rules的结果）
                        if let Some(extra) = &metadata.extra_metadata {
                            if extra.get("excluded_by_rule_id").is_some() {
                                stats.rule_excluded_files_skipped += 1;
                                println!("[BATCH_PROC] 跳过已排除的文件: {:?} (规则: {:?})", metadata.file_path, extra.get("excluded_by_rule_name"));
                                continue;
                            }
                        }
                        
                        // 白名单扩展名检查（双重保险）
                        if !metadata.is_dir {
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
                            println!("[BATCH_PROC] 跳过目录: {:?}", metadata.file_path);
                            continue;
                        }
                        
                        stats.processed_files += 1;
                        
                        batch.push(metadata);
                        if batch.len() >= batch_size {
                            println!("[BATCH_PROC] 批处理达到大小限制 ({} 项)，正在发送到API", batch.len());
                            
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
                        if (!batch.is_empty()) {
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

    // 事件处理器
    async fn event_handler(
        &self,
        mut rx: Receiver<(PathBuf, notify::EventKind)>,
        tx_metadata: Sender<FileMetadata>,
    ) {
        println!("[EVENT_HANDLER] Started event handler");
        while let Some((path, kind)) = rx.recv().await {
            println!("[EVENT_HANDLER] Received event {:?} for path {:?}", kind, path);
            if let Some(metadata) = self.process_file_event(path.clone(), kind).await {
                println!("[EVENT_HANDLER] Processed metadata for {:?}, sending to batch processor", path);
                if let Err(e) = tx_metadata.send(metadata).await {
                    eprintln!("[EVENT_HANDLER] Error sending metadata to batch processor: {}", e);
                } else {
                    println!("[EVENT_HANDLER] Successfully sent metadata to batch processor");
                }
            } else {
                println!("[EVENT_HANDLER] No metadata produced for path {:?}", path);
            }
        }
        println!("[EVENT_HANDLER] Event handler channel closed, exiting");
    }

    // 执行初始扫描
    async fn perform_initial_scan(&self, tx_metadata: &Sender<FileMetadata>) -> Result<(), String> {
        let directories = self.monitored_dirs.lock().unwrap().clone();
        
        // 获取完全磁盘访问权限状态
        let full_disk_access = {
            let cache_guard = self.config_cache.lock().unwrap();
            cache_guard.as_ref().map_or(false, |config| config.full_disk_access)
        };
        
        println!("[INITIAL_SCAN] Full disk access status: {}", full_disk_access);
        
        for dir in directories {
            // 使用与 start_monitoring 相同的逻辑来决定是否扫描目录
            let should_scan = if full_disk_access {
                !dir.is_blacklist
            } else {
                dir.auth_status == DirectoryAuthStatus::Authorized && !dir.is_blacklist
            };
            
            if !should_scan {
                println!("[INITIAL_SCAN] 跳过目录: {}", dir.path);
                continue;
            }
            
            println!("[INITIAL_SCAN] 扫描目录: {}", dir.path);
            let path = PathBuf::from(&dir.path);
            if (!path.exists()) {
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
            let walker = WalkDir::new(&path).into_iter()
                .filter_entry(|e| {
                    // 不扫描隐藏文件
                    if Self::is_hidden_file(e.path()) {
                        return false;
                    }
                    
                    // 优先检查黑名单路径 - 将检查移到这里可以更早过滤掉不需要的路径
                    if self.is_in_blacklist(e.path()) {
                        println!("[INITIAL_SCAN] 跳过黑名单路径: {:?}", e.path());
                        return false;
                    }
                    
                    // 不扫描macOS bundle以及其内部的所有文件
                    if Self::is_macos_bundle_folder(e.path()) {
                        // 只增加bundle计数如果是顶层的bundle（不是bundle内部的文件）
                        let segments = e.path().to_string_lossy().matches('/').count();
                        if (segments <= 1) { // 顶层目录
                            skipped_bundles += 1;  // 注意：这是线程安全的，因为在同一线程中
                            // 不能在这里更新stats，因为这是在过滤器闭包中
                        }
                        println!("[INITIAL_SCAN] 跳过Bundle或其内部文件: {:?}", e.path());
                        return false;
                    }
                    
                    // 检查路径中的任何部分是否包含macOS bundle扩展名
                    // 这样可以确保bundle内部的所有文件也被跳过
                    if Self::is_inside_macos_bundle(e.path()) {
                        println!("[INITIAL_SCAN] 跳过Bundle内部文件: {:?}", e.path());
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
                                config.file_extension_maps.iter()
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
            for entry_result in walker {
                // 忽略错误条目
                let entry = match entry_result {
                    Ok(e) => e,
                    Err(_) => continue,
                };
                
                total_files += 1;
                let entry_path = entry.path().to_path_buf();
                
                // 黑名单路径已在filter_entry中检查，这里不再需要重复检查
                
                // 处理文件事件
                if let Some(metadata) = self.process_file_event(
                    entry_path,
                    notify::EventKind::Create(notify::event::CreateKind::Any),
                ).await {
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
    pub async fn start_monitoring(&mut self) -> Result<(), String> {
        // 确保API就绪 - 重试机制
        println!("[START_MONITORING] 正在等待API服务就绪...");
        
        // 最多尝试60次，每次等待1秒，共计最多等待60秒
        let max_retries = 60;
        let mut retries = 0;
        let mut config_fetched = false;
        
        while !config_fetched && retries < max_retries {
            match self.fetch_and_store_all_config().await {
                Ok(_) => {
                    println!("[START_MONITORING] 成功连接到API服务并获取配置！");
                    config_fetched = true;
                },
                Err(e) => {
                    if retries % 5 == 0 { // 每5次尝试输出一次日志，避免日志过多
                        println!("[START_MONITORING] API服务尚未就绪，等待中 ({}/{}): {}", retries, max_retries, e);
                    }
                    retries += 1;
                    sleep(Duration::from_secs(1)).await;
                }
            }
        }
        
        if !config_fetched {
            let error = format!("经过{}秒尝试，无法连接到API服务获取配置", max_retries);
            eprintln!("[START_MONITORING] {}", error);
            return Err(error);
        }
        
        println!("[START_MONITORING] API服务连接成功，配置已获取");

        // self.update_monitored_directories().await?; // This is now part of fetch_and_store_all_config

        // 获取完全磁盘访问权限状态
        let full_disk_access = {
            let cache_guard = self.config_cache.lock().unwrap();
            cache_guard.as_ref().map_or(false, |config| config.full_disk_access)
        };
        
        println!("[START_MONITORING] Full disk access status: {}", full_disk_access);
        
        // Clone the monitored directories to avoid holding the lock across await points
        let dirs_to_watch = {
            let dirs_guard = self.monitored_dirs.lock().unwrap();
            
            // 调试用：打印所有目录及其授权状态
            println!("[DEBUG_MONITORING] 所有监控目录列表:");
            for (i, dir) in dirs_guard.iter().enumerate() {
                println!("[DEBUG_MONITORING] 目录 {}: 路径='{}', 授权状态={:?}, 黑名单={}", 
                    i, dir.path, dir.auth_status, dir.is_blacklist);
            }
            
            dirs_guard.iter()
                .filter(|d| {
                    // 如果有完全磁盘访问权限，只过滤黑名单文件夹
                    // 否则，需要同时判断授权状态和黑名单状态
                    let watch_this_dir = if full_disk_access {
                        !d.is_blacklist
                    } else {
                        d.auth_status == DirectoryAuthStatus::Authorized && !d.is_blacklist
                    };
                    
                    // 调试日志
                    println!("[DEBUG_MONITORING] 目录 '{}': {}将被监控", 
                        d.path, if watch_this_dir { "" } else { "不" });
                    
                    watch_this_dir
                })
                .cloned()
                .collect::<Vec<_>>()
        };
        
        // 调试用：打印实际监控的目录列表
        println!("[DEBUG_MONITORING] 以下{}个目录将被监控:", dirs_to_watch.len());
        for (i, dir) in dirs_to_watch.iter().enumerate() {
            println!("[DEBUG_MONITORING] 监控目录 {}: '{}'", i+1, dir.path);
        }
        
        if dirs_to_watch.is_empty() {
            return Err("自动启动文件监控失败: No authorized directories to monitor".into());
        }

        // 创建事件通道
        let (event_tx, event_rx) = mpsc::channel::<(PathBuf, notify::EventKind)>(100);
        let (metadata_tx, metadata_rx) = mpsc::channel::<FileMetadata>(100);
        
        self.event_tx = Some(event_tx.clone());
         
        // 创建元数据发送通道的克隆，用于事件处理器和初始扫描
        let metadata_tx_for_events = metadata_tx.clone();
        let metadata_tx_for_scan = metadata_tx.clone();
        
        // 启动批处理器
        let batch_size = self.batch_size;
        let batch_interval = self.batch_interval;
        let self_clone_for_batch = self.clone();
        tokio::spawn(async move {
            self_clone_for_batch.batch_processor(metadata_rx, batch_size, batch_interval).await;
        });
        
        // 启动事件处理器
        let self_clone_for_events = self.clone();
        tokio::spawn(async move {
            self_clone_for_events.event_handler(event_rx, metadata_tx_for_events).await;
        });

        // 准备初始扫描
        let self_clone_for_scan = self.clone();
        tokio::spawn(async move {
            if let Err(e) = self_clone_for_scan.perform_initial_scan(&metadata_tx_for_scan).await {
                eprintln!("Initial scan error: {}", e);
            }
            
            // 初始扫描后批处理器会自动发送数据到API，并设置auto_create_tasks=true
            // 不需要额外调用notify_api_for_analysis，因为批处理已经包含了任务创建
            sleep(Duration::from_secs(5)).await; // 等待批处理完成
            println!("[INITIAL_SCAN] Initial scan complete and batch processing should have triggered tasks via auto_create_tasks=true");
        });

        // 为每个授权目录创建监控器
        let mut watcher_futures = FuturesUnordered::new();
        
        for dir in dirs_to_watch {
            let dir_path = dir.path.clone();
            let event_tx = event_tx.clone();
            
            watcher_futures.push(tokio::spawn(async move {
                if let Err(e) = Self::watch_directory(&dir_path, event_tx).await {
                    eprintln!("Error watching directory {}: {}", dir_path, e);
                    Err(e)
                } else {
                    Ok(())
                }
            }));
        }
        
        // 等待所有监控器启动
        while let Some(result) = watcher_futures.next().await {
            if let Err(e) = result {
                eprintln!("Watcher task failed: {}", e);
            }
        }
        
        Ok(())
    }

    // 为单个目录创建监控器
    async fn watch_directory(dir_path: &str, event_tx: Sender<(PathBuf, notify::EventKind)>) -> Result<(), String> {
        // println!("[TEST_DEBUG] watch_directory: Starting for path: {}", dir_path);

        // 创建通道用于接收文件系统事件
        let (watcher_tx, mut watcher_rx) = mpsc::channel(100);
        
        // 创建推荐的监控器
        let mut watcher = RecommendedWatcher::new(
            move |res| {
                let _ = watcher_tx.blocking_send(res);
            },
            Config::default(),
        )
        .map_err(|e| format!("Failed to create watcher: {}", e))?;
        
        // println!("[TEST_DEBUG] watch_directory: Watcher created for path: {}", dir_path);
        
        // 开始监控指定目录
        watcher
            .watch(
                Path::new(dir_path),
                RecursiveMode::Recursive,
            )
            .map_err(|e| format!("Failed to watch directory: {}", e))?;
        
        // println!("[TEST_DEBUG] watch_directory: Successfully watching path: {}", dir_path);
        
        // 持续处理文件系统事件
        let task_dir_path = dir_path.to_string(); // Clone dir_path for the async task
        tokio::spawn(async move {
            // println!("[TEST_DEBUG] watch_directory: Event processing task started for path: {}", task_dir_path);
            while let Some(result) = watcher_rx.recv().await {
                // println!("[TEST_DEBUG] watch_directory: Received event result for path {}: {:?}", task_dir_path, result);
                match result {
                    Ok(event) => {
                        // println!("[TEST_DEBUG] watch_directory: Parsed event for path {}: {:?}", task_dir_path, event);
                        // 筛选我们关心的事件类型
                        match event.kind {
                            notify::EventKind::Create(_) | 
                            notify::EventKind::Modify(_) | 
                            notify::EventKind::Remove(_) => {
                                // println!("[TEST_DEBUG] watch_directory: Relevant event kind for path {}: {:?}, paths: {:?}", task_dir_path, event.kind, event.paths);
                                for path_buf in event.paths { // Renamed path to path_buf to avoid conflict
                                    // println!("[TEST_DEBUG] watch_directory: Sending path {:?} with kind {:?} to event_tx from watcher for {}", path_buf, event.kind, task_dir_path);
                                    
                                    // 确认路径是否与监控目录相关
                                    // if let Some(path_str) = path_buf.to_str() {
                                    //     if path_str.starts_with(&task_dir_path) || task_dir_path.starts_with(path_str) {
                                    //         println!("[TEST_DEBUG] watch_directory: Path {:?} matches monitored directory {}", path_buf, task_dir_path);
                                    //     } else {
                                    //         println!("[TEST_DEBUG] watch_directory: WARNING! Path {:?} does not seem to match monitored directory {}", path_buf, task_dir_path);
                                    //     }
                                    // }
                                    
                                    let path_for_logging = path_buf.clone();
                                    match event_tx.send((path_buf, event.kind.clone())).await {
                                        Ok(_) => println!("[TEST_DEBUG] watch_directory: Successfully sent event for {:?}", path_for_logging),
                                        Err(e) => eprintln!("[TEST_DEBUG] watch_directory: Failed to send event to event_tx for path {}: {}", task_dir_path, e)
                                    }
                                }
                            }
                            _ => {
                                // println!("[TEST_DEBUG] watch_directory: Ignoring event kind for path {}: {:?}", task_dir_path, event.kind);
                            }
                        }
                    }
                    Err(e) => eprintln!("[TEST_DEBUG] watch_directory: Watch error for path {}: {}", task_dir_path, e),
                }
            }
            // println!("[TEST_DEBUG] watch_directory: Event processing task finished for path: {}", task_dir_path);
        });
        
        Ok(())
    }

    // 获取监控统计信息
    pub fn get_monitor_stats(&self) -> MonitorStats {
        match self.stats.lock() {
            Ok(stats) => stats.clone(),
            Err(_) => MonitorStats::default(), // 返回默认统计信息，以防锁定失败
        }
    }

    // 扫描单个目录
    pub async fn scan_single_directory(&self, path: &str) -> Result<(), String> {
        println!("[SINGLE_SCAN] 开始扫描单个目录: {}", path);
        
        // 检查配置缓存是否存在
        if self.config_cache.lock().unwrap().is_none() {
            eprintln!("[SINGLE_SCAN] 配置缓存为空，尝试获取配置");
            self.fetch_and_store_all_config().await?;
        }
        
        // 获取完全磁盘访问权限状态
        let full_disk_access = {
            let cache_guard = self.config_cache.lock().unwrap();
            cache_guard.as_ref().map_or(false, |config| config.full_disk_access)
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
            self_clone_for_batch.batch_processor(metadata_rx, batch_size, batch_interval).await;
        });
        
        // 扫描目录
        println!("[SINGLE_SCAN] 开始扫描目录: {}", path);
        let path_buf = PathBuf::from(path);
        if (!path_buf.exists()) {
            return Err(format!("目录不存在: {}", path));
        }

        let mut total_files = 0;
        let mut skipped_files = 0;
        let mut processed_files = 0;
        let mut skipped_bundles = 0;
        
        // 使用 WalkDir 执行递归扫描
        let walker = WalkDir::new(&path_buf).into_iter()
            .filter_entry(|e| {
                // 不扫描隐藏文件
                if Self::is_hidden_file(e.path()) {
                    return false;
                }
                
                // 不扫描macOS bundle以及其内部的所有文件
                if Self::is_macos_bundle_folder(e.path()) {
                    skipped_bundles += 1;
                    println!("[SINGLE_SCAN] 跳过Bundle或其内部文件: {:?}", e.path());
                    return false;
                }
                
                // 检查路径中的任何部分是否包含macOS bundle扩展名
                if Self::is_inside_macos_bundle(e.path()) {
                    println!("[SINGLE_SCAN] 跳过Bundle内部文件: {:?}", e.path());
                    return false;
                }
                
                true
            });
        
        for entry in walker {
            match entry {
                Ok(entry) => {
                    total_files += 1;
                    
                    if (total_files % 100 == 0) {
                        println!("[SINGLE_SCAN] 扫描进度: {} 个文件", total_files);
                    }
                    
                    if !entry.file_type().is_file() {
                        continue; // 仅处理文件，跳过目录
                    }
                    
                    // 处理单个文件 - 复用现有的 process_file_event 方法
                    if let Some(metadata) = self.process_file_event(entry.path().to_path_buf(), notify::EventKind::Create(notify::event::CreateKind::Any)).await {
                        if metadata_tx.send(metadata).await.is_err() {
                            eprintln!("[SINGLE_SCAN] 无法发送元数据到批处理器，通道可能已关闭");
                        }
                        processed_files += 1;
                    } else {
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

    // 监控新添加的目录（在添加目录到监控列表后调用）
    pub async fn setup_watch_for_directory(&self, path: &str) -> Result<(), String> {
        println!("[SETUP_WATCH] 为新添加的目录 {} 设置监控", path);
        
        // 验证目录是否应该被监控（检查授权状态和黑名单）
        let full_disk_access = {
            let cache_guard = self.config_cache.lock().unwrap();
            cache_guard.as_ref().map_or(false, |config| config.full_disk_access)
        };
        
        // 从监控目录列表中查找此目录
        let should_watch = {
            let dirs_guard = self.monitored_dirs.lock().unwrap();
            dirs_guard.iter()
                .find(|d| d.path == path)
                .map(|dir| {
                    if full_disk_access {
                        !dir.is_blacklist
                    } else {
                        dir.auth_status == DirectoryAuthStatus::Authorized && !dir.is_blacklist
                    }
                })
                .unwrap_or(false)
        };
        
        if !should_watch {
            println!("[SETUP_WATCH] 目录 {} 不需要监控（未授权或在黑名单中）", path);
            return Ok(());
        }
        
        // 创建一个事件发送者的克隆
        if let Some(event_tx) = &self.event_tx {
            let event_tx_clone = event_tx.clone();
            
            // 为闭包克隆路径字符串，以便在async move中使用
            let path_clone = path.to_string();
            
            // 启动目录监控
            tokio::spawn(async move {
                if let Err(e) = Self::watch_directory(&path_clone, event_tx_clone).await {
                    eprintln!("[SETUP_WATCH] 为目录 {} 设置监控失败: {}", path_clone, e);
                } else {
                    println!("[SETUP_WATCH] 成功为目录 {} 设置监控", path_clone);
                }
            });
            
            Ok(())
        } else {
            Err(format!("无法为目录 {} 设置监控：事件通道未初始化", path))
        }
    }
}

#[cfg(test)]
mod tests {
    use std::path::Path;
    use super::FileMonitor;

    #[test]
    fn test_macos_bundle_detection() {
        let test_paths = vec![
            // 基础文件类型 - 不应匹配
            ("/Users/test/Documents/test.txt", false),
            ("/Users/test/Documents/notes.md", false),
            
            // 顶层包文件 - 应匹配
            ("/Users/test/Applications/App.app", true),
            ("/Users/test/Projects/MyProject.xcodeproj", true),
            ("/Users/test/Movies/FinalCutProjects/MyMovie.fcpbundle", true),
            ("/Users/test/Pictures/Photos Library.photoslibrary", true),
            ("/Users/test/Documents/Keynote/Presentation.key", true),
            ("/Users/test/Documents/Pages/Document.pages", true),
            ("/Users/test/Documents/Numbers/Spreadsheet.numbers", true),
            ("/Users/test/Library/Application Support/MyApp.bundle", true),
            ("/Users/test/Library/Frameworks/MyFramework.framework", true),
            ("/Users/test/Library/en.lproj", true),
            ("/Users/test/Library/QuickLook/Preview.qlgenerator", true),
            
            // 深层路径 - iMovie库内部的文件，应该匹配
            ("/Users/test/Movies/iMovie 剪辑资源库.imovielibrary/2025-3-16/CurrentVersion.imovieevent", true),
            ("/Users/test/Movies/iMovie 剪辑资源库.imovielibrary/Shared/Stills.modelDatabase", true),
            
            // TV库相关文件 - 应该匹配
            ("/Users/test/Movies/TV.tvlibrary", true),
            ("/Users/test/Movies/TV.tvlibrary/Library.json", true),
            ("/Users/test/Movies/TV.tvlibrary/Metadata/TV Shows/Show.tvshow", true),
            
            // 深层路径 - 应用Bundle内部的文件，应该匹配
            ("/Users/test/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/DeviceSupport/16.0/DeveloperDiskImage.dmg", true),
            ("/Users/test/Library/Developer/Xcode/DerivedData/MyApp-abc123/Build/Products/Debug/MyApp.app/Contents/Resources/Base.lproj/Main.nib", true),
            
            // 深层路径 - 照片库内部的文件，应该匹配
            ("/Users/test/Pictures/照片图库.photoslibrary/database/Library.apdb", true),
            ("/Users/test/Pictures/照片图库.photoslibrary/resources/derivatives/masters/8/867/867ED30F-9780-40EC-A704-0E94BF09E0EF_1_201_a.jpeg", true),
            
            // 普通文件夹和文件 - 不应匹配
            ("/Users/test/Documents/normal_folder", false),
            ("/Users/test/Projects/rust-project", false),
            ("/Users/test/Documents/.hidden_file", false),
            
            // 特殊情况 - 名称中包含但不完全符合bundle模式的文件/目录 - 不应匹配
            ("/Users/test/Documents/app_data.json", false),
            ("/Users/test/Projects/framework_test", false),
        ];

        for (path_str, expected_result) in test_paths {
            let path = Path::new(path_str);
            let is_bundle = FileMonitor::is_macos_bundle_folder(path);
            assert_eq!(
                is_bundle, expected_result,
                "Path '{}' was detected as {} but expected {}",
                path_str, 
                if is_bundle { "bundle" } else { "not bundle" },
                if expected_result { "bundle" } else { "not bundle" }
            );
        }
    }
}
