use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use tauri::{
    // Emitter,
    Manager,
    // Window,
};

/// 刷新监控配置（重新获取文件夹配置和Bundle扩展名）
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn refresh_monitoring_config(
    state: tauri::State<'_, crate::AppState>,
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
            println!(
                "[CMD] refresh_monitoring_config 成功，配置摘要: {:?}",
                summary
            );
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

/// 刷新简化配置（重新获取扩展名映射和Bundle配置）
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn refresh_simplified_config(
    state: tauri::State<'_, crate::AppState>,
) -> Result<serde_json::Value, String> {
    println!("[CMD] refresh_simplified_config 被调用");

    match state.refresh_simplified_config().await {
        Ok(()) => {
            // 获取更新后的配置摘要
            match state.get_simplified_config().await {
                Ok(config) => {
                    println!("[CMD] refresh_simplified_config 成功");
                    Ok(serde_json::json!({
                        "status": "success",
                        "message": "简化配置刷新成功",
                        "summary": {
                            "extension_mappings_count": config.extension_mappings.len(),
                            "bundle_extensions_count": config.bundle_extensions.len(),
                            "ignore_patterns_count": config.ignore_patterns.len(),
                            "file_categories_count": config.file_categories.len()
                        }
                    }))
                }
                Err(e) => {
                    eprintln!("[CMD] 获取配置摘要失败: {}", e);
                    Ok(serde_json::json!({
                        "status": "success",
                        "message": "简化配置刷新成功，但无法获取摘要",
                        "error": e
                    }))
                }
            }
        }
        Err(e) => {
            eprintln!("[CMD] refresh_simplified_config 失败: {}", e);
            Err(format!("简化配置刷新失败: {}", e))
        }
    }
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

/// 添加黑名单文件夹到队列（如果初始扫描已完成则立即处理队列）
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn queue_add_blacklist_folder(
    parent_id: i32,
    folder_path: String,
    folder_alias: Option<String>,
    state: tauri::State<'_, crate::AppState>,
    _app_handle: tauri::AppHandle,
) -> Result<serde_json::Value, String> {
    println!(
        "[CMD] queue_add_blacklist_folder 被调用，父ID: {}, 路径: {}",
        parent_id, folder_path
    );

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
    _app_handle: tauri::AppHandle, // 使用下划线前缀表示故意不使用的参数
) -> Result<serde_json::Value, String> {
    println!(
        "[CMD] queue_delete_folder 被调用，ID: {}, 路径: {}, 是否黑名单: {}",
        folder_id, folder_path, is_blacklist
    );

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
    state: tauri::State<'_, crate::AppState>,
) -> Result<serde_json::Value, String> {
    println!(
        "[CMD] queue_toggle_folder_status 被调用，ID: {}, 路径: {}, 设为黑名单: {}",
        folder_id, folder_path, is_blacklist
    );

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
    state: tauri::State<'_, crate::AppState>,
) -> Result<serde_json::Value, String> {
    println!(
        "[CMD] queue_add_whitelist_folder 被调用，路径: {}",
        folder_path
    );

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
    state: tauri::State<'_, crate::AppState>,
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

#[derive(Debug, Deserialize, Serialize)]
pub struct FileInfo {
    pub id: i64,
    pub path: String,
    pub file_name: String,
    pub extension: Option<String>,
    pub tags: Option<Vec<String>>,
}

#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn search_files_by_tags(
    tag_names: Vec<String>,
    operator: String,
    app_handle: tauri::AppHandle,
) -> Result<Vec<FileInfo>, String> {
    println!(
        "[CMD] search_files_by_tags called with tags: {:?}, operator: {}",
        tag_names, operator
    );

    // Get API host and port from state
    let (api_host, api_port) = {
        let api_state = app_handle.state::<crate::ApiState>();
        let api_state_guard = api_state.0.lock().unwrap();
        (api_state_guard.host.clone(), api_state_guard.port)
    };

    // Build the API request
    let client = reqwest::Client::new();
    let url = format!("http://{}:{}/tagging/search-files", api_host, api_port);

    let request_data = serde_json::json!({
        "tag_names": tag_names,
        "operator": operator,
        "limit": 50 // Set a reasonable limit for real-time search
    });

    // Send the POST request
    match client.post(&url).json(&request_data).send().await {
        Ok(response) => {
            if response.status().is_success() {
                match response.json::<Vec<FileInfo>>().await {
                    Ok(files) => {
                        println!("[CMD] search_files_by_tags found {} files", files.len());
                        Ok(files)
                    }
                    Err(e) => Err(format!("Failed to parse response: {}", e)),
                }
            } else {
                let status = response.status();
                let error_text = response
                    .text()
                    .await
                    .unwrap_or_else(|_| "Could not read error response".to_string());
                Err(format!(
                    "API request failed with status {}: {}",
                    status, error_text
                ))
            }
        }
        Err(e) => Err(format!("Failed to send request: {}", e)),
    }
}

/// 获取标签云数据
#[tauri::command(rename_all = "snake_case", async, async_runtime = "tokio")]
pub async fn get_tag_cloud_data(
    limit: Option<u32>,
    app_handle: tauri::AppHandle,
) -> Result<serde_json::Value, String> {
    println!("[CMD] get_tag_cloud_data 被调用，limit: {:?}", limit);

    // 获取API信息
    let (api_host, api_port) = {
        let api_state = app_handle.state::<crate::ApiState>();
        let api_state_guard = api_state.0.lock().unwrap();

        if api_state_guard.process_child.is_none() {
            return Err("API服务未运行".to_string());
        }

        (api_state_guard.host.clone(), api_state_guard.port)
    };

    // 构建API请求
    let client = reqwest::Client::new();
    let mut url = format!("http://{}:{}/tagging/tag-cloud", api_host, api_port);

    // 添加查询参数
    if let Some(lim) = limit {
        url = format!("{}?limit={}", url, lim);
    }

    // 发送GET请求
    match client.get(&url).send().await {
        Ok(response) => {
            if response.status().is_success() {
                match response.json::<serde_json::Value>().await {
                    Ok(response_data) => {
                        // println!("[CMD] get_tag_cloud_data 成功获取标签云响应: {:?}", response_data);
                        Ok(response_data)
                    }
                    Err(e) => Err(format!("解析标签云数据失败: {}", e)),
                }
            } else {
                let status = response.status();
                let error_text = response
                    .text()
                    .await
                    .unwrap_or_else(|_| "无法读取错误响应".to_string());
                Err(format!("API请求失败 [{}]: {}", status, error_text))
            }
        }
        Err(e) => Err(format!("发送请求失败: {}", e)),
    }
}
