use futures::stream::{FuturesUnordered, StreamExt};
use notify::{Config, RecommendedWatcher, RecursiveMode, Watcher};
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue; // For extra_data in FileFilterRuleRust
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::fs;
use tokio::sync::mpsc::{self, Receiver, Sender};
use tokio::time::sleep;
use walkdir::WalkDir;

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
pub struct FileMonitor {
    monitored_dirs: Arc<Mutex<Vec<MonitoredDirectory>>>,
    config_cache: Arc<Mutex<Option<AllConfigurations>>>, // Added config cache
    api_host: String,
    api_port: u16,
    client: reqwest::Client,
    event_tx: Option<Sender<(PathBuf, notify::EventKind)>>,
    batch_size: usize,
    batch_interval: Duration,
}

impl FileMonitor {
    // 创建新的文件监控器实例
    pub fn new(api_host: String, api_port: u16) -> Self {
        FileMonitor {
            monitored_dirs: Arc::new(Mutex::new(Vec::new())),
            config_cache: Arc::new(Mutex::new(None)), // Initialize config cache
            api_host,
            api_port,
            client: reqwest::Client::builder()
                .timeout(Duration::from_secs(30))
                .build()
                .expect("Failed to create HTTP client"),
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

                            // Also update monitored_dirs from this unified config endpoint
                            let mut monitored_dirs_lock = self.monitored_dirs.lock().unwrap();
                            
                            // 根据完全磁盘访问权限状态过滤文件夹
                            let mut authorized_folders = Vec::new();
                            for dir in &config_data.monitored_folders {
                                // 如果有完全磁盘访问权限，只过滤黑名单文件夹
                                // 否则，需要同时判断授权状态和黑名单状态
                                let should_monitor = if config_data.full_disk_access {
                                    !dir.is_blacklist
                                } else {
                                    dir.auth_status == DirectoryAuthStatus::Authorized && !dir.is_blacklist
                                };
                                
                                if should_monitor {
                                    authorized_folders.push(dir.clone());
                                }
                            }
                            
                            *monitored_dirs_lock = authorized_folders;
                            
                            println!("[CONFIG_FETCH] Updated monitored_dirs with {} entries from /config/all. (Full disk access: {})",
                                monitored_dirs_lock.len(), config_data.full_disk_access);
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

    // 检查路径是否在黑名单内
    fn is_in_blacklist(&self, path: &Path) -> bool {
        let dirs = self.monitored_dirs.lock().unwrap();
        for dir in dirs.iter() {
            if dir.is_blacklist && path.starts_with(&dir.path) {
                return true;
            }
        }
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

        // 创建额外元数据对象
        let mut extra_data = serde_json::Map::new();
        
        // 根据扩展名进行初步分类
        if let Some(ext) = &metadata.extension {
            // 这里可以添加静态规则或从API获取规则
            // Replace hardcoded logic with rules from config.file_extension_maps
            let mut applied_category = false;
            for ext_map_rule in &config.file_extension_maps {
                if ext_map_rule.extension == *ext {
                    metadata.category_id = Some(ext_map_rule.category_id);
                    // Find category name for extra_data (optional, but nice for debugging)
                    let category_name = config.file_categories.iter()
                        .find(|cat| cat.id == ext_map_rule.category_id)
                        .map_or("unknown_category_id".to_string(), |cat| cat.name.clone());
                    extra_data.insert("file_type_from_ext_map".to_string(), serde_json::Value::String(category_name));
                    applied_category = true;
                    println!("[APPLY_RULES] Applied category {} from extension map for ext: {}", ext_map_rule.category_id, ext);
                    break; // Assuming first match is enough, or consider priority
                }
            }

            if !applied_category {
                 // Fallback to old hardcoded logic if no extension map rule matched (optional)
                let category_id = match ext.as_str() {
                    "jpg" | "jpeg" | "png" | "gif" | "bmp" | "webp" => 1, // 图片
                    "doc" | "docx" | "pdf" | "txt" | "md" | "rtf" => 2,   // 文档
                    "mp3" | "wav" | "flac" | "ogg" | "mp4" | "mov" => 3,  // 媒体
                    "zip" | "rar" | "7z" | "gz" | "tar" => 4,             // 压缩文件
                    "exe" | "dmg" | "app" | "msi" => 5,                   // 可执行文件
                    "js" | "ts" | "py" | "rs" | "go" | "java" | "c" | "cpp" | "h" => 6, // 代码
                    _ => 0, // 未知类型
                };
                if category_id > 0 {
                    metadata.category_id = Some(category_id);
                    extra_data.insert("file_type_fallback".to_string(), serde_json::Value::String(match category_id {
                        1 => "image".to_string(),
                        2 => "document".to_string(),
                        3 => "media".to_string(),
                        4 => "archive".to_string(),
                        5 => "executable".to_string(),
                        6 => "code".to_string(),
                        _ => "unknown".to_string(),
                    }));
                     println!("[APPLY_RULES] Applied category {} from fallback for ext: {}", category_id, ext);
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
            // Placeholder for actual pattern matching logic (regex, glob, keyword)
            // This will be expanded in the next step.
            let mut matched_this_rule = false;
            match filter_rule.rule_type {
                RuleTypeRust::Filename => {
                    if filter_rule.pattern_type == "keyword" && filename.contains(&filter_rule.pattern) {
                        matched_this_rule = true;
                         println!("[APPLY_RULES] Matched filename keyword rule '{}' for: {}", filter_rule.name, filename);
                    }
                    // Add regex/glob matching here if pattern_type dictates
                }
                RuleTypeRust::Extension => {
                    if let Some(ext_val) = &metadata.extension {
                        if filter_rule.pattern_type == "keyword" && *ext_val == filter_rule.pattern {
                             matched_this_rule = true;
                             println!("[APPLY_RULES] Matched extension rule '{}' for: {}", filter_rule.name, ext_val);
                        }
                        // Add regex/glob matching here
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


        // Fallback for screenshot/temp/draft if not covered by general FileFilterRules
        // This can be removed if FileFilterRules are comprehensive
        if filename.contains("screenshot") || filename.contains("screen shot") || filename.contains("截图") || filename.starts_with("截屏") {
            if !rule_matches.iter().any(|r| r.to_lowercase().contains("screenshot")) { // Avoid duplicate if a rule already tagged it
                rule_matches.push("screenshot_fallback".to_string());
                if metadata.tags.is_none() { metadata.tags = Some(Vec::new()); }
                if let Some(tags) = &mut metadata.tags { tags.push("screenshot".to_string()); }
                extra_data.insert("is_screenshot_fallback".to_string(), serde_json::Value::Bool(true));
            }
        }
        // ... (similar for temporary and draft, or remove if rules handle them) ...

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
        println!("[TEST_DEBUG] send_batch_metadata_to_api: Sending batch of {} items to URL: {}", metadata_batch.len(), url);

        // 构建请求体，包含文件元数据和自动创建任务标志
        let mut request_body = serde_json::Map::new();
        request_body.insert(
            "data_list".to_string(), // Changed key from "metadata_batch" to "data_list"
            serde_json::to_value(&metadata_batch).map_err(|e| format!("Failed to serialize metadata batch: {}", e))?
        );
        request_body.insert("auto_create_tasks".to_string(), serde_json::Value::Bool(true));
        
        // 打印 request_body 的键
        let keys: Vec<String> = request_body.keys().cloned().collect();
        println!("[TEST_DEBUG] send_batch_metadata_to_api: Request body for batch keys: {:?}", keys);

        match self.client.post(&url).json(&request_body).send().await {
            Ok(response) => {
                let status = response.status();
                println!("[TEST_DEBUG] send_batch_metadata_to_api: Received response with status: {}", status);

                if status.is_success() {
                    let response_text = response.text().await.unwrap_or_else(|_| "Failed to read response text".to_string());
                    match serde_json::from_str::<ApiResponse>(&response_text) {
                        Ok(api_resp) => {
                             println!("[TEST_DEBUG] send_batch_metadata_to_api: Successfully parsed API response: {:?}", api_resp);
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

    // 告诉API创建分析任务
    async fn notify_api_for_analysis(&self) -> Result<bool, String> {
        let url = format!(
            "http://{}:{}/insights/generate", // Corrected endpoint
            self.api_host, self.api_port
        );
        println!("[TEST_DEBUG] notify_api_for_analysis: Notifying API for analysis at URL: {}", url);

        let _ = HashMap::from([
            ("task_name", "file_analysis"), // 这些值可以根据你的实际需求调整
            ("task_type", "insight"), // This matches the PRD and Python logic for insights
            ("priority", "medium"),
        ]);
        
        let mut data_payload = HashMap::new();
        data_payload.insert("task_name", serde_json::Value::String("file_analysis".to_string()));
        data_payload.insert("priority", serde_json::Value::String("medium".to_string()));

        let request_body = serde_json::json!({ "data": data_payload });

        println!("[TEST_DEBUG] notify_api_for_analysis: Task request body: {:?}", request_body);


        match self.client.post(&url).json(&request_body).send().await {
            Ok(response) => {
                let status = response.status();
                let response_text = response.text().await.unwrap_or_else(|_| "Failed to read response text".to_string());
                println!("[TEST_DEBUG] notify_api_for_analysis: Received response with status: {}. Body snippet: {}", status, &response_text[..std::cmp::min(response_text.len(), 200)]);
                if status.is_success() {
                    println!("[TEST_DEBUG] notify_api_for_analysis: API notified successfully.");
                    Ok(true)
                } else {
                    eprintln!("[TEST_DEBUG] notify_api_for_analysis: API notification failed with status: {}. Body snippet: {}", status, &response_text[..std::cmp::min(response_text.len(), 200)]);
                    Ok(false) 
                }
            }
            Err(e) => {
                eprintln!("[TEST_DEBUG] notify_api_for_analysis: Failed to notify API for analysis: {}", e);
                Err(format!("Failed to notify API for analysis: {}", e))
            }
        }
    }

    // 处理文件变化事件
    async fn process_file_event(&self, path: PathBuf, event_kind: notify::EventKind) -> Option<FileMetadata> {
        println!("[PROCESS_EVENT] Processing event {:?} for path {:?}", event_kind, path);

        // Check config cache early
        if self.config_cache.lock().unwrap().is_none() {
            eprintln!("[PROCESS_EVENT] Config cache is not populated. Cannot process file event for {:?}. Attempting to fetch.", path);
            if self.fetch_and_store_all_config().await.is_err() {
                eprintln!("[PROCESS_EVENT] Failed to fetch config. Aborting processing for {:?}", path);
                return None;
            }
             println!("[PROCESS_EVENT] Config fetched successfully. Retrying processing for {:?}", path);
        }

        // 忽略黑名单中的路径 - needs to access monitored_dirs from config_cache or self.monitored_dirs
        // Let's assume self.monitored_dirs is kept up-to-date by fetch_and_store_all_config
        if self.is_in_blacklist(&path) {
            println!("[PROCESS_EVENT] Path {:?} is in blacklist. Ignoring.", path);
            return None;
        }

        // 忽略不存在或无法访问的文件
        if !path.exists() {
            println!("[TEST_DEBUG] process_file_event: Path {:?} does not exist or is inaccessible. Ignoring.", path);
            return None;
        }
        println!("[TEST_DEBUG] process_file_event: Path {:?} exists.", path);


        // 获取基本文件元数据
        println!("[TEST_DEBUG] process_file_event: Getting metadata for path {:?}", path);
        let mut metadata = match Self::get_file_metadata(&path).await {
            Some(meta) => {
                println!("[TEST_DEBUG] process_file_event: Initial metadata for {:?}: {:?}", path, meta);
                meta
            }
            None => {
                println!("[TEST_DEBUG] process_file_event: Failed to get metadata for path {:?}. Ignoring.", path);
                return None;
            }
        };

        // 仅为文件计算哈希，不为目录计算
        if !metadata.is_dir {
            println!("[TEST_DEBUG] process_file_event: Calculating hash for file {:?}", path);
            metadata.hash_value = Self::calculate_simple_hash(&path, 4096).await;
            println!("[TEST_DEBUG] process_file_event: Calculated hash for {:?}: {:?}", path, metadata.hash_value.as_deref().unwrap_or("N/A"));
        } else {
            println!("[TEST_DEBUG] process_file_event: Path {:?} is a directory, skipping hash calculation.", path);
        }
        
        println!("[TEST_DEBUG] process_file_event: Metadata BEFORE applying rules for {:?}: {:?}", path, metadata);

        // 应用初步规则进行分类
        println!("[TEST_DEBUG] process_file_event: Applying initial rules for metadata of {:?}", path);
        self.apply_initial_rules(&mut metadata).await; 
        
        // Check if the file was marked for exclusion by rules
        if let Some(extra_meta) = &metadata.extra_metadata {
            if extra_meta.get("excluded_by_rule_id").is_some() {
                 println!("[PROCESS_EVENT] File {:?} was excluded by rule: {:?}. Not processing further.", metadata.file_path, extra_meta.get("excluded_by_rule_name"));
                // Depending on design, we might still want to return the metadata for logging, 
                // but batch_processor will skip sending it.
                // For now, let's return it so it can be logged by the caller if needed,
                // but it won't be sent to the API.
                // Or, to strictly prevent further processing: return None;
            }
        }
        
        println!("[TEST_DEBUG] process_file_event: Metadata AFTER applying rules for {:?}: {:?}", path, metadata); // "粗筛"结果

        Some(metadata)
    }

    // 批处理文件元数据发送
    async fn batch_processor(
        &self, 
        mut rx: Receiver<FileMetadata>,
        batch_size: usize,
        batch_interval: Duration
    ) {
        let mut batch = Vec::with_capacity(batch_size);
        let mut last_send = tokio::time::Instant::now();

        loop {
            tokio::select! {
                maybe_metadata = rx.recv() => {
                    if let Some(metadata) = maybe_metadata {
                        // Check if file was marked for exclusion by apply_initial_rules
                        if let Some(extra) = &metadata.extra_metadata {
                            if extra.get("excluded_by_rule_id").is_some() {
                                println!("[BATCH_PROC] Skipping excluded file: {:?} (Rule: {:?})", metadata.file_path, extra.get("excluded_by_rule_name"));
                                continue; // Skip adding to batch
                            }
                        }
                        batch.push(metadata);
                        if batch.len() >= batch_size {
                            println!("[BATCH_PROC] Batch size reached ({} items). Logging batch.", batch.len());
                            for item in &batch {
                                println!("[BATCH_CONTENT] {:?}", item);
                            }
                            // TEMPORARILY DISABLED SENDING TO API
                            // if let Err(e) = self.send_batch_metadata_to_api(batch.clone()).await {
                            //     eprintln!("[BATCH_PROC] Error sending batch: {}", e);
                            // }
                            batch.clear();
                            last_send = tokio::time::Instant::now();
                        }
                    } else {
                        // Channel closed
                        if !batch.is_empty() {
                            println!("[BATCH_PROC] Channel closed. Logging remaining batch ({} items).", batch.len());
                             for item in &batch {
                                println!("[BATCH_CONTENT] {:?}", item);
                            }
                            // TEMPORARILY DISABLED SENDING TO API
                            // if let Err(e) = self.send_batch_metadata_to_api(batch.clone()).await {
                            //     eprintln!("[BATCH_PROC] Error sending final batch: {}", e);
                            // }
                            batch.clear();
                        }
                        println!("[BATCH_PROC] Metadata channel closed. Exiting batch processor.");
                        return;
                    }
                },
                _ = sleep(batch_interval) => {
                    if !batch.is_empty() && tokio::time::Instant::now().duration_since(last_send) >= batch_interval {
                        println!("[BATCH_PROC] Batch interval reached. Logging batch ({} items).", batch.len());
                        for item in &batch {
                            println!("[BATCH_CONTENT] {:?}", item);
                        }
                        // TEMPORARILY DISABLED SENDING TO API
                        // if let Err(e) = self.send_batch_metadata_to_api(batch.clone()).await {
                        //     eprintln!("[BATCH_PROC] Error sending batch due to interval: {}", e);
                        // }
                        batch.clear();
                        last_send = tokio::time::Instant::now();
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
        while let Some((path, kind)) = rx.recv().await {
            if let Some(metadata) = self.process_file_event(path, kind).await {
                let _ = tx_metadata.send(metadata).await;
            }
        }
    }

    // 执行初始扫描
    async fn perform_initial_scan(&self, tx_metadata: &Sender<FileMetadata>) -> Result<(), String> {
        let directories = self.monitored_dirs.lock().unwrap().clone();
        
        for dir in directories {
            if (dir.auth_status != DirectoryAuthStatus::Authorized) || dir.is_blacklist {
                continue;
            }
            
            let path = PathBuf::from(&dir.path);
            if !path.exists() {
                continue;
            }

            // 使用 WalkDir 执行递归扫描
            let walker = WalkDir::new(&path).into_iter();
            for entry in walker.filter_map(Result::ok) {
                let entry_path = entry.path().to_path_buf();
                
                // 忽略黑名单中的路径
                if self.is_in_blacklist(&entry_path) {
                    continue;
                }
                
                // 处理文件事件
                if let Some(metadata) = self.process_file_event(
                    entry_path,
                    notify::EventKind::Create(notify::event::CreateKind::Any),
                ).await {
                    let _ = tx_metadata.send(metadata).await;
                }
            }
        }
        
        Ok(())
    }

    // 启动文件夹监控
    pub async fn start_monitoring(&mut self) -> Result<(), String> {
        // 更新受监控的目录列表和所有配置
        println!("[START_MONITORING] Attempting to fetch all configurations...");
        self.fetch_and_store_all_config().await.map_err(|e| {
            eprintln!("[START_MONITORING] Critical error: Failed to fetch initial configuration: {}", e);
            format!("Failed to fetch initial configuration: {}", e)
        })?;
        println!("[START_MONITORING] Initial configuration fetched successfully.");

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
            dirs_guard.iter()
                .filter(|d| {
                    // 如果有完全磁盘访问权限，只过滤黑名单文件夹
                    // 否则，需要同时判断授权状态和黑名单状态
                    if full_disk_access {
                        !d.is_blacklist
                    } else {
                        d.auth_status == DirectoryAuthStatus::Authorized && !d.is_blacklist
                    }
                })
                .cloned()
                .collect::<Vec<_>>()
        };
        
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
            
            // 初始扫描后通知API
            sleep(Duration::from_secs(5)).await; // 等待批处理完成
            if let Err(e) = self_clone_for_scan.notify_api_for_analysis().await {
                eprintln!("Failed to notify API after initial scan: {}", e);
            }
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
        println!("[TEST_DEBUG] watch_directory: Starting for path: {}", dir_path);

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
        
        println!("[TEST_DEBUG] watch_directory: Watcher created for path: {}", dir_path);
        
        // 开始监控指定目录
        watcher
            .watch(
                Path::new(dir_path),
                RecursiveMode::Recursive,
            )
            .map_err(|e| format!("Failed to watch directory: {}", e))?;
        
        println!("[TEST_DEBUG] watch_directory: Successfully watching path: {}", dir_path);
        
        // 持续处理文件系统事件
        let task_dir_path = dir_path.to_string(); // Clone dir_path for the async task
        tokio::spawn(async move {
            println!("[TEST_DEBUG] watch_directory: Event processing task started for path: {}", task_dir_path);
            while let Some(result) = watcher_rx.recv().await {
                println!("[TEST_DEBUG] watch_directory: Received event result for path {}: {:?}", task_dir_path, result);
                match result {
                    Ok(event) => {
                        println!("[TEST_DEBUG] watch_directory: Parsed event for path {}: {:?}", task_dir_path, event);
                        // 筛选我们关心的事件类型
                        match event.kind {
                            notify::EventKind::Create(_) | 
                            notify::EventKind::Modify(_) | 
                            notify::EventKind::Remove(_) => {
                                println!("[TEST_DEBUG] watch_directory: Relevant event kind for path {}: {:?}, paths: {:?}", task_dir_path, event.kind, event.paths);
                                for path_buf in event.paths { // Renamed path to path_buf to avoid conflict
                                    println!("[TEST_DEBUG] watch_directory: Sending path {:?} with kind {:?} to event_tx from watcher for {}", path_buf, event.kind, task_dir_path);
                                    if let Err(e) = event_tx.send((path_buf, event.kind.clone())).await {
                                        eprintln!("[TEST_DEBUG] watch_directory: Failed to send event to event_tx for path {}: {}", task_dir_path, e);
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
            println!("[TEST_DEBUG] watch_directory: Event processing task finished for path: {}", task_dir_path);
        });
        
        Ok(())
    }
}

impl Clone for FileMonitor {
    fn clone(&self) -> Self {
        FileMonitor {
            monitored_dirs: self.monitored_dirs.clone(),
            config_cache: self.config_cache.clone(), // Clone config cache
            api_host: self.api_host.clone(),
            api_port: self.api_port,
            client: self.client.clone(),
            event_tx: None,
            batch_size: self.batch_size,
            batch_interval: self.batch_interval,
        }
    }
}
