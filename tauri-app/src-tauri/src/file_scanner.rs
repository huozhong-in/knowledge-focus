use chrono::{
    // Duration, 
    Local, 
    TimeZone};
use serde::{Deserialize, Serialize};
// use std::collections::HashSet;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{
    command, 
    AppHandle,
    Manager, 
    State,
    Emitter}; // 添加Emitter trait
use walkdir::WalkDir;

use crate::file_monitor::{
    AllConfigurations, 
    FileExtensionMapRust, 
    // MonitoredDirectory, 
    DirectoryAuthStatus}; // Added MonitoredDirectory, DirectoryAuthStatus
use crate::AppState; // Import AppState from lib.rs

// 定义文件信息结构
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileInfo {
    pub file_path: String,
    pub file_name: String,
    pub file_size: u64,
    pub extension: Option<String>,
    pub created_time: Option<String>,
    pub modified_time: String,
    pub category_id: Option<i32>,
}

// 定义时间范围枚举
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TimeRange {
    #[serde(rename = "today")]
    Today,
    #[serde(rename = "last7days")]
    Last7Days,
    #[serde(rename = "last30days")]
    Last30Days,
}

// 定义文件类型枚举
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)] // Added PartialEq
pub enum FileType {
    #[serde(rename = "image")]
    Image,
    #[serde(rename = "audio-video")]
    AudioVideo,
    #[serde(rename = "archive")]
    Archive,
    #[serde(rename = "document")]
    Document,
    #[serde(rename = "all")]
    All,
}

// 获取文件扩展名
fn get_file_extension(file_path: &Path) -> Option<String> {
    file_path
        .extension()
        .and_then(|ext| ext.to_str())
        .map(|ext| ext.to_lowercase())
}

// 检查文件是否隐藏
fn is_hidden_file(path: &Path) -> bool {
    // 先检查文件/目录名本身是否以.开头
    let is_name_hidden = path.file_name()
        .and_then(|name| name.to_str())
        .map(|name| name.starts_with("."))
        .unwrap_or(false);
        
    if is_name_hidden {
        return true;
    }
    
    // 检查路径中是否有任何部分是隐藏目录（以.开头）
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
fn is_macos_bundle_folder(path: &Path) -> bool {
    // 首先处理可能为null的情况
    if path.as_os_str().is_empty() {
        return false;
    }
    
    // 设置常用的bundle扩展名
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
                lowercase_component.ends_with(ext)
            }) {
                return true;
            }
        }
    }
    
    // 3. 如果是目录，检查是否有典型的macOS bundle目录结构
    if path.is_dir() && cfg!(target_os = "macos") {
        let info_plist = path.join("Contents/Info.plist");
        if info_plist.exists() {
            return true;
        }
    }
    
    false
}

// 检查文件是否在macOS bundle内部
fn is_inside_macos_bundle(path: &Path) -> bool {
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

#[derive(Debug, Default)]
struct ScanStats {
    total_discovered: u64,  // 发现的所有文件数
    hidden_filtered: u64,   // 被过滤的隐藏文件数
    extension_filtered: u64, // 被扩展名过滤的文件数
    bundle_filtered: u64,   // 被过滤的bundle文件数
    total_included: u64,    // 最终包含的文件数
}

// 根据文件类型枚举获取对应的分类ID列表
fn get_category_ids_for_file_type(file_type: &FileType) -> Vec<i32> {
    match file_type {
        FileType::Image => vec![2], // Assuming category_id 2 is for Images based on create_default_config
        FileType::AudioVideo => vec![3], // Assuming category_id 3 is for Audio/Video
        FileType::Archive => vec![4], // Assuming category_id 4 is for Archives
        FileType::Document => vec![1], // Assuming category_id 1 is for Documents
        FileType::All => vec![], // All types will not filter by category_id here
    }
}

// 根据扩展名和文件类型检查文件是否匹配
fn is_file_of_type(extension: &Option<String>, file_type: &FileType, extension_maps: &[FileExtensionMapRust]) -> bool {
    if *file_type == FileType::All {
        return true; // No filtering by type if FileType is All
    }

    if let Some(ext) = extension {
        let ext = ext.to_lowercase();
        let target_category_ids = get_category_ids_for_file_type(file_type);
        
        // 检查文件扩展名是否在扩展名映射列表中
        // 只有扩展名在列表中且关联到指定分类ID的文件才会被返回
        let matches = extension_maps.iter().any(|map| {
            map.extension.to_lowercase() == ext && target_category_ids.contains(&map.category_id)
        });
        
        return matches;
    } else {
        false
    }
}

// 检查文件是否在指定的时间范围内
fn is_file_in_time_range(modified_time_secs: u64, time_range: &TimeRange) -> bool {
    let modified_time = match UNIX_EPOCH.checked_add(std::time::Duration::from_secs(modified_time_secs)) {
        Some(time) => time,
        None => return false, // Handle potential overflow
    };

    let now = SystemTime::now();

    match time_range {
        TimeRange::Today => {
            let twenty_four_hours_ago = match now.checked_sub(std::time::Duration::from_secs(24 * 3600)) { // Corrected Duration usage
                 Some(time) => time,
                 None => return false,
            };
            modified_time >= twenty_four_hours_ago
        }
        TimeRange::Last7Days => {
             let seven_days_ago = match now.checked_sub(std::time::Duration::from_secs(7 * 24 * 3600)) { // Corrected Duration usage
                 Some(time) => time,
                 None => return false,
            };
            modified_time >= seven_days_ago
        }
        TimeRange::Last30Days => {
             let thirty_days_ago = match now.checked_sub(std::time::Duration::from_secs(30 * 24 * 3600)) { // Corrected Duration usage
                 Some(time) => time,
                 None => return false,
            };
            modified_time >= thirty_days_ago
        }
    }
}

// 将系统时间转换为ISO格式字符串
fn system_time_to_iso_string(system_time: SystemTime) -> String {
    let duration = match system_time.duration_since(UNIX_EPOCH) {
        Ok(duration) => duration,
        Err(_) => return "".to_string(),
    };

    let seconds = duration.as_secs();
    // Use Local::timestamp_opt for safer conversion
    let datetime = match Local.timestamp_opt(seconds as i64, 0) {
        chrono::LocalResult::Single(dt) => dt,
        _ => Local::now(), // Fallback to current time on error
    };
    datetime.to_rfc3339()
}

// 根据类别ID获取文件扩展名列表 (This function might not be needed in file_scanner anymore)
// fn get_extensions_by_category(
//     category_id: i32,
//     extension_maps: &[FileExtensionMapRust],
// ) -> HashSet<String> {
//     extension_maps
//         .iter()
//         .filter(|map| map.category_id == category_id)
//         .map(|map| map.extension.clone())
//         .collect()
// }

// Tauri命令：扫描指定时间范围内的文件
#[command]
pub async fn scan_files_by_time_range(
    _app_handle: AppHandle,
    time_range: TimeRange,
    app_state: State<'_, AppState>, // Access AppState
) -> Result<Vec<FileInfo>, String> {
    println!("调用 scan_files_by_time_range: {:?}", time_range);

    let config = app_state.get_config().await?; // Use the AppState to get config

    println!("开始扫描文件...");
    let result = scan_files_with_filter(&config, Some(time_range), None).await;
    println!("扫描完成, 文件数量: {}", result.as_ref().map_or(0, |files| files.len()));
    result
}

// Tauri命令：扫描特定类型的文件
#[command]
pub async fn scan_files_by_type(
    _app_handle: AppHandle,
    file_type: FileType,
    app_state: State<'_, AppState>, // Access AppState
) -> Result<Vec<FileInfo>, String> {
    println!("调用 scan_files_by_type: {:?}", file_type);

    let config = app_state.get_config().await?; // Use the AppState to get config

    println!("开始扫描文件...");
    let result = scan_files_with_filter(&config, None, Some(file_type)).await;
    println!("扫描完成, 文件数量: {}", result.as_ref().map_or(0, |files| files.len()));
    result
}

// 启动后端全量扫描工作，必须在前端权限检查通过后才调用
#[command]
pub async fn start_backend_scanning(
    app_handle: tauri::AppHandle,
    app_state: tauri::State<'_, AppState>,
) -> Result<bool, String> {
    println!("[扫描] 启动后端全量扫描工作");
    println!("[扫描] 【重要提示】此函数只能在前端确认用户已授予完全磁盘访问权限后调用");
    println!("[扫描] 正确流程：IntroDialog检查权限通过 -> 调用start_backend_scanning -> 进入应用");
    
    // 获取文件监控器
    let file_monitor_option = {
        let guard = app_state.file_monitor.lock().unwrap();
        guard.clone()
    };
    
    // 如果文件监控器不存在，返回错误
    let file_monitor = match file_monitor_option {
        Some(monitor) => monitor,
        None => {
            eprintln!("[扫描] 文件监控器未初始化");
            return Err("文件监控器未初始化".to_string());
        }
    };
    
    // 通过FileMonitor获取配置而不是AppState
    // 这里先刷新配置以确保获取到最新的监控目录列表
    if let Err(e) = file_monitor.refresh_all_configurations().await {
        eprintln!("[扫描] 刷新配置失败: {}", e);
        return Err(format!("无法刷新配置: {}", e));
    }
    
    // 检查是否有监控目录
    let monitored_dirs = file_monitor.get_monitored_directories();
    if monitored_dirs.is_empty() {
        println!("[扫描] 没有监控目录，无需启动扫描");
        return Ok(false);
    }
    
    println!("[扫描] 找到 {} 个监控目录，准备启动扫描", monitored_dirs.len());
    
    // 发送事件通知前端扫描开始
    if let Err(e) = app_handle.emit("scan_started", ()) {
        eprintln!("[扫描] 发送扫描开始事件失败: {:?}", e);
    }
    
    // 启动后台扫描任务
    let app_handle_clone = app_handle.clone();
    let file_monitor_clone = file_monitor.clone();
    tokio::spawn(async move {
        println!("[扫描] 开始执行全量扫描");
        
        // 设置扫描完成标志为false
        let app_state_handle = app_handle_clone.state::<AppState>();
        {
            let mut scan_completed = app_state_handle.initial_scan_completed.lock().unwrap();
            *scan_completed = false;
        }
        
        // 执行初始扫描（完整的监控设置和扫描）
        let mut fm = file_monitor_clone.clone();
        match fm.start_monitoring_setup_and_initial_scan().await {
            Ok(_) => {
                println!("[扫描] 初始扫描和监控设置完成");
                
                // 更新扫描完成标志
                {
                    let mut scan_completed = app_state_handle.initial_scan_completed.lock().unwrap();
                    *scan_completed = true;
                }
                
                // 更新AppState中的配置
                if let Some(config) = fm.get_configurations() {
                    app_state_handle.update_config(config);
                    println!("[扫描] 已更新AppState配置");
                }
                
                // 发送事件通知前端扫描完成
                if let Err(e) = app_handle_clone.emit("scan_completed", true) {
                    eprintln!("[扫描] 发送扫描完成事件失败: {:?}", e);
                }
                
                // 启动防抖动监控器
                let debounced_monitor_state = app_state_handle.debounced_file_monitor.clone();
                if let Some(mut debounced_monitor) = {
                    let guard = debounced_monitor_state.lock().unwrap();
                    guard.clone()
                } {
                    let directories: Vec<String> = fm.get_monitored_directories()
                        .into_iter()
                        .map(|dir| dir.path)
                        .collect();
                    
                    if let Err(e) = debounced_monitor.start_monitoring(directories, std::time::Duration::from_millis(2_000)).await {
                        eprintln!("[扫描] 启动防抖动监控失败: {}", e);
                    } else {
                        println!("[扫描] 防抖动监控已启动");
                    }
                }
            },
            Err(e) => {
                eprintln!("[扫描] 初始扫描失败: {}", e);
                
                // 发送事件通知前端扫描失败
                if let Err(emit_err) = app_handle_clone.emit("scan_error", format!("扫描失败: {}", e)) {
                    eprintln!("[扫描] 发送扫描错误事件失败: {:?}", emit_err);
                }
            }
        }
    });
    
    Ok(true)
}

// 新增：访问敏感文件夹前的权限确认
// 在start_monitoring_setup_and_initial_scan方法中，访问敏感文件夹前调用此函数
// 如果没有授权，将不会继续访问（由于权限控制移至前端，此函数仅作为提示）
fn ensure_permission_for_sensitive_folder() -> bool {
    println!("[权限] 访问敏感文件夹前检查权限 - 提示：权限验证已移至前端");
    
    #[cfg(target_os = "macos")]
    {
        println!("[权限] macOS系统，假设前端已通过tauri-plugin-macos-permissions-api验证权限");
        // 返回true，因为实际权限检查已在前端完成
        // 如果前端未处理权限，此处可能会导致无权限访问
        true
    }
    
    #[cfg(not(target_os = "macos"))]
    {
        println!("[权限] 非macOS系统，假设已有权限");
        true
    }
}

// 帮助跟踪权限状态的函数
fn log_permission_check(action: &str, path: &Path) {
    #[cfg(target_os = "macos")]
    {
        println!("[权限] {} 访问路径: {} - 提示：此访问应当在前端权限验证通过后进行", 
            action, path.display());
    }
    
    #[cfg(not(target_os = "macos"))]
    {
        println!("[权限] {} 访问路径: {}", action, path.display());
    }
}

// 内部函数：使用指定过滤条件扫描文件
async fn scan_files_with_filter(
    config: &AllConfigurations,
    time_range: Option<TimeRange>,
    file_type: Option<FileType>,
) -> Result<Vec<FileInfo>, String> {
    let mut files = Vec::new();
    let extension_maps = &config.file_extension_maps;

    // 检查扩展名映射是否为空
    if extension_maps.is_empty() {
        return Err("配置中未找到文件扩展名映射".to_string());
    }

    // 创建有效扩展名哈希集，用于快速查找
    let mut valid_extensions = std::collections::HashSet::new();
    for map in extension_maps {
        valid_extensions.insert(map.extension.to_lowercase());
    }

    // 统计扫描和过滤信息
    let mut stats = ScanStats {
        total_discovered: 0,
        hidden_filtered: 0,
        extension_filtered: 0,
        bundle_filtered: 0,
        total_included: 0,
    };

    for monitored_dir in &config.monitored_folders {
        // Only scan authorized and non-blacklisted directories
        let should_scan = if config.full_disk_access {
            !monitored_dir.is_blacklist
        } else {
            monitored_dir.auth_status == DirectoryAuthStatus::Authorized && !monitored_dir.is_blacklist
        };

        if !should_scan {
            println!("[SCAN] 跳过目录 {:?} (auth_status: {:?}, is_blacklist: {})", monitored_dir.path, monitored_dir.auth_status, monitored_dir.is_blacklist);
            continue;
        }

        let path = Path::new(&monitored_dir.path);
        
        // 记录权限敏感目录的访问
        log_permission_check("开始扫描", path);
        
        // 确保前端已经验证权限
        if path.to_string_lossy().contains("/Users") {
            println!("[SCAN] 访问用户敏感目录: {:?} - 应该已经通过前端权限检查", path);
        }
        
        if !path.exists() || !path.is_dir() {
            continue;
        }

        for entry in WalkDir::new(path)
            .follow_links(true)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            stats.total_discovered += 1;

            // 首先，最高优先级过滤 - 隐藏文件
            if is_hidden_file(entry.path()) {
                stats.hidden_filtered += 1;
                continue;
            }
            
            // 检查是否为macOS bundle或位于bundle内部（高优先级过滤）
            if is_macos_bundle_folder(entry.path()) {
                stats.bundle_filtered += 1;
                continue;
            }
            
            if is_inside_macos_bundle(entry.path()) {
                stats.bundle_filtered += 1;
                continue;
            }
            
            // 路径级别过滤 - 检查路径中是否包含需要过滤的目录
            let path = entry.path();
            let mut should_skip = false;
            
            for component in path.components() {
                if let std::path::Component::Normal(name) = component {
                    if let Some(name_str) = name.to_str() {
                        // 过滤掉路径中包含以点开头的目录（隐藏目录）
                        if name_str.starts_with(".") && name_str != "." && name_str != ".." {
                            stats.hidden_filtered += 1;
                            should_skip = true;
                            break;
                        }
                        // 过滤掉Cache目录 (大小写不敏感)
                        if name_str.eq_ignore_ascii_case("Cache") {
                            should_skip = true;
                            break;
                        }
                    }
                }
            }
            
            if should_skip {
                continue;
            }

            // 只处理文件（不处理目录）
            if !entry.file_type().is_file() {
                continue;
            }

            let file_path = entry.path();
            let extension = get_file_extension(file_path);
            
            // 白名单扩展名过滤：只处理有扩展名且扩展名在配置白名单中的文件
            if let Some(ref ext) = extension {
                let ext_lower = ext.to_lowercase();
                if !valid_extensions.contains(&ext_lower) {
                    // 扩展名不在白名单中，跳过并记录
                    stats.extension_filtered += 1;
                    println!("[SCAN] 跳过非白名单扩展名文件: {} (扩展名: {})", file_path.display(), ext_lower);
                    continue;
                }
            } else if file_type != Some(FileType::All) {
                // 没有扩展名且不是查找所有文件类型，跳过
                stats.extension_filtered += 1;
                println!("[SCAN] 跳过无扩展名文件: {}", file_path.display());
                continue;
            }

            // 应用文件类型过滤器
            if let Some(ref ft) = file_type {
                if !is_file_of_type(&extension, ft, extension_maps) {
                    println!("[SCAN] 跳过不匹配类型过滤器的文件: {} (期望类型: {:?})", file_path.display(), ft);
                    continue;
                }
            }

            // 获取文件元数据
            let metadata = match std::fs::metadata(file_path) {
                Ok(meta) => meta,
                Err(e) => {
                    println!("[SCAN] 无法获取文件元数据: {} (错误: {})", file_path.display(), e);
                    continue;
                }
            };

            // 获取修改时间
            let modified_time = match metadata.modified() {
                Ok(time) => time,
                Err(_) => continue,
            };

            let modified_time_secs = match modified_time.duration_since(UNIX_EPOCH) {
                Ok(duration) => duration.as_secs(),
                Err(_) => continue,
            };

            // 应用时间范围过滤器
            if let Some(ref tr) = time_range {
                if !is_file_in_time_range(modified_time_secs, tr) {
                    println!("[SCAN] 跳过不在时间范围内的文件: {} (范围: {:?})", file_path.display(), tr);
                    continue;
                }
            }

            // 获取创建时间
            let created_time = metadata
                .created()
                .ok()
                .map(|time| system_time_to_iso_string(time));

            // 计算文件大小
            let file_size = metadata.len();

            // 获取文件名
            let file_name = file_path
                .file_name()
                .and_then(|name| name.to_str())
                .unwrap_or("")
                .to_string();

            // 根据扩展名匹配分类ID
            let category_id = extension.as_ref().and_then(|ext| {
                extension_maps
                    .iter()
                    .find(|map| map.extension.to_lowercase() == ext.to_lowercase())
                    .map(|map| map.category_id)
            });

            // 文件通过了所有过滤器，添加到结果列表
            files.push(FileInfo {
                file_path: file_path.to_string_lossy().into_owned(),
                file_name,
                file_size,
                extension,
                created_time,
                modified_time: system_time_to_iso_string(modified_time),
                category_id,
            });
            
            stats.total_included += 1;
            
            // 返回前500个文件
            if files.len() >= 500 {
                println!("[SCAN] 已达到500个文件的限制，停止扫描");
                break;
            }
        }
    }

    // 打印扫描统计信息
    println!("[SCAN] 扫描统计: 发现文件总数: {}, 包含文件数: {}, 被过滤文件数: {} (隐藏: {}, 扩展名: {}, Bundle: {})", 
        stats.total_discovered, 
        stats.total_included,
        stats.hidden_filtered + stats.extension_filtered + stats.bundle_filtered,
        stats.hidden_filtered,
        stats.extension_filtered,
        stats.bundle_filtered
    );

    Ok(files)
}

// 创建默认配置，当AppState不可用时使用
// fn create_default_config() -> AllConfigurations {
//     use std::env;

//     // Get user home directory
//     let home_dir = env::var("HOME").unwrap_or_else(|_| "/".to_string());
//     let downloads_dir = format!("{}/Downloads", home_dir);
//     let documents_dir = format!("{}/Documents", home_dir);
//     let desktop_dir = format!("{}/Desktop", home_dir);

//     // Create default monitored directories list
//     let monitored_folders = vec![
//         MonitoredDirectory {
//             id: Some(1),
//             path: downloads_dir,
//             alias: Some("下载".to_string()),
//             is_blacklist: false,
//             auth_status: DirectoryAuthStatus::Authorized,
//             created_at: Some("2023-01-01T00:00:00Z".to_string()),
//             updated_at: Some("2023-01-01T00:00:00Z".to_string()),
//         },
//         MonitoredDirectory {
//             id: Some(2),
//             path: documents_dir,
//             alias: Some("文档".to_string()),
//             is_blacklist: false,
//             auth_status: DirectoryAuthStatus::Authorized,
//             created_at: Some("2023-01-01T00:00:00Z".to_string()),
//             updated_at: Some("2023-01-01T00:00:00Z".to_string()),
//         },
//         MonitoredDirectory {
//             id: Some(3),
//             path: desktop_dir,
//             alias: Some("桌面".to_string()),
//             is_blacklist: false,
//             auth_status: DirectoryAuthStatus::Authorized,
//             created_at: Some("2023-01-01T00:00:00Z".to_string()),
//             updated_at: Some("2023-01-01T00:00:00Z".to_string()),
//         },
//     ];

//     // Create default file categories
//     let file_categories = vec![
//         crate::file_monitor::FileCategoryRust {
//             id: 1,
//             name: "文档".to_string(),
//             description: Some("文档文件".to_string()),
//             icon: Some("📄".to_string()),
//         },
//         crate::file_monitor::FileCategoryRust {
//             id: 2,
//             name: "图片".to_string(),
//             description: Some("图片文件".to_string()),
//             icon: Some("🖼️".to_string()),
//         },
//         crate::file_monitor::FileCategoryRust {
//             id: 3,
//             name: "音视频".to_string(),
//             description: Some("音频和视频文件".to_string()),
//             icon: Some("🎬".to_string()),
//         },
//         crate::file_monitor::FileCategoryRust {
//             id: 4,
//             name: "压缩包".to_string(),
//             description: Some("压缩文件".to_string()),
//             icon: Some("🗃️".to_string()),
//         },
//     ];

//     // Create default file extension maps
//     let file_extension_maps = vec![
//         FileExtensionMapRust {
//             id: 1,
//             extension: "pdf".to_string(),
//             category_id: 1,
//             description: Some("PDF文档".to_string()),
//             priority: crate::file_monitor::RulePriorityRust::Medium,
//         },
//         FileExtensionMapRust {
//             id: 2,
//             extension: "doc".to_string(),
//             category_id: 1,
//             description: Some("Word文档".to_string()),
//             priority: crate::file_monitor::RulePriorityRust::Medium,
//         },
//         FileExtensionMapRust {
//             id: 3,
//             extension: "docx".to_string(),
//             category_id: 1,
//             description: Some("Word文档".to_string()),
//             priority: crate::file_monitor::RulePriorityRust::Medium,
//         },
//         FileExtensionMapRust {
//             id: 4,
//             extension: "jpg".to_string(),
//             category_id: 2,
//             description: Some("JPG图片".to_string()),
//             priority: crate::file_monitor::RulePriorityRust::Medium,
//         },
//         FileExtensionMapRust {
//             id: 5,
//             extension: "png".to_string(),
//             category_id: 2,
//             description: Some("PNG图片".to_string()),
//             priority: crate::file_monitor::RulePriorityRust::Medium,
//         },
//         FileExtensionMapRust {
//             id: 6,
//             extension: "mp3".to_string(),
//             category_id: 3,
//             description: Some("MP3音频".to_string()),
//             priority: crate::file_monitor::RulePriorityRust::Medium,
//         },
//         FileExtensionMapRust {
//             id: 7,
//             extension: "mp4".to_string(),
//             category_id: 3,
//             description: Some("MP4视频".to_string()),
//             priority: crate::file_monitor::RulePriorityRust::Medium,
//         },
//         FileExtensionMapRust {
//             id: 8,
//             extension: "zip".to_string(),
//             category_id: 4,
//             description: Some("ZIP压缩包".to_string()),
//             priority: crate::file_monitor::RulePriorityRust::Medium,
//         },
//     ];

//     // Default project recognition rules
//     let project_recognition_rules = vec![];

//     // Build default AllConfigurations
//     AllConfigurations {
//         file_categories,
//         file_filter_rules: vec![],
//         file_extension_maps,
//         project_recognition_rules,
//         monitored_folders,
//         full_disk_access: false,
//     }
// }
