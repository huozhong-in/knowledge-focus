use std::fs;
use std::path::Path;
use std::sync::Arc;
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

/// 停止监控指定ID的目录
/// 该命令会从监控列表中移除目录，使Rust端停止对该目录的监控
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn stop_monitoring_directory(directory_id: i32, state: tauri::State<'_, crate::AppState>) -> Result<(), String> {
    println!("[CMD] stop_monitoring_directory 被调用，目录ID: {}", directory_id);
    
    // 获取文件监控器
    let monitor = {
        let guard = state.file_monitor.lock().unwrap();
        match &*guard {
            Some(monitor) => monitor.clone(),
            None => return Err("文件监控器未初始化".to_string()),
        }
    };
    
    // 先获取目录的路径，用于后续停止防抖动监控
    let directory_path: Option<String> = {
        let dirs = monitor.get_monitored_directories();
        dirs.iter()
            .find(|dir| dir.id == Some(directory_id))
            .map(|dir| dir.path.clone())
    };
    
    // 调用监控器的停止监控方法
    monitor.stop_monitoring_directory(directory_id).await?;
    
    // 如果找到目录路径，同时停止防抖动监控
    if let Some(path) = directory_path {
        // 尝试获取防抖动监控器
        let debounced_monitor = {
            let guard = state.debounced_file_monitor.lock().unwrap();
            match &*guard {
                Some(deb_monitor) => Some(deb_monitor.clone()),
                None => None,
            }
        };
        
        // 如果防抖动监控器存在，停止对该路径的监控
        if let Some(deb_monitor) = debounced_monitor {
            println!("[CMD] 同时停止防抖动监控: {}", path);
            deb_monitor.stop_monitoring_path(&path);
        }
    }
    
    // 返回成功
    Ok(())
}

// --- 文件夹层级管理命令 ---

/// 添加黑名单文件夹到指定父文件夹下
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn add_blacklist_folder(
    parent_id: i32,
    folder_path: String,
    folder_alias: Option<String>,
    app_handle: tauri::AppHandle
) -> Result<serde_json::Value, String> {
    println!("[CMD] add_blacklist_folder 被调用，父ID: {}, 路径: {}", parent_id, folder_path);
    
    // 获取API信息
    let (api_host, api_port) = {
        let api_state = app_handle.state::<crate::ApiState>();
        let api_state_guard = api_state.0.lock().unwrap();
        (api_state_guard.host.clone(), api_state_guard.port)
    };
    
    // 构建API请求
    let client = reqwest::Client::new();
    let url = format!("http://{}:{}/folders/blacklist/{}", api_host, api_port, parent_id);
    
    let mut request_data = serde_json::json!({
        "path": folder_path
    });
    
    if let Some(alias) = folder_alias {
        request_data["alias"] = serde_json::Value::String(alias);
    }
    
    // 发送POST请求
    match client.post(&url)
        .json(&request_data)
        .send()
        .await
    {
        Ok(response) => {
            if response.status().is_success() {
                match response.json::<serde_json::Value>().await {
                    Ok(json_response) => {
                        println!("[CMD] add_blacklist_folder 成功: {:?}", json_response);
                        Ok(json_response)
                    }
                    Err(e) => Err(format!("解析响应失败: {}", e))
                }
            } else {
                let status = response.status();
                let error_text = response.text().await.unwrap_or_else(|_| "无法读取错误响应".to_string());
                Err(format!("API请求失败 [{}]: {}", status, error_text))
            }
        }
        Err(e) => Err(format!("发送请求失败: {}", e))
    }
}

/// 移除黑名单文件夹
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn remove_blacklist_folder(
    folder_id: i32,
    app_handle: tauri::AppHandle
) -> Result<serde_json::Value, String> {
    println!("[CMD] remove_blacklist_folder 被调用，文件夹ID: {}", folder_id);
    
    // 获取API信息
    let (api_host, api_port) = {
        let api_state = app_handle.state::<crate::ApiState>();
        let api_state_guard = api_state.0.lock().unwrap();
        (api_state_guard.host.clone(), api_state_guard.port)
    };
    
    // 构建API请求
    let client = reqwest::Client::new();
    let url = format!("http://{}:{}/directories/{}", api_host, api_port, folder_id);
    
    // 发送DELETE请求
    match client.delete(&url).send().await {
        Ok(response) => {
            if response.status().is_success() {
                match response.json::<serde_json::Value>().await {
                    Ok(json_response) => {
                        println!("[CMD] remove_blacklist_folder 成功: {:?}", json_response);
                        Ok(json_response)
                    }
                    Err(e) => Err(format!("解析响应失败: {}", e))
                }
            } else {
                let status = response.status();
                let error_text = response.text().await.unwrap_or_else(|_| "无法读取错误响应".to_string());
                Err(format!("API请求失败 [{}]: {}", status, error_text))
            }
        }
        Err(e) => Err(format!("发送请求失败: {}", e))
    }
}

/// 获取文件夹层级关系
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn get_folder_hierarchy(
    app_handle: tauri::AppHandle
) -> Result<serde_json::Value, String> {
    println!("[CMD] get_folder_hierarchy 被调用");
    
    // 获取API信息
    let (api_host, api_port) = {
        let api_state = app_handle.state::<crate::ApiState>();
        let api_state_guard = api_state.0.lock().unwrap();
        (api_state_guard.host.clone(), api_state_guard.port)
    };
    
    // 构建API请求
    let client = reqwest::Client::new();
    let url = format!("http://{}:{}/folders/hierarchy", api_host, api_port);
    
    // 发送GET请求
    match client.get(&url).send().await {
        Ok(response) => {
            if response.status().is_success() {
                match response.json::<serde_json::Value>().await {
                    Ok(json_response) => {
                        println!("[CMD] get_folder_hierarchy 成功获取层级关系");
                        Ok(json_response)
                    }
                    Err(e) => Err(format!("解析响应失败: {}", e))
                }
            } else {
                let status = response.status();
                let error_text = response.text().await.unwrap_or_else(|_| "无法读取错误响应".to_string());
                Err(format!("API请求失败 [{}]: {}", status, error_text))
            }
        }
        Err(e) => Err(format!("发送请求失败: {}", e))
    }
}

/// 刷新监控配置（重新获取文件夹配置和Bundle扩展名）
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn refresh_monitoring_config(
    state: tauri::State<'_, crate::AppState>
) -> Result<serde_json::Value, String> {
    println!("[CMD] refresh_monitoring_config 被调用");
    
    // 获取文件监控器
    let monitor = {
        let guard = state.file_monitor.lock().unwrap();
        match &*guard {
            Some(monitor) => monitor.clone(),
            None => return Err("文件监控器未初始化".to_string()),
        }
    };
    
    // 刷新所有配置
    match monitor.refresh_all_configurations().await {
        Ok(()) => {
            let summary = monitor.get_configuration_summary();
            println!("[CMD] refresh_monitoring_config 成功，配置摘要: {:?}", summary);
            Ok(serde_json::json!({
                "status": "success",
                "message": "配置刷新成功",
                "summary": summary
            }))
        }
        Err(e) => {
            eprintln!("[CMD] refresh_monitoring_config 失败: {}", e);
            Err(format!("配置刷新失败: {}", e))
        }
    }
}

/// 获取当前Bundle扩展名列表
#[tauri::command(rename_all = "snake_case")]
pub fn get_bundle_extensions(
    state: tauri::State<'_, crate::AppState>
) -> Result<Vec<String>, String> {
    println!("[CMD] get_bundle_extensions 被调用");
    
    // 获取文件监控器
    let monitor = {
        let guard = state.file_monitor.lock().unwrap();
        match &*guard {
            Some(monitor) => monitor.clone(),
            None => return Err("文件监控器未初始化".to_string()),
        }
    };
    
    // 从当前配置中提取Bundle扩展名列表
    let extensions = monitor.get_bundle_extensions();
    println!("[CMD] get_bundle_extensions 返回 {} 个扩展名", extensions.len());
    Ok(extensions)
}

/// 获取配置状态摘要
#[tauri::command(rename_all = "snake_case")]
pub fn get_configuration_summary(
    state: tauri::State<'_, crate::AppState>
) -> Result<serde_json::Value, String> {
    println!("[CMD] get_configuration_summary 被调用");
    
    // 获取文件监控器
    let monitor = {
        let guard = state.file_monitor.lock().unwrap();
        match &*guard {
            Some(monitor) => monitor.clone(),
            None => return Err("文件监控器未初始化".to_string()),
        }
    };
    
    // 获取配置摘要
    let summary = monitor.get_configuration_summary();
    println!("[CMD] get_configuration_summary 返回摘要: {:?}", summary);
    Ok(summary)
}

#[derive(Serialize)]
pub struct DirectoryEntry {
    name: String,
    path: String,
    is_directory: bool,
}

#[tauri::command]
pub async fn read_directory(path: String) -> Result<Vec<DirectoryEntry>, String> {
    println!("[CMD] read_directory 被调用，路径: {}", path);
    
    let path_obj = Path::new(&path);
    
    if !path_obj.exists() {
        return Err("路径不存在".to_string());
    }
    
    if !path_obj.is_dir() {
        return Err("路径不是文件夹".to_string());
    }
    
    let mut entries = Vec::new();
    
    match fs::read_dir(path_obj) {
        Ok(dir_entries) => {
            for entry in dir_entries {
                match entry {
                    Ok(dir_entry) => {
                        let entry_path = dir_entry.path();
                        let is_directory = entry_path.is_dir();
                        
                        // 只返回目录，忽略文件
                        if is_directory {
                            // 过滤掉隐藏文件夹（以.开头的）
                            if let Some(name) = entry_path.file_name() {
                                if let Some(name_str) = name.to_str() {
                                    if !name_str.starts_with('.') {
                                        entries.push(DirectoryEntry {
                                            name: name_str.to_string(),
                                            path: entry_path.to_string_lossy().to_string(),
                                            is_directory,
                                        });
                                    }
                                }
                            }
                        }
                    }
                    Err(e) => {
                        println!("[CMD] 读取目录项失败: {}", e);
                        // 继续处理其他项，不中断整个过程
                    }
                }
            }
        }
        Err(e) => {
            return Err(format!("无法读取目录: {}", e));
        }
    }
    
    // 按名称排序
    entries.sort_by(|a, b| a.name.cmp(&b.name));
    
    println!("[CMD] read_directory 成功读取 {} 个子目录", entries.len());
    Ok(entries)
}

// --- 配置变更队列管理命令 ---

/// 添加黑名单文件夹到队列（如果初始扫描已完成则立即处理队列）
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn queue_add_blacklist_folder(
    parent_id: i32,
    folder_path: String,
    folder_alias: Option<String>,
    state: tauri::State<'_, crate::AppState>,
    _app_handle: tauri::AppHandle
) -> Result<serde_json::Value, String> {
    println!("[CMD] queue_add_blacklist_folder 被调用，父ID: {}, 路径: {}", parent_id, folder_path);
    
    // 添加到队列
    let change = crate::ConfigChangeRequest::AddBlacklist {
        parent_id,
        folder_path: folder_path.clone(),
        folder_alias,
    };
    state.add_pending_config_change(change);
    
    // 检查初始扫描是否已完成
    if state.is_initial_scan_completed() {
        println!("[CONFIG_QUEUE] 初始扫描已完成，配置变更已加入队列，即将处理");
        // 触发队列处理
        state.process_pending_config_changes();
        
        Ok(serde_json::json!({
            "status": "queued_for_processing",
            "message": format!("黑名单文件夹 {} 已加入处理队列并即将执行", folder_path)
        }))
    } else {
        println!("[CONFIG_QUEUE] 初始扫描未完成，将黑名单添加操作加入队列");
        Ok(serde_json::json!({
            "status": "queued",
            "message": format!("黑名单文件夹 {} 已加入处理队列，将在初始扫描完成后处理", folder_path)
        }))
    }
}

/// 删除文件夹（队列版本）
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn queue_delete_folder(
    folder_id: i32,
    folder_path: String,
    is_blacklist: bool,
    state: tauri::State<'_, crate::AppState>,
    _app_handle: tauri::AppHandle  // 使用下划线前缀表示故意不使用的参数
) -> Result<serde_json::Value, String> {
    println!("[CMD] queue_delete_folder 被调用，ID: {}, 路径: {}, 是否黑名单: {}", folder_id, folder_path, is_blacklist);
    
    // 检查文件监控器是否已初始化
    {
        let guard = state.file_monitor.lock().unwrap();
        if guard.is_none() {
            return Err("文件监控器未初始化".to_string());
        }
    }
    
    // 即使初始扫描已完成，也应将变更放入队列，以确保操作按正确顺序执行
    // 添加到队列
    let change = crate::ConfigChangeRequest::DeleteFolder {
        folder_id,
        folder_path: folder_path.clone(),
        is_blacklist,
    };
    state.add_pending_config_change(change);
    
    // 如果初始扫描已完成，立即处理队列
    if state.is_initial_scan_completed() {
        println!("[CONFIG_QUEUE] 初始扫描已完成，配置变更已加入队列，即将处理");
        // 触发队列处理
        state.process_pending_config_changes();
        
        Ok(serde_json::json!({
            "status": "queued_for_processing",
            "message": format!("文件夹 {} 删除操作已加入处理队列并即将执行", folder_path)
        }))
    } else {
        println!("[CONFIG_QUEUE] 初始扫描未完成，将文件夹删除操作加入队列");
        Ok(serde_json::json!({
            "status": "queued",
            "message": format!("文件夹 {} 删除操作已加入处理队列，将在初始扫描完成后处理", folder_path)
        }))
    }
}

/// 切换文件夹黑白名单状态（队列版本）
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn queue_toggle_folder_status(
    folder_id: i32,
    folder_path: String,
    is_blacklist: bool,
    state: tauri::State<'_, crate::AppState>
) -> Result<serde_json::Value, String> {
    println!("[CMD] queue_toggle_folder_status 被调用，ID: {}, 路径: {}, 设为黑名单: {}", folder_id, folder_path, is_blacklist);
    
    // 添加到队列
    let change = crate::ConfigChangeRequest::ToggleFolder {
        folder_id,
        is_blacklist,
        folder_path: folder_path.clone(),
    };
    state.add_pending_config_change(change);
    
    // 检查初始扫描是否已完成
    if state.is_initial_scan_completed() {
        println!("[CONFIG_QUEUE] 初始扫描已完成，配置变更已加入队列，即将处理");
        // 触发队列处理
        state.process_pending_config_changes();
        
        Ok(serde_json::json!({
            "status": "queued_for_processing",
            "message": format!("文件夹 {} 状态切换已加入处理队列并即将执行", folder_path)
        }))
    } else {
        println!("[CONFIG_QUEUE] 初始扫描未完成，将文件夹状态切换操作加入队列");
        Ok(serde_json::json!({
            "status": "queued",
            "message": format!("文件夹 {} 状态切换已加入处理队列，将在初始扫描完成后处理", folder_path)
        }))
    }
}

/// 添加白名单文件夹（队列版本）
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn queue_add_whitelist_folder(
    folder_path: String,
    folder_alias: Option<String>,
    state: tauri::State<'_, crate::AppState>
) -> Result<serde_json::Value, String> {
    println!("[CMD] queue_add_whitelist_folder 被调用，路径: {}", folder_path);
    
    // 添加到队列
    let change = crate::ConfigChangeRequest::AddWhitelist {
        folder_path: folder_path.clone(),
        folder_alias,
    };
    state.add_pending_config_change(change);
    
    // 检查初始扫描是否已完成
    if state.is_initial_scan_completed() {
        println!("[CONFIG_QUEUE] 初始扫描已完成，配置变更已加入队列，即将处理");
        // 触发队列处理
        state.process_pending_config_changes();
        
        Ok(serde_json::json!({
            "status": "queued_for_processing",
            "message": format!("白名单文件夹 {} 已加入处理队列并即将执行", folder_path)
        }))
    } else {
        println!("[CONFIG_QUEUE] 初始扫描未完成，将白名单添加操作加入队列");
        Ok(serde_json::json!({
            "status": "queued",
            "message": format!("白名单文件夹 {} 已加入处理队列，将在初始扫描完成后处理", folder_path)
        }))
    }
}

/// 获取配置变更队列状态
#[tauri::command(rename_all = "snake_case")]
pub fn queue_get_status(
    state: tauri::State<'_, crate::AppState>
) -> Result<serde_json::Value, String> {
    // println!("[CMD] queue_get_status 被调用");
    
    let initial_scan_completed = state.is_initial_scan_completed();
    let pending_changes_count = state.get_pending_config_changes_count();
    let has_pending_changes = state.has_pending_config_changes();
    
    Ok(serde_json::json!({
        "initial_scan_completed": initial_scan_completed,
        "pending_changes_count": pending_changes_count,
        "has_pending_changes": has_pending_changes
    }))
}

/// 【兼容旧版】获取配置变更队列状态（重定向到queue_get_status）
#[tauri::command(rename_all = "snake_case")]
pub fn get_config_queue_status(
    state: tauri::State<'_, crate::AppState>
) -> Result<serde_json::Value, String> {
    // println!("[CMD] get_config_queue_status 被调用 (重定向到queue_get_status)");
    queue_get_status(state)
}

// --- 配置变更队列管理命令结束 ---

// --- 文件监控配置扩展命令 ---

/// 添加黑名单文件夹（支持层级结构）
#[tauri::command(rename_all = "snake_case", async)]
pub async fn add_blacklist_folder_with_path(
    path: String, 
    parent_id: Option<i32>,
    state: tauri::State<'_, crate::AppState>
) -> Result<serde_json::Value, String> {
    println!("[CMD] add_blacklist_folder_with_path 被调用，路径: {}, 父ID: {:?}", path, parent_id);
    
    // 获取文件监控器
    let monitor = {
        let guard = state.file_monitor.lock().unwrap();
        if let Some(monitor) = &*guard {
            monitor.clone()
        } else {
            return Err("文件监控器未初始化".to_string());
        }
    };

    // TODO: 实现层级黑名单添加逻辑（在阶段三B完成后实现）
    // 目前只是简单地将路径添加到黑名单
    let api_host = monitor.get_api_host();
    let api_port = monitor.get_api_port();

    // 构建请求URL
    let url = format!(
        "http://{}:{}/blacklist/add",
        api_host, api_port
    );

    // 准备请求数据
    let mut request_data = serde_json::Map::new();
    request_data.insert("path".to_string(), serde_json::Value::String(path));
    if let Some(pid) = parent_id {
        request_data.insert("parent_id".to_string(), serde_json::Value::Number(serde_json::Number::from(pid)));
    }
    
    // 发送请求到API
    let client = reqwest::Client::new();
    match client.post(&url).json(&request_data).send().await {
        Ok(response) => {
            if response.status().is_success() {
                let result = response.json::<serde_json::Value>().await
                    .map_err(|e| format!("解析API响应失败: {}", e))?;
                
                // 刷新文件监控器的配置（异步，不等待完成）
                let monitor_clone = monitor.clone();
                tokio::spawn(async move {
                    if let Err(e) = monitor_clone.refresh_folder_configuration().await {
                        eprintln!("[CMD] 刷新配置失败: {}", e);
                    }
                });
                
                Ok(result)
            } else {
                let error = response.text().await.unwrap_or_else(|_| "读取错误响应失败".to_string());
                Err(format!("添加黑名单失败: {}", error))
            }
        },
        Err(e) => Err(format!("请求API失败: {}", e))
    }
}

/// 移除黑名单文件夹（通过路径）
#[tauri::command(rename_all = "snake_case", async)]
pub async fn remove_blacklist_folder_by_path(
    path: String, 
    state: tauri::State<'_, crate::AppState>
) -> Result<serde_json::Value, String> {
    println!("[CMD] remove_blacklist_folder_by_path 被调用，路径: {}", path);
    
    // 获取文件监控器
    let monitor = {
        let guard = state.file_monitor.lock().unwrap();
        if let Some(monitor) = &*guard {
            monitor.clone()
        } else {
            return Err("文件监控器未初始化".to_string());
        }
    };

    // 构建请求URL
    let url = format!(
        "http://{}:{}/blacklist/remove",
        monitor.get_api_host(), monitor.get_api_port()
    );
    
    // 准备请求数据
    let mut request_data = serde_json::Map::new();
    request_data.insert("path".to_string(), serde_json::Value::String(path));
    
    // 发送请求到API
    let client = reqwest::Client::new();
    match client.post(&url).json(&request_data).send().await {
        Ok(response) => {
            if response.status().is_success() {
                let result = response.json::<serde_json::Value>().await
                    .map_err(|e| format!("解析API响应失败: {}", e))?;
                
                // 刷新文件监控器的配置（异步，不等待完成）
                let monitor_clone = monitor.clone();
                tokio::spawn(async move {
                    if let Err(e) = monitor_clone.refresh_folder_configuration().await {
                        eprintln!("[CMD] 刷新配置失败: {}", e);
                    }
                });
                
                Ok(result)
            } else {
                let error = response.text().await.unwrap_or_else(|_| "读取错误响应失败".to_string());
                Err(format!("移除黑名单失败: {}", error))
            }
        },
        Err(e) => Err(format!("请求API失败: {}", e))
    }
}

// 删除重复的 refresh_monitoring_config 和 get_bundle_extensions 函数定义，
// 因为这些函数已经在前面定义过了

// --- End of 文件监控配置扩展命令 ---

/// 【兼容旧版】添加黑名单文件夹到队列（重定向到queue_add_blacklist_folder）
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn add_blacklist_folder_queued(
    parent_id: i32,
    folder_path: String,
    folder_alias: Option<String>,
    state: tauri::State<'_, crate::AppState>,
    app_handle: tauri::AppHandle
) -> Result<serde_json::Value, String> {
    println!("[CMD] add_blacklist_folder_queued 被调用 (重定向到queue_add_blacklist_folder)");
    queue_add_blacklist_folder(parent_id, folder_path, folder_alias, state, app_handle).await
}

/// 【兼容旧版】删除文件夹（队列版本）（重定向到queue_delete_folder）
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn remove_folder_queued(
    folder_id: i32,
    folder_path: String,
    is_blacklist: bool,
    state: tauri::State<'_, crate::AppState>,
    app_handle: tauri::AppHandle
) -> Result<serde_json::Value, String> {
    println!("[CMD] remove_folder_queued 被调用 (重定向到queue_delete_folder)");
    queue_delete_folder(folder_id, folder_path, is_blacklist, state, app_handle).await
}

/// 【兼容旧版】切换文件夹黑白名单状态（队列版本）（重定向到queue_toggle_folder_status）
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn toggle_folder_status_queued(
    folder_id: i32,
    folder_path: String,
    is_blacklist: bool,
    state: tauri::State<'_, crate::AppState>
) -> Result<serde_json::Value, String> {
    println!("[CMD] toggle_folder_status_queued 被调用 (重定向到queue_toggle_folder_status)");
    queue_toggle_folder_status(folder_id, folder_path, is_blacklist, state).await
}

/// 【兼容旧版】添加白名单文件夹（队列版本）（重定向到queue_add_whitelist_folder）
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn add_whitelist_folder_queued(
    folder_path: String,
    folder_alias: Option<String>,
    state: tauri::State<'_, crate::AppState>
) -> Result<serde_json::Value, String> {
    println!("[CMD] add_whitelist_folder_queued 被调用 (重定向到queue_add_whitelist_folder)");
    queue_add_whitelist_folder(folder_path, folder_alias, state).await
}

/// 重启文件监控系统命令
#[tauri::command(rename_all = "snake_case", async)]
pub async fn restart_file_monitoring(
    app_state: tauri::State<'_, crate::AppState>,
) -> Result<String, String> {
    println!("[CMD] restart_file_monitoring 命令被调用，开始重启文件监控系统...");
    
    // 1. 获取并重新初始化文件监控器
    let mut monitor = {
        let monitor_guard = app_state.file_monitor.lock().unwrap();
        match &*monitor_guard {
            Some(monitor) => monitor.clone(),
            None => {
                return Err("文件监控器未初始化，无法重启".to_string());
            }
        }
    };
    
    // 2. 重新初始化元数据通道
    if let Err(e) = monitor.start_monitoring_setup_and_initial_scan().await {
        return Err(format!("重新初始化文件监控器失败: {}", e));
    }
    
    // 3. 更新 AppState 中的监控器
    {
        let mut file_monitor_guard = app_state.file_monitor.lock().unwrap();
        *file_monitor_guard = Some(monitor.clone());
        println!("[CMD] restart_file_monitoring 已更新 AppState.file_monitor");
    }
    
    // 4. 重新创建并初始化防抖动监控器
    // 先创建新的防抖动监控器
    let mut debounced_monitor = {
        let monitor_arc = Arc::new(monitor.clone());
        crate::file_monitor_debounced::DebouncedFileMonitor::new(monitor_arc)
    };
    
    // 获取当前的目录列表
    let monitored_dirs = monitor.get_monitored_dirs();
    
    // 更新 AppState 中的防抖动监控器
    {
        let mut debounced_monitor_guard = app_state.debounced_file_monitor.lock().unwrap();
        *debounced_monitor_guard = Some(debounced_monitor.clone());
        println!("[CMD] restart_file_monitoring 已更新 AppState.debounced_file_monitor");
    }
    
    // 启动防抖动监控 - 在 MutexGuard 已经释放后进行
    if let Err(e) = debounced_monitor.start_monitoring(
        monitored_dirs,
        std::time::Duration::from_millis(500)
    ).await {
        return Err(format!("重启防抖动监控失败: {}", e));
    }
    
    println!("[CMD] restart_file_monitoring 已成功启动防抖动监控");
    Ok("文件监控系统已成功重启".to_string())
}
