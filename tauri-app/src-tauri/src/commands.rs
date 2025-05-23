use std::fs;
use std::path::Path;
use crate::AppState;
use tauri::State;
use serde::Serialize;

#[tauri::command(rename_all = "snake_case")]
pub fn resolve_directory_from_path(path_str: String) -> Result<String, String> {
    // 检查是否有特殊前缀或协议
    if path_str.starts_with("file://") {
        // 检测到文件URL协议，去除前缀
        let clean_path = path_str.replace("file://", "");
        return resolve_directory_from_path(clean_path);
    }

    let path = Path::new(&path_str);

    match fs::metadata(path) {
        Ok(metadata) => {
            if metadata.is_file() {
                // 如果是文件，返回其父目录
                match path.parent() {
                    Some(parent_path) => {
                        let result = parent_path.to_string_lossy().into_owned();
                        Ok(result)
                    }
                    None => Err(format!("文件 '{}' 没有父文件夹", path.display())),
                }
            } else if metadata.is_dir() {
                // 如果是目录，直接返回
                let result = path.to_string_lossy().into_owned();
                Ok(result)
            } else {
                Err(format!("路径 '{}' 不是有效的文件或文件夹", path.display()))
            }
        }
        Err(e) => Err(format!("无法读取路径 '{}' 的元数据: {}", path.display(), e)),
    }
}

#[derive(Serialize)]
pub struct MonitorStatsResponse {
    processed_files: u64,
    filtered_files: u64,
    filtered_bundles: u64,
    error_count: u64,
}

#[tauri::command(rename_all = "snake_case")]
pub fn get_file_monitor_stats(state: State<AppState>) -> Result<MonitorStatsResponse, String> {
    let monitor_state = state.file_monitor.lock().map_err(|e| e.to_string())?;
    
    if let Some(monitor) = &*monitor_state {
        // 获取监控统计信息
        let stats = monitor.get_monitor_stats();
        
        Ok(MonitorStatsResponse {
            processed_files: stats.processed_files,
            filtered_files: stats.filtered_files,
            filtered_bundles: stats.filtered_bundles,
            error_count: stats.error_count,
        })
    } else {
        Err("文件监控尚未启动".to_string())
    }
}

#[tauri::command(rename_all = "snake_case")]
pub fn test_bundle_detection(path: String) -> Result<bool, String> {
    use crate::file_monitor::FileMonitor;
    use std::path::Path;
    
    // 测试指定路径是否为macOS bundle
    let path_obj = Path::new(&path);
    let is_bundle = FileMonitor::is_macos_bundle_folder(path_obj);
    
    // 返回结果
    Ok(is_bundle)
}
