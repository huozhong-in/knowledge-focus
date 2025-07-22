use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Manager, Emitter};
use tauri::path::BaseDirectory;
use tauri_plugin_shell::{process::CommandEvent, ShellExt};
use tokio::sync::oneshot;
use serde::{Deserialize, Serialize};

/// 桥接事件数据结构
#[derive(Debug, Serialize, Deserialize)]
struct BridgeEventData {
    event: String,
    payload: serde_json::Value,
}

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
        
        // According to dev/production environment, choose different Python paths
        let python_path = if cfg!(debug_assertions) {
            "../../../../api/.venv/bin/python"
        } else {
            // Production environment - use Python from venv directory
            "./venv/bin/python" // Assuming venv is bundled relative to the executable
        };
        println!("Python路径: {}", python_path);

        let sidecar_result = app_handle.shell().sidecar(python_path);

        let sidecar = match sidecar_result {
            //打印调试信息，sidecar的绝对路径
            Ok(s) => {
                // println!("成功找到sidecar: {:?}", s);
                s
            },
            Err(e) => {
                eprintln!("无法找到sidecar: {}", e);
                if let Some(window) = app_handle.get_webview_window("main") {
                    let _ = window.emit("api-process-error", Some(format!("无法找到sidecar: {}", e)));
                }
                // API启动失败，发送失败信号
                if let Some(sender) = tx.lock().unwrap().take() {
                    let _ = sender.send(false);
                }
                return;
            }
        };
        
        // Use Tauri's resource path API to handle script path
        // 检查是否在lldb调试模式下运行 - 因为debug模式和dev模式的当前工作目录不同
        let script_path = if cfg!(debug_assertions) {
            if std::env::var("LLDB_DEBUGGER").is_ok() {
                // LLDB调试模式
                "./api/main.py".to_string()
            } else {
                // 普通开发模式
                "../../api/main.py".to_string()
                // "../../api/bridge_events.py".to_string()
            }
        } else {
            // Production environment - use resource path API
            match app_handle
                .path()
                .resolve("api/main.py", BaseDirectory::Resource)
            {
                Ok(p) => p.to_string_lossy().to_string(),
                Err(e) => {
                    eprintln!("无法解析资源路径: {}", e);
                    if let Some(window) = app_handle.get_webview_window("main") {
                        let _ = window.emit(
                            "api-process-error",
                            Some(format!("无法解析资源路径: {}", e)),
                        );
                    }
                    // API启动失败，发送失败信号
                    if let Some(sender) = tx.lock().unwrap().take() {
                        let _ = sender.send(false);
                    }
                    return;
                }
            }
        };
        println!("脚本路径: {}", script_path);

        // 构造基础参数
        let mut args = vec![
            script_path.clone(),
            "--port".to_string(),
            port_to_use.to_string(),
            "--host".to_string(),
            host_to_use.clone(),
            "--db-path".to_string(),
            db_path_to_use.clone(),
        ];

        // 如果是开发环境，添加 --mode=dev 参数
        if cfg!(debug_assertions) {
            args.push("--mode".to_string());
            args.push("dev".to_string());
        }

        let command = sidecar.args(&args);
        println!("命令行: {:?}", command);

        match command.spawn() {
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
                let api_url = format!("http://{}:{}/health", host_to_use, port_to_use);
                let tx_for_health = Arc::clone(&tx);
                
                tauri::async_runtime::spawn(async move {
                    // 尝试等待API启动并健康检查通过
                    let client = reqwest::Client::new();
                    let max_retries = 30; // 最多尝试30次
                    let retry_interval = std::time::Duration::from_millis(500); // 每500ms检查一次
                    
                    for _ in 0..max_retries {
                        match client.get(&api_url).timeout(std::time::Duration::from_secs(1)).send().await {
                            Ok(response) if response.status().is_success() => {
                                println!("API健康检查成功，API准备就绪");
                                // API准备好了，发送成功信号到内部通道
                                // 不再向主窗口发送信号，统一由 lib.rs 处理
                                if let Some(sender) = tx_for_health.lock().unwrap().take() {
                                    let _ = sender.send(true);
                                }
                                break;
                            }
                            _ => {
                                // API尚未准备好，等待后重试
                                tokio::time::sleep(retry_interval).await;
                            }
                        }
                    }
                });
                
                // 监听API进程事件
                tauri::async_runtime::spawn(async move {
                    while let Some(event) = rx.recv().await {
                        if let Some(window) = app_handle_clone.get_webview_window("main") {
                            match event {
                                CommandEvent::Stdout(line) => {
                                    let line_str = String::from_utf8_lossy(&line);
                                    
                                    // 检查是否是桥接事件通知
                                    if let Some(event_data) = parse_bridge_event(&line_str) {
                                        // 这是一个标准化的桥接事件，转发给前端
                                        let payload = if event_data.payload.is_null() {
                                            None
                                        } else {
                                            Some(event_data.payload)
                                        };
                                        println!("桥接事件已转发: {} -> {:?}", event_data.event, payload);
                                        let _ = window.emit(&event_data.event, payload);
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
