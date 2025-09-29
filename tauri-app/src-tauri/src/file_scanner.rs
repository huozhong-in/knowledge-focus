//! # 文件处理引擎 (File Processing Engine)
//!
//! 该模块负责具体的文件操作和处理逻辑，包括：
//! - 文件发现和扫描
//! - 文件过滤和分类（按扩展名、类型、时间范围）
//! - macOS Bundle识别和处理
//! - 文件元数据提取和结构化
//! - Tauri命令接口（供前端调用）
//!
//! 注意：尽管模块名为"scanner"，但它实际上是整个文件处理的核心引擎，
//! 被file_monitor模块调用来执行具体的文件操作任务。

use chrono::{
    // Duration,
    Local,
    TimeZone,
};
use serde::{Deserialize, Serialize};
// use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{command, AppHandle, Emitter, Manager, State}; // 添加Emitter trait
use walkdir::WalkDir;

use crate::file_monitor::{AllConfigurations, FileExtensionMapRust};
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
    let is_name_hidden = path
        .file_name()
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
        if fallback_bundle_extensions
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
            if fallback_bundle_extensions
                .iter()
                .any(|ext| lowercase_component.ends_with(ext))
            {
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

// 检查文件是否在macOS bundle内部，如果是则返回bundle路径
fn is_inside_macos_bundle(path: &Path) -> Option<PathBuf> {
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

// Bundle处理相关函数 - 基于重构需求

// 检查目录是否为macOS Bundle（方法1：扩展名预筛选）
fn has_bundle_extension(path: &Path, bundle_extensions: &[String]) -> bool {
    if let Some(extension) = path.extension().and_then(|ext| ext.to_str()) {
        let ext_with_dot = format!(".{}", extension.to_lowercase());
        bundle_extensions
            .iter()
            .any(|bundle_ext| bundle_ext.to_lowercase() == ext_with_dot)
    } else {
        false
    }
}

// 检查Bundle结构（方法2：Contents/Info.plist确认）
fn has_bundle_structure(path: &Path) -> bool {
    if !path.is_dir() {
        return false;
    }

    let info_plist_path = path.join("Contents").join("Info.plist");
    info_plist_path.exists()
}

// 组合方法：识别macOS Bundle（方法1+2）
fn is_macos_bundle(path: &Path, bundle_extensions: &[String]) -> bool {
    // 首先检查扩展名（快速预筛选）
    if !has_bundle_extension(path, bundle_extensions) {
        return false;
    }

    // 然后确认内部结构（确保真正是Bundle）
    has_bundle_structure(path)
}

// 检查给定路径是否在任何Bundle内部，如果是则返回最外层Bundle路径
fn find_containing_bundle(path: &Path, bundle_extensions: &[String]) -> Option<PathBuf> {
    let mut current_path = path;
    let mut bundle_path: Option<PathBuf> = None;

    // 从当前路径向上遍历，寻找Bundle
    while let Some(parent) = current_path.parent() {
        if is_macos_bundle(parent, bundle_extensions) {
            // 继续向上查找，确保找到最外层的Bundle
            bundle_path = Some(parent.to_path_buf());
        }
        current_path = parent;
    }

    bundle_path
}

#[derive(Debug, Default)]
struct ScanStats {
    total_discovered: u64,   // 发现的所有文件数
    hidden_filtered: u64,    // 被过滤的隐藏文件数
    extension_filtered: u64, // 被扩展名过滤的文件数
    bundle_filtered: u64,    // 被过滤的bundle文件数
    total_included: u64,     // 最终包含的文件数
}

// 根据文件类型枚举获取对应的分类ID列表
fn get_category_ids_for_file_type(file_type: &FileType) -> Vec<i32> {
    match file_type {
        FileType::Image => vec![2], // Assuming category_id 2 is for Images based on create_default_config
        FileType::AudioVideo => vec![3], // Assuming category_id 3 is for Audio/Video
        FileType::Archive => vec![4], // Assuming category_id 4 is for Archives
        FileType::Document => vec![1], // Assuming category_id 1 is for Documents
        FileType::All => vec![],    // All types will not filter by category_id here
    }
}

// 根据扩展名和文件类型检查文件是否匹配
fn is_file_of_type(
    extension: &Option<String>,
    file_type: &FileType,
    extension_maps: &[FileExtensionMapRust],
) -> bool {
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
    let modified_time =
        match UNIX_EPOCH.checked_add(std::time::Duration::from_secs(modified_time_secs)) {
            Some(time) => time,
            None => return false, // Handle potential overflow
        };

    let now = SystemTime::now();

    match time_range {
        TimeRange::Today => {
            let twenty_four_hours_ago =
                match now.checked_sub(std::time::Duration::from_secs(24 * 3600)) {
                    // Corrected Duration usage
                    Some(time) => time,
                    None => return false,
                };
            modified_time >= twenty_four_hours_ago
        }
        TimeRange::Last7Days => {
            let seven_days_ago =
                match now.checked_sub(std::time::Duration::from_secs(7 * 24 * 3600)) {
                    // Corrected Duration usage
                    Some(time) => time,
                    None => return false,
                };
            modified_time >= seven_days_ago
        }
        TimeRange::Last30Days => {
            let thirty_days_ago =
                match now.checked_sub(std::time::Duration::from_secs(30 * 24 * 3600)) {
                    // Corrected Duration usage
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
    println!(
        "扫描完成, 文件数量: {}",
        result.as_ref().map_or(0, |files| files.len())
    );
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
    println!(
        "扫描完成, 文件数量: {}",
        result.as_ref().map_or(0, |files| files.len())
    );
    result
}

// Tauri命令：使用简化配置扫描文件（支持时间范围和文件类型过滤）
#[command]
pub async fn scan_files_simplified_command(
    _app_handle: AppHandle,
    time_range: Option<TimeRange>,
    file_type: Option<FileType>,
    app_state: State<'_, AppState>,
) -> Result<Vec<FileInfo>, String> {
    println!(
        "[SIMPLIFIED_SCAN] 调用简化扫描: 时间范围={:?}, 文件类型={:?}",
        time_range, file_type
    );

    // 获取简化配置
    let simplified_config = app_state.get_simplified_config().await?;

    // 获取监控文件夹
    let config = app_state.get_config().await?;
    let monitored_folders = &config.monitored_folders;

    println!(
        "[SIMPLIFIED_SCAN] 开始简化扫描，监控文件夹数: {}",
        monitored_folders.len()
    );
    let result =
        scan_files_simplified(&simplified_config, monitored_folders, time_range, file_type).await;

    match &result {
        Ok(files) => println!("[SIMPLIFIED_SCAN] 扫描完成，文件数量: {}", files.len()),
        Err(e) => println!("[SIMPLIFIED_SCAN] 扫描失败: {}", e),
    }

    result
}

// 启动后端全量扫描工作，必须在前端权限检查通过后才调用
#[command]
pub async fn start_backend_scanning(
    app_handle: tauri::AppHandle,
    app_state: tauri::State<'_, AppState>,
) -> Result<bool, String> {
    println!("[扫描] 启动后端全量扫描工作");
    // println!("[扫描] 【重要提示】此函数只能在前端确认用户已授予完全磁盘访问权限后调用");
    // println!("[扫描] 正确流程：Splash检查权限通过 -> 调用start_backend_scanning -> 进入应用");

    // Get the FileMonitor instance from AppState.
    // It should have been created by setup_file_monitoring_infrastructure and be in a "new" state.
    let mut file_monitor_instance = {
        let monitor_option = {
            let guard = app_state.file_monitor.lock().unwrap();
            guard.clone()
        };
        match monitor_option {
            Some(monitor) => {
                println!("[扫描] Found FileMonitor instance in AppState.");
                monitor
            }
            None => {
                // This case should ideally not happen if setup_file_monitoring_infrastructure ran correctly.
                eprintln!("[扫描] FileMonitor not found in AppState. This is unexpected. Creating a new one.");
                let (api_host, api_port) = {
                    let api_state = app_handle.state::<crate::ApiState>();
                    let api_state_guard = api_state.0.lock().unwrap();
                    if api_state_guard.process_child.is_none() {
                        return Err("API服务未运行，无法启动文件监控".to_string());
                    }
                    (api_state_guard.host.clone(), api_state_guard.port)
                };
                crate::file_monitor::FileMonitor::new(api_host, api_port)
            }
        }
    };

    // The FileMonitor instance (file_monitor_instance) is now obtained.
    // It will be fully initialized (including starting scans and batch processors)
    // exclusively inside the spawned task below.

    // 通过FileMonitor获取配置而不是AppState
    // 这里先刷新配置以确保获取到最新的监控目录列表
    // This initial refresh is better handled by start_monitoring_setup_and_initial_scan,
    // which already fetches configuration.
    /*
    if let Err(e) = file_monitor_instance.refresh_all_configurations().await {
        eprintln!("[扫描] 刷新配置失败: {}", e);
        return Err(format!("无法刷新配置: {}", e));
    }

    // 检查是否有监控目录
    let monitored_dirs = file_monitor_instance.get_monitored_directories();
    if monitored_dirs.is_empty() {
        println!("[扫描] 没有监控目录，无需启动扫描");
        return Ok(false);
    }

    println!("[扫描] 找到 {} 个监控目录，准备启动扫描", monitored_dirs.len());
    */

    // 发送事件通知前端扫描开始
    if let Err(e) = app_handle.emit("scan_started", ()) {
        eprintln!("[扫描] 发送扫描开始事件失败: {:?}", e);
    }

    // 启动后台扫描任务
    let app_handle_clone = app_handle.clone();
    tokio::spawn(async move {
        // file_monitor_instance is moved into this task.
        println!("[扫描] 开始执行全量扫描");

        // 设置扫描完成标志为false
        let app_state_handle = app_handle_clone.state::<AppState>();
        {
            let mut scan_completed = app_state_handle.initial_scan_completed.lock().unwrap();
            *scan_completed = false;
        }

        // 执行初始扫描（完整的监控设置和扫描）
        match file_monitor_instance
            .start_monitoring_setup_and_initial_scan(app_handle_clone.clone())
            .await
        {
            Ok(_) => {
                println!("[扫描] 初始扫描和监控设置完成");

                // 更新扫描完成标志
                {
                    let mut scan_completed =
                        app_state_handle.initial_scan_completed.lock().unwrap();
                    *scan_completed = true;
                    // After the initial scan is complete, process any pending configuration changes.
                    // Note: process_pending_config_changes spawns its own Tokio task.
                    app_state_handle.process_pending_config_changes();
                }

                // Update AppState with the initialized FileMonitor and its config
                if let Some(config) = file_monitor_instance.get_configurations() {
                    app_state_handle.update_config(config);
                    let mut app_state_monitor_guard = app_state_handle.file_monitor.lock().unwrap();
                    *app_state_monitor_guard = Some(file_monitor_instance.clone());
                    println!("[扫描] 已更新AppState配置");
                }

                // 发送事件通知前端扫描完成
                if let Err(e) = app_handle_clone.emit("scan_completed", true) {
                    eprintln!("[扫描] 发送扫描完成事件失败: {:?}", e);
                }

                // 初始化或重新初始化防抖动监控器
                let debounced_monitor_state = app_state_handle.debounced_file_monitor.clone();

                // 检查是否已存在防抖动监控器
                let debounced_monitor_opt = {
                    let guard = debounced_monitor_state.lock().unwrap();
                    guard.clone()
                };

                let mut debounced_monitor = match debounced_monitor_opt {
                    Some(monitor) => {
                        println!("[扫描] 使用已存在的防抖动监控器");
                        monitor
                    }
                    None => {
                        println!("[扫描] 创建新的防抖动监控器");
                        // 创建新的防抖动监控器
                        let monitor_arc = std::sync::Arc::new(file_monitor_instance.clone());
                        let new_monitor = crate::file_monitor_debounced::DebouncedFileMonitor::new(
                            monitor_arc,
                            Some(app_handle_clone.clone()),
                        );

                        // 保存到 AppState
                        {
                            let mut guard = debounced_monitor_state.lock().unwrap();
                            *guard = Some(new_monitor.clone());
                        }

                        new_monitor
                    }
                };

                // 获取目录列表并启动防抖动监控
                let directories: Vec<String> = file_monitor_instance
                    .get_monitored_directories()
                    .into_iter()
                    .filter(|dir| !dir.is_blacklist) // 过滤掉黑名单目录
                    .map(|dir| dir.path)
                    .collect();

                if directories.is_empty() {
                    println!("[扫描] 没有需要监控的白名单目录，跳过防抖动监控器启动");
                } else {
                    println!(
                        "[扫描] 正在启动防抖动监控，监控 {} 个目录",
                        directories.len()
                    );

                    if let Err(e) = debounced_monitor
                        .start_monitoring(directories, std::time::Duration::from_millis(2_000))
                        .await
                    {
                        eprintln!("[扫描] 启动防抖动监控失败: {}", e);
                    } else {
                        println!("[扫描] 防抖动监控已启动");

                        // 更新 AppState 中的防抖动监控器
                        {
                            let mut guard = debounced_monitor_state.lock().unwrap();
                            *guard = Some(debounced_monitor);
                        }
                    }
                }
            }
            Err(e) => {
                eprintln!("[扫描] 初始扫描失败: {}", e);

                // 发送事件通知前端扫描失败
                if let Err(emit_err) = app_handle_clone.emit("scan_error", e.to_string()) {
                    eprintln!("[扫描] 发送扫描错误事件失败: {:?}", emit_err);
                }
            }
        }
    });

    Ok(true)
}

// 帮助跟踪权限状态的函数
fn log_permission_check(action: &str, path: &Path) {
    #[cfg(target_os = "macos")]
    {
        println!(
            "[权限] {} 访问路径: {} - 提示：此访问应当在前端权限验证通过后进行",
            action,
            path.display()
        );
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
        // 只扫描非黑名单目录
        let should_scan = !monitored_dir.is_blacklist;

        if !should_scan {
            println!("[SCAN] 跳过黑名单目录 {:?}", monitored_dir.path);
            continue;
        }

        let path = Path::new(&monitored_dir.path);

        // 记录权限敏感目录的访问
        log_permission_check("开始扫描", path);

        // 确保前端已经验证权限
        if path.to_string_lossy().contains("/Users") {
            println!(
                "[SCAN] 访问用户敏感目录: {:?} - 应该已经通过前端权限检查",
                path
            );
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

            if let Some(_) = is_inside_macos_bundle(entry.path()) {
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
                    println!(
                        "[SCAN] 跳过非白名单扩展名文件: {} (扩展名: {})",
                        file_path.display(),
                        ext_lower
                    );
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
                    println!(
                        "[SCAN] 跳过不匹配类型过滤器的文件: {} (期望类型: {:?})",
                        file_path.display(),
                        ft
                    );
                    continue;
                }
            }

            // 获取文件元数据
            let metadata = match std::fs::metadata(file_path) {
                Ok(meta) => meta,
                Err(e) => {
                    println!(
                        "[SCAN] 无法获取文件元数据: {} (错误: {})",
                        file_path.display(),
                        e
                    );
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
                    println!(
                        "[SCAN] 跳过不在时间范围内的文件: {} (范围: {:?})",
                        file_path.display(),
                        tr
                    );
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

// 新的简化扫描函数，使用FileScanningConfig
async fn scan_files_simplified(
    config: &crate::file_monitor::FileScanningConfig,
    monitored_folders: &[crate::file_monitor::MonitoredDirectory],
    time_range: Option<TimeRange>,
    file_type: Option<FileType>,
) -> Result<Vec<FileInfo>, String> {
    let mut files = Vec::new();
    let mut stats = ScanStats::default();

    println!(
        "[SCAN_SIMPLIFIED] 开始简化扫描，监控文件夹数: {}",
        monitored_folders.len()
    );
    println!(
        "[SCAN_SIMPLIFIED] 配置：扩展名映射: {}, Bundle扩展名: {}, 忽略规则: {}",
        config.extension_mappings.len(),
        config.bundle_extensions.len(),
        config.ignore_patterns.len()
    );

    // 遍历所有监控的文件夹
    for folder in monitored_folders {
        if folder.is_blacklist {
            println!("[SCAN_SIMPLIFIED] 跳过黑名单文件夹: {}", folder.path);
            continue;
        }

        let folder_path = PathBuf::from(&folder.path);
        if !folder_path.exists() {
            println!("[SCAN_SIMPLIFIED] 文件夹不存在: {}", folder.path);
            continue;
        }

        println!("[SCAN_SIMPLIFIED] 扫描文件夹: {}", folder.path);

        // 使用walkdir遍历文件夹
        let walker = WalkDir::new(&folder_path).follow_links(false).max_depth(10); // 限制最大深度避免无限递归

        for entry in walker.into_iter() {
            let entry = match entry {
                Ok(e) => e,
                Err(e) => {
                    println!("[SCAN_SIMPLIFIED] 读取文件时出错: {}", e);
                    continue;
                }
            };

            let file_path = entry.path();
            stats.total_discovered += 1;

            // 检查是否为隐藏文件
            if is_hidden_file(file_path) {
                stats.hidden_filtered += 1;
                continue;
            }

            // 检查是否为Bundle
            if file_path.is_dir() && is_macos_bundle(file_path, &config.bundle_extensions) {
                println!("[SCAN_SIMPLIFIED] 发现Bundle: {}", file_path.display());

                // 将Bundle作为整体文件处理
                let bundle_extension = get_file_extension(file_path);

                // 检查Bundle的扩展名是否在我们关注的范围内
                if let Some(ref ext) = bundle_extension {
                    if let Some(&category_id) = config.extension_mappings.get(ext) {
                        // 获取Bundle的元数据
                        let metadata = match entry.metadata() {
                            Ok(m) => m,
                            Err(_) => {
                                stats.bundle_filtered += 1;
                                continue;
                            }
                        };

                        let modified_time = match metadata.modified() {
                            Ok(time) => time,
                            Err(_) => {
                                stats.bundle_filtered += 1;
                                continue;
                            }
                        };

                        let modified_time_secs = match modified_time.duration_since(UNIX_EPOCH) {
                            Ok(duration) => duration.as_secs(),
                            Err(_) => {
                                stats.bundle_filtered += 1;
                                continue;
                            }
                        };

                        // 应用时间范围过滤器
                        if let Some(ref tr) = time_range {
                            if !is_file_in_time_range(modified_time_secs, tr) {
                                stats.bundle_filtered += 1;
                                continue;
                            }
                        }

                        // 应用文件类型过滤器（基于分类ID）
                        if let Some(ref ft) = file_type {
                            if *ft != FileType::All {
                                let target_category_ids = get_category_ids_for_file_type(ft);
                                if !target_category_ids.is_empty()
                                    && !target_category_ids.contains(&category_id)
                                {
                                    stats.bundle_filtered += 1;
                                    continue;
                                }
                            }
                        }

                        let created_time = metadata
                            .created()
                            .ok()
                            .map(|time| system_time_to_iso_string(time));

                        let file_name = file_path
                            .file_name()
                            .and_then(|name| name.to_str())
                            .unwrap_or("")
                            .to_string();

                        files.push(FileInfo {
                            file_path: file_path.to_string_lossy().into_owned(),
                            file_name,
                            file_size: metadata.len(),
                            extension: bundle_extension,
                            created_time,
                            modified_time: system_time_to_iso_string(modified_time),
                            category_id: Some(category_id),
                        });

                        stats.total_included += 1;
                        println!(
                            "[SCAN_SIMPLIFIED] 包含Bundle: {} (分类: {})",
                            file_path.display(),
                            category_id
                        );
                    } else {
                        stats.bundle_filtered += 1;
                        println!("[SCAN_SIMPLIFIED] Bundle扩展名不在关注范围: {}", ext);
                    }
                } else {
                    stats.bundle_filtered += 1;
                    println!(
                        "[SCAN_SIMPLIFIED] Bundle无法获取扩展名: {}",
                        file_path.display()
                    );
                }

                // 跳过Bundle内部文件的扫描
                continue;
            }

            // 检查是否在Bundle内部
            if let Some(bundle_path) = find_containing_bundle(file_path, &config.bundle_extensions)
            {
                println!(
                    "[SCAN_SIMPLIFIED] 跳过Bundle内部文件: {} (Bundle: {})",
                    file_path.display(),
                    bundle_path.display()
                );
                stats.bundle_filtered += 1;
                continue;
            }

            // 只处理普通文件
            if !file_path.is_file() {
                continue;
            }

            // 获取文件扩展名
            let extension = get_file_extension(file_path);

            // 只包含在扩展名映射中的文件
            let category_id = if let Some(ref ext) = extension {
                if let Some(&cat_id) = config.extension_mappings.get(ext) {
                    cat_id
                } else {
                    stats.extension_filtered += 1;
                    continue; // 扩展名不在关注范围内
                }
            } else {
                stats.extension_filtered += 1;
                continue; // 无扩展名文件不包含
            };

            // 应用文件类型过滤器
            if let Some(ref ft) = file_type {
                if *ft != FileType::All {
                    let target_category_ids = get_category_ids_for_file_type(ft);
                    if !target_category_ids.is_empty()
                        && !target_category_ids.contains(&category_id)
                    {
                        stats.extension_filtered += 1;
                        continue;
                    }
                }
            }

            // 获取文件元数据
            let metadata = match entry.metadata() {
                Ok(m) => m,
                Err(_) => {
                    stats.extension_filtered += 1;
                    continue;
                }
            };

            let modified_time = match metadata.modified() {
                Ok(time) => time,
                Err(_) => {
                    stats.extension_filtered += 1;
                    continue;
                }
            };

            let modified_time_secs = match modified_time.duration_since(UNIX_EPOCH) {
                Ok(duration) => duration.as_secs(),
                Err(_) => {
                    stats.extension_filtered += 1;
                    continue;
                }
            };

            // 应用时间范围过滤器
            if let Some(ref tr) = time_range {
                if !is_file_in_time_range(modified_time_secs, tr) {
                    continue;
                }
            }

            let created_time = metadata
                .created()
                .ok()
                .map(|time| system_time_to_iso_string(time));

            let file_name = file_path
                .file_name()
                .and_then(|name| name.to_str())
                .unwrap_or("")
                .to_string();

            files.push(FileInfo {
                file_path: file_path.to_string_lossy().into_owned(),
                file_name,
                file_size: metadata.len(),
                extension,
                created_time,
                modified_time: system_time_to_iso_string(modified_time),
                category_id: Some(category_id),
            });

            stats.total_included += 1;

            // 限制返回文件数量
            if files.len() >= 500 {
                println!("[SCAN_SIMPLIFIED] 已达到500个文件的限制，停止扫描");
                break;
            }
        }

        // 如果已经达到文件数量限制，跳出文件夹循环
        if files.len() >= 500 {
            break;
        }
    }

    // 打印扫描统计信息
    println!("[SCAN_SIMPLIFIED] 扫描统计: 发现总数: {}, 包含: {}, 过滤: {} (隐藏: {}, 扩展名: {}, Bundle: {})", 
        stats.total_discovered, 
        stats.total_included,
        stats.hidden_filtered + stats.extension_filtered + stats.bundle_filtered,
        stats.hidden_filtered,
        stats.extension_filtered,
        stats.bundle_filtered
    );

    Ok(files)
}
