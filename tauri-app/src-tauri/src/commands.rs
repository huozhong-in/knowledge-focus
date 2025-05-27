use std::fs;
use std::path::Path;
use crate::AppState;
use tauri::{State, Manager}; // 添加Manager以使用app_handle方法
use serde::Serialize;

#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn scan_directory(path: String, state: tauri::State<'_, crate::AppState>, app_handle: tauri::AppHandle) -> Result<(), String> {
    println!("[CMD] scan_directory 被调用，路径: {}", path);
    
    // 获取对monitor的克隆，避免长时间持有锁
    // 获取监控器或初始化一个新的，所有MutexGuard必须在任何await之前释放
    let monitor = {
        // 作用域1：尝试获取现有监控器
        let existing_monitor = {
            let guard = state.file_monitor.lock().unwrap();
            if let Some(monitor) = &*guard {
                println!("[CMD] scan_directory 文件监控器已就绪，继续扫描");
                let monitor_clone = monitor.clone();
                // 在作用域结束时guard会自动释放
                Some(monitor_clone)
            } else {
                None
            }
        }; // guard在这里自动释放
        
        // 如果已有监控器，直接返回
        if let Some(monitor) = existing_monitor {
            monitor
        } else {
            println!("[CMD] scan_directory 文件监控器未初始化，尝试启动监控...");
            
            // 尝试启动文件监控
            use crate::{ApiState, file_monitor::FileMonitor};
            
            // 获取API信息
            let api_host;
            let api_port;
            {
                let api_state = app_handle.state::<ApiState>();
                let api_state_guard = api_state.0.lock().unwrap();
                
                if api_state_guard.process_child.is_none() {
                    return Err("API服务未运行，无法启动文件监控".to_string());
                }
                
                api_host = api_state_guard.host.clone();
                api_port = api_state_guard.port;
            }
            
            // 创建并启动监控
            let mut monitor = FileMonitor::new(api_host, api_port);
            if let Err(e) = monitor.start_monitoring_setup_and_initial_scan().await {
                return Err(format!("文件监控器启动失败: {}", e));
            }
            // 保存监控实例
            {
                let mut monitor_guard = state.file_monitor.lock().unwrap();
                *monitor_guard = Some(monitor.clone());
                println!("[CMD] scan_directory 已自动启动文件监控器");
                // 确保锁在这个作用域结束时被释放
            }
            
            monitor
            
        }
    };
    
    // 刷新目录列表，确保目录已经添加到监控列表中
    if let Err(e) = monitor.update_monitored_directories().await {
        eprintln!("[CMD] scan_directory 无法刷新监控目录: {}", e);
    }
    
    // 执行单个目录扫描
    monitor.scan_single_directory(&path).await?;
    
    // 为新添加的目录设置防抖动监控
    let debounced_monitor_state = app_handle.state::<AppState>().debounced_file_monitor.clone();
    
    // Scope the lock so it's dropped before any await points
    let deb_monitor_clone = {
        let deb_monitor_guard = debounced_monitor_state.lock().unwrap();
        if let Some(deb_monitor) = &*deb_monitor_guard {
            // Clone the monitor before dropping the guard
            Some(deb_monitor.clone())
        } else {
            eprintln!("[CMD] scan_directory: DebouncedFileMonitor not found in state. Cannot set up new watch for {}.", path);
            None
        }
        // Guard is automatically dropped here at end of scope
    };

    // Now use the cloned monitor if available
    if let Some(monitor) = deb_monitor_clone {
        let debounce_duration = std::time::Duration::from_millis(500); // Or get from config
        if let Err(e) = monitor.add_directory_to_watch(path.clone(), debounce_duration).await {
             eprintln!("[CMD] scan_directory: Failed to set up debounced watch for {}: {}", path, e);
        } else {
             println!("[CMD] scan_directory: Successfully set up debounced watch for {}", path);
        }
    }
    Ok(())
}
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
