use std::sync::{Arc, Mutex};
use tauri::path::BaseDirectory;
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_shell::{process::CommandEvent, ShellExt};
use tokio::sync::oneshot;

// 引入事件缓冲器
use crate::event_buffer::{BridgeEventData, EventBuffer};

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
pub fn start_python_api(
    app_handle: AppHandle,
    api_state_mutex: Arc<Mutex<crate::ApiProcessState>>,
) -> oneshot::Receiver<bool> {
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
                        if window.is_visible().unwrap_or(false) {
                            let _ = window.emit("api-error", Some(format!("无法获取当前工作目录: {}", e)));
                        }
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
                        if window.is_visible().unwrap_or(false) {
                            let _ = window.emit("api-error", Some(format!("无法获取应用数据目录: {}", e)));
                        }
                    }
                    return;
                }
            }
        };
        println!("venv_parent_path: {:?}", venv_parent_path);

        // 如果是生产环境，复制BaseDirectory::Resource/api/pyproject.toml到app_data_dir
        if !cfg!(debug_assertions) {
            let resource_api_path = match app_handle.path().resolve("api", BaseDirectory::Resource)
            {
                Ok(path) => path,
                Err(e) => {
                    eprintln!("无法解析资源路径: {}", e);
                    if let Some(window) = app_handle.get_webview_window("main") {
                        if window.is_visible().unwrap_or(false) {
                            let _ = window.emit("api-error", Some(format!("无法解析资源路径: {}", e)));
                        }
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
                    let _ = window.emit(
                        "api-error",
                        Some(format!("duplicate pyproject.toml failed: {}", e)),
                    );
                }
                return;
            }
        }

        // 创建或更新虚拟环境
        let sidecar_command = app_handle.shell().sidecar("uv").unwrap().args([
            "sync",
            "--index-strategy",
            "unsafe-best-match",
            "--no-progress",
            "--directory",
            venv_parent_path.to_str().unwrap(),
        ]);
        println!("Running command: {:?}", sidecar_command);

        // 捕获 uv sync 的输出并发送到前端
        match sidecar_command.spawn() {
            Ok((mut sync_rx, _sync_child)) => {
                println!("uv sync 进程已启动");
                if let Some(window) = app_handle.get_webview_window("main") {
                    let _ = window.emit(
                        "api-log",
                        Some("Syncing Python virtual environment...".to_string()),
                    );
                }

                // 监听 uv sync 的输出
                let app_handle_for_sync = app_handle.clone();
                let sync_task = tauri::async_runtime::spawn(async move {
                    while let Some(event) = sync_rx.recv().await {
                        // 检查窗口是否仍然存在，避免向已销毁的窗口发送事件
                        if let Some(window) = app_handle_for_sync.get_webview_window("main") {
                            // 检查窗口是否真的可用（可能已经被销毁但引用仍存在）
                            if window.is_visible().unwrap_or(false) {
                                match event {
                                    CommandEvent::Stdout(line) => {
                                        let line_str = String::from_utf8_lossy(&line);
                                        if window.is_visible().unwrap_or(false) {
                                            let _ = window.emit("api-log", Some(line_str.to_string()));
                                        }
                                    }
                                    CommandEvent::Stderr(line) => {
                                        let line_str = String::from_utf8_lossy(&line);
                                        // uv 命令将正常的进度信息输出到 stderr，所以我们需要区分真正的错误
                                        // 只有包含明确错误关键词的才当作错误处理
                                        if line_str.contains("error")
                                            || line_str.contains("Error")
                                            || line_str.contains("ERROR")
                                            || line_str.contains("failed")
                                            || line_str.contains("Failed")
                                            || line_str.contains("FAILED")
                                        {
                                            if window.is_visible().unwrap_or(false) {
                                                let _ = window.emit("api-error", Some(line_str.to_string()));
                                            }
                                        } else {
                                            // 其他 stderr 输出当作正常日志处理（如下载进度等）
                                            if window.is_visible().unwrap_or(false) {
                                                let _ = window.emit("api-log", Some(line_str.to_string()));
                                            }
                                        }
                                    }
                                    CommandEvent::Terminated(status) => {
                                        println!(
                                            "uv sync 进程终止，状态码: {}",
                                            status.code.unwrap_or(-1)
                                        );
                                        if status.code.unwrap_or(-1) != 0 {
                                            let _ = window.emit(
                                                "api-error",
                                                Some(format!(
                                                    "uv sync failed，exit code: {}",
                                                    status.code.unwrap_or(-1)
                                                )),
                                            );
                                        } else {
                                            let _ = window.emit(
                                                "api-log",
                                                Some(
                                                    "Python virtual environment sync completed"
                                                        .to_string(),
                                                ),
                                            );
                                        }
                                        break;
                                    }
                                    _ => {}
                                }
                            } else {
                                // 窗口不可见，可能已被销毁，停止发送事件
                                println!("主窗口不可见，停止发送 uv sync 日志事件");
                                break;
                            }
                        } else {
                            // 窗口不存在，停止发送事件
                            println!("主窗口不存在，停止发送 uv sync 日志事件");
                            break;
                        }
                    }
                });

                // 等待 uv sync 完成
                sync_task.await.expect("uv sync 任务失败");
            }
            Err(e) => {
                eprintln!("启动 uv sync 失败: {}", e);
                if let Some(window) = app_handle.get_webview_window("main") {
                    if window.is_visible().unwrap_or(false) {
                        let _ = window.emit("api-error", Some(format!("uv sync failed: {}", e)));
                    }
                }
                return;
            }
        }

        // 通过uv运行main.py
        // 如果是开发环境main.py在../api/main.py，否则在BaseDirectory::Resource/api/main.py
        let script_path = if cfg!(debug_assertions) {
            venv_parent_path.join("main.py")
        } else {
            match app_handle
                .path()
                .resolve("api/main.py", BaseDirectory::Resource)
            {
                Ok(path) => path,
                Err(e) => {
                    eprintln!("无法解析main.py路径: {}", e);
                    if let Some(window) = app_handle.get_webview_window("main") {
                        if window.is_visible().unwrap_or(false) {
                            let _ = window.emit("api-error", Some(format!("无法解析main.py路径: {}", e)));
                        }
                    }
                    return;
                }
            }
        };
        println!("main_py_path: {:?}", script_path);

        // 通过uv运行Python脚本
        let sidecar_command = app_handle.shell().sidecar("uv").unwrap().args([
            "run",
            "--directory",
            venv_parent_path.to_str().unwrap(),
            script_path.to_str().unwrap(),
            "--host",
            host_to_use.as_str(),
            "--port",
            port_to_use.to_string().as_str(),
            "--db-path",
            db_path_to_use.as_str(),
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
                        Some("Starting Python API service (uv run)...".to_string()),
                    );
                    let _ = window.emit(
                        "api-log",
                        Some(format!(
                            "Initializing FastAPI server on {}:{}",
                            host_to_use, port_to_use
                        )),
                    );
                }

                let app_handle_clone = app_handle.clone();
                let api_state_mutex_clone = api_state_mutex.clone();

                // 监听API进程事件
                let event_buffer_clone = event_buffer.clone();
                tauri::async_runtime::spawn(async move {
                    while let Some(event) = rx.recv().await {
                        if let Some(window) = app_handle_clone.get_webview_window("main") {
                            // 检查窗口是否仍然可见/有效
                            if !window.is_visible().unwrap_or(false) {
                                println!("FastAPI事件处理: 窗口已不可见，停止发送事件");
                                break;
                            }

                            match event {
                                CommandEvent::Stdout(line) => {
                                    let line_str = String::from_utf8_lossy(&line);

                                    // 检查是否是桥接事件通知
                                    if let Some(event_data) = parse_bridge_event(&line_str) {
                                        // 使用事件缓冲器处理桥接事件
                                        println!(
                                            "收到桥接事件: {} (通过缓冲器处理)",
                                            event_data.event
                                        );
                                        event_buffer_clone.handle_event(event_data).await;
                                    } else {
                                        // 普通的Python日志输出
                                        // println!("Python API: {}", line_str);
                                        if window.is_visible().unwrap_or(false) {
                                            let _ = window.emit("api-log", Some(line_str.to_string()));
                                        }
                                    }
                                }
                                CommandEvent::Stderr(line) => {
                                    let line_str = String::from_utf8_lossy(&line);
                                    // Python/FastAPI 的 stderr 输出需要区分错误和正常信息
                                    // 只有包含明确错误关键词的才当作错误处理
                                    if line_str.contains("error")
                                        || line_str.contains("Error")
                                        || line_str.contains("ERROR")
                                        || line_str.contains("failed")
                                        || line_str.contains("Failed")
                                        || line_str.contains("FAILED")
                                        || line_str.contains("exception")
                                        || line_str.contains("Exception")
                                        || line_str.contains("EXCEPTION")
                                        || line_str.contains("traceback")
                                        || line_str.contains("Traceback")
                                    {
                                        if window.is_visible().unwrap_or(false) {
                                            let _ = window.emit("api-error", Some(line_str.to_string()));
                                        }
                                    } else {
                                        // 其他 stderr 输出当作正常日志处理（如启动信息等）
                                        if window.is_visible().unwrap_or(false) {
                                            let _ = window.emit("api-log", Some(line_str.to_string()));
                                        }
                                    }
                                }
                                CommandEvent::Error(err) => {
                                    eprintln!("Python API进程错误: {}", err);
                                    if window.is_visible().unwrap_or(false) {
                                        let _ = window.emit("api-error", Some(err.to_string()));
                                    }
                                    if let Ok(mut state) = api_state_mutex_clone.lock() {
                                        state.process_child = None;
                                    }
                                }
                                CommandEvent::Terminated(status) => {
                                    println!(
                                        "API进程已终止，状态码: {}",
                                        status.code.unwrap_or(-1)
                                    );
                                    if window.is_visible().unwrap_or(false) {
                                        let _ = window.emit(
                                            "api-log",
                                            Some(format!(
                                                "API process terminated with exit code: {}",
                                                status.code.unwrap_or(-1)
                                            ))
                                        );
                                    }
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
                    if window.is_visible().unwrap_or(false) {
                        let _ = window.emit("api-error", Some(format!("启动API服务失败: {}", e)));
                    }
                }
                // API启动失败，发送失败信号
                if let Some(sender) = tx.lock().unwrap().take() {
                    let _ = sender.send(false);
                }
            }
        }
    });

    rx // 返回接收端
}
