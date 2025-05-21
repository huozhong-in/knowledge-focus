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
    // Manager, 
    State}; // Added State
use walkdir::WalkDir;

use crate::file_monitor::{
    AllConfigurations, 
    FileExtensionMapRust, 
    // MonitoredDirectory, 
    DirectoryAuthStatus}; // Added MonitoredDirectory, DirectoryAuthStatus
use crate::AppState; // Import AppState

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

        // Check if the file's extension maps to any of the target category IDs
        extension_maps.iter().any(|map| {
            map.extension.to_lowercase() == ext && target_category_ids.contains(&map.category_id)
        })
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

// 内部函数：使用指定过滤条件扫描文件
async fn scan_files_with_filter(
    config: &AllConfigurations,
    time_range: Option<TimeRange>,
    file_type: Option<FileType>,
) -> Result<Vec<FileInfo>, String> {
    let mut files = Vec::new();
    let extension_maps = &config.file_extension_maps;

    for monitored_dir in &config.monitored_folders {
        // Only scan authorized and non-blacklisted directories
        let should_scan = if config.full_disk_access {
            !monitored_dir.is_blacklist
        } else {
            monitored_dir.auth_status == DirectoryAuthStatus::Authorized && !monitored_dir.is_blacklist
        };

        if !should_scan {
            println!("Skipping directory {:?} (auth_status: {:?}, is_blacklist: {})", monitored_dir.path, monitored_dir.auth_status, monitored_dir.is_blacklist);
            continue;
        }

        let path = Path::new(&monitored_dir.path);
        if !path.exists() || !path.is_dir() {
            continue;
        }

        for entry in WalkDir::new(path)
            .follow_links(true)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            if !entry.file_type().is_file() {
                continue;
            }

            let file_path = entry.path();
            let extension = get_file_extension(file_path);

            // Check file type filter
            if let Some(ref ft) = file_type {
                if !is_file_of_type(&extension, ft, extension_maps) {
                    continue;
                }
            }

            // Get file metadata
            let metadata = match std::fs::metadata(file_path) {
                Ok(meta) => meta,
                Err(_) => continue,
            };

            // Get modified time
            let modified_time = match metadata.modified() {
                Ok(time) => time,
                Err(_) => continue,
            };

            let modified_time_secs = match modified_time.duration_since(UNIX_EPOCH) {
                Ok(duration) => duration.as_secs(),
                Err(_) => continue,
            };

            // Check time range filter
            if let Some(ref tr) = time_range {
                if !is_file_in_time_range(modified_time_secs, tr) {
                    continue;
                }
            }

            // Get created time
            let created_time = metadata
                .created()
                .ok()
                .map(|time| system_time_to_iso_string(time));

            // Calculate file size
            let file_size = metadata.len();

            // Get file name
            let file_name = file_path
                .file_name()
                .and_then(|name| name.to_str())
                .unwrap_or("")
                .to_string();

            // Match category ID based on extension maps
            let category_id = extension.as_ref().and_then(|ext| {
                extension_maps
                    .iter()
                    .find(|map| map.extension.to_lowercase() == ext.to_lowercase())
                    .map(|map| map.category_id)
            });

            files.push(FileInfo {
                file_path: file_path.to_string_lossy().into_owned(),
                file_name,
                file_size,
                extension,
                created_time,
                modified_time: system_time_to_iso_string(modified_time),
                category_id,
            });
        }
    }

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
