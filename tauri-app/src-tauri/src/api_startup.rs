use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Manager, Emitter};
use tauri::path::BaseDirectory;
use tauri_plugin_shell::{process::CommandEvent, ShellExt};
use tokio::sync::oneshot;

// 引入事件缓冲器
use crate::event_buffer::{EventBuffer, BridgeEventData};

/// 解析Python stdout输出中的桥接事件
/// 
/// 支持的格式：
/// EVENT_NOTIFY_JSON:{"event":"event-name","payload":{...}}
/// 
/// 返回解析后的事件数据，如果不是桥接事件则返回None
fn parse_bridge_event(line: &str) -> Option<BridgeEventData> {
    let line = line.trim();
    
    // 检查新格式：EVENT_NOTIFY_JSON:
    if let Some(json_part) = line.strip_prefix("EVENT_NOTIFY_JSON:") {
        match serde_json::from_str::<BridgeEventData>(json_part) {
            Ok(event_data) => {
                return Some(event_data);
            }
            Err(e) => {
                eprintln!("解析桥接事件JSON失败: {} - 原始内容: {}", e, json_part);
                return None;
            }
        }
    }

    // 不是桥接事件
    None
}

// Helper function to start the Python API service
// 返回一个oneshot channel的接收端，当API成功启动且可访问后会发送信号
pub fn start_python_api(app_handle: AppHandle, api_state_mutex: Arc<Mutex<crate::ApiProcessState>>) -> oneshot::Receiver<bool> {
    // 创建一对channel，用于通知API已准备好
    let (tx, rx) = oneshot::channel();
    
    // oneshot发送端不能克隆，但我们可以在开始健康检查前保存它
    let tx = std::sync::Arc::new(std::sync::Mutex::new(Some(tx)));
    
    // 创建事件缓冲器
    let event_buffer = Arc::new(EventBuffer::new(app_handle.clone()));
    
    tauri::async_runtime::spawn(async move {
        let port_to_use: u16;
        let host_to_use: String;
        let db_path_to_use: String;

        {
            // Scope to ensure lock is released
            let api_state_guard = api_state_mutex.lock().unwrap();
            port_to_use = api_state_guard.port;
            host_to_use = api_state_guard.host.clone();
            db_path_to_use = api_state_guard.db_path.clone();
        }

        // 获取当前工作目录，用于调试
        let current_dir = std::env::current_dir()
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|_| "无法获取当前工作目录".to_string());
        println!("当前工作目录: {}", current_dir);
        
        // According to dev/production environment, choose different venv_parent_path: ../api or /path/to/app/app_data_dir
        let venv_parent_path = if cfg!(debug_assertions) {
            // 在当前工作目录的上一级目录中寻找api文件夹
            match std::env::current_dir() {
                Ok(mut path) => {
                    path.pop(); // 移动到上一级目录
                    path.pop(); // 移动到上一级目录
                    path.push("api");
                    path
                }
                Err(e) => {
                    eprintln!("无法获取当前工作目录: {}", e);
                    if let Some(window) = app_handle.get_webview_window("main") {
                        let _ = window.emit("api-process-error", Some(format!("无法获取当前工作目录: {}", e)));
                    }
                    return;
                }
            }
        } else {
            match app_handle.path().app_data_dir() {
                Ok(path) => path,
                Err(e) => {
                    eprintln!("无法获取应用数据目录: {}", e);
                    if let Some(window) = app_handle.get_webview_window("main") {
                        let _ = window.emit("api-process-error", Some(format!("无法获取应用数据目录: {}", e)));
                    }
                    return;
                }
            }
        };
        println!("venv_parent_path: {:?}", venv_parent_path);
        
        // 如果是生产环境，复制BaseDirectory::Resource/api/pyproject.toml到app_data_dir
        if !cfg!(debug_assertions) {
            let resource_api_path = match app_handle.path().resolve("api", BaseDirectory::Resource) {
                Ok(path) => path,
                Err(e) => {
                    eprintln!("无法解析资源路径: {}", e);
                    if let Some(window) = app_handle.get_webview_window("main") {
                        let _ = window.emit("api-process-error", Some(format!("无法解析资源路径: {}", e)));
                    }
                    return;
                }
            };
            let pyproject_src_path = resource_api_path.join("pyproject.toml");
            let pyproject_dest_path = venv_parent_path.join("pyproject.toml");
            println!("pyproject_src_path: {:?}", pyproject_src_path);
            println!("pyproject_dest_path: {:?}", pyproject_dest_path);
            // 总是复制文件，以便在部署新版本后能自动更新虚拟环境
            if let Err(e) = std::fs::copy(&pyproject_src_path, &pyproject_dest_path) {
                eprintln!("复制pyproject.toml失败: {}", e);
                if let Some(window) = app_handle.get_webview_window("main") {
                    let _ = window.emit("api-process-error", Some(format!("复制pyproject.toml失败: {}", e)));
                }
                return;
            }
        }
        
        // 创建或更新虚拟环境
        let sidecar_command = app_handle
        .shell()
        .sidecar("uv")
        .unwrap()
        .args(["sync", "--directory", venv_parent_path.to_str().unwrap()]);
        println!("Running command: {:?}", sidecar_command);
        sidecar_command
        .spawn()
        .expect("Failed to create or update virtual environment");

        // 通过uv运行main.py
        // 如果是开发环境main.py在../api/main.py，否则在BaseDirectory::Resource/api/main.py
        let script_path = if cfg!(debug_assertions) {
            venv_parent_path.join("main.py")
        } else {
            match app_handle.path().resolve("api/main.py", BaseDirectory::Resource) {
                Ok(path) => path,
                Err(e) => {
                    eprintln!("无法解析main.py路径: {}", e);
                    if let Some(window) = app_handle.get_webview_window("main") {
                        let _ = window.emit("api-process-error", Some(format!("无法解析main.py路径: {}", e)));
                    }
                    return;
                }
            }
        };
        println!("app_py_path: {:?}", script_path);
        let sidecar_command = app_handle
        .shell()
        .sidecar("uv")
        .unwrap()
        .args([
            "run", 
            "--directory", venv_parent_path.to_str().unwrap(),
            script_path.to_str().unwrap(), 
            "--host", host_to_use.as_str(), 
            "--port", port_to_use.to_string().as_str(),
            "--db-path", db_path_to_use.as_str(),
            ]);
        println!("Running command: {:?}", sidecar_command);

        match sidecar_command.spawn() {
            Ok((mut rx, child)) => {
                {
                    // Scope to ensure lock is released
                    let mut api_state_guard = api_state_mutex.lock().unwrap();
                    api_state_guard.process_child = Some(child);
                }
                println!(
                    "API服务已启动. Port: {}, Host: {}",
                    port_to_use, host_to_use
                );
                if let Some(window) = app_handle.get_webview_window("main") {
                    let _ = window.emit(
                        "api-log",
                        Some(format!(
                            "API服务已启动. Port: {}, Host: {}",
                            port_to_use, host_to_use
                        )),
                    );
                }

                let app_handle_clone = app_handle.clone();
                let api_state_mutex_clone = api_state_mutex.clone();
                
                // 启动健康检查，在API准备好后发送信号
                // let api_url = format!("http://{}:{}/health", host_to_use, port_to_use);
                // let tx_for_health = Arc::clone(&tx);
                
                // tauri::async_runtime::spawn(async move {
                //     // 尝试等待API启动并健康检查通过
                //     let client = reqwest::Client::new();
                //     let max_retries = 300;
                //     let retry_interval = std::time::Duration::from_millis(500); // 每500ms检查一次
                    
                //     for _ in 0..max_retries {
                //         match client.get(&api_url).timeout(std::time::Duration::from_secs(1)).send().await {
                //             Ok(response) if response.status().is_success() => {
                //                 println!("API健康检查成功，API准备就绪");
                //                 // API准备好了，发送成功信号到内部通道
                //                 // 不再向主窗口发送信号，统一由 lib.rs 处理
                //                 if let Some(sender) = tx_for_health.lock().unwrap().take() {
                //                     let _ = sender.send(true);
                //                 }
                //                 break;
                //             }
                //             _ => {
                //                 // API尚未准备好，等待后重试
                //                 tokio::time::sleep(retry_interval).await;
                //             }
                //         }
                //     }
                // });
                
                // 监听API进程事件
                let event_buffer_clone = event_buffer.clone();
                tauri::async_runtime::spawn(async move {
                    while let Some(event) = rx.recv().await {
                        if let Some(window) = app_handle_clone.get_webview_window("main") {
                            match event {
                                CommandEvent::Stdout(line) => {
                                    let line_str = String::from_utf8_lossy(&line);
                                    
                                    // 检查是否是桥接事件通知
                                    if let Some(event_data) = parse_bridge_event(&line_str) {
                                        // 使用事件缓冲器处理桥接事件
                                        println!("收到桥接事件: {} (通过缓冲器处理)", event_data.event);
                                        event_buffer_clone.handle_event(event_data).await;
                                    } else {
                                        // 普通的Python日志输出
                                        // println!("Python API: {}", line_str);
                                        let _ = window.emit("api-log", Some(line_str.to_string()));
                                    }
                                }
                                CommandEvent::Stderr(line) => {
                                    let line_str = String::from_utf8_lossy(&line);
                                    // eprintln!("Python API Debug: {}", line_str);
                                    let _ = window.emit("api-error", Some(line_str.to_string()));
                                }
                                CommandEvent::Error(err) => {
                                    eprintln!("Python API进程错误: {}", err);
                                    let _ = window.emit("api-process-error", Some(err.to_string()));
                                    if let Ok(mut state) = api_state_mutex_clone.lock() {
                                        state.process_child = None;
                                    }
                                }
                                CommandEvent::Terminated(status) => {
                                    println!(
                                        "API进程已终止，状态码: {}",
                                        status.code.unwrap_or(-1)
                                    );
                                    let _ = window.emit("api-terminated", Some(status.code));
                                    if let Ok(mut state) = api_state_mutex_clone.lock() {
                                        state.process_child = None;
                                    }
                                }
                                _ => {}
                            }
                        }
                    }
                });
            }
            Err(e) => {
                eprintln!("启动API服务失败: {}", e);
                if let Some(window) = app_handle.get_webview_window("main") {
                    let _ = window.emit("api-process-error", Some(format!("启动API服务失败: {}", e)));
                }
                // API启动失败，发送失败信号
                if let Some(sender) = tx.lock().unwrap().take() {
                    let _ = sender.send(false);
                }
            }
        }
    });
    
    rx  // 返回接收端
}
