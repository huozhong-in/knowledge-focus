// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use tauri::path::BaseDirectory;
use tauri::Emitter;
use tauri::Manager;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    WindowEvent,
};
// 导入自定义命令
mod commands;
use tauri_plugin_shell::{process::CommandEvent, ShellExt};
use tauri_plugin_store::StoreBuilder;

// 存储API进程的状态
struct ApiProcessState {
    process_child: Option<tauri_plugin_shell::process::CommandChild>,
    port: u16,
    host: String,
    db_path: String,
}

// API状态包装为线程安全类型
struct ApiState(Arc<Mutex<ApiProcessState>>);

// 获取API状态的命令
#[tauri::command]
fn get_api_status(
    state: tauri::State<ApiState>,
) -> Result<HashMap<String, serde_json::Value>, String> {
    let api_state = state.0.lock().unwrap();
    let mut response = HashMap::new();

    response.insert(
        "running".into(),
        serde_json::Value::Bool(api_state.process_child.is_some()),
    );
    response.insert(
        "port".into(),
        serde_json::Value::Number(api_state.port.into()),
    );
    response.insert(
        "host".into(),
        serde_json::Value::String(api_state.host.clone()),
    );
    response.insert(
        "url".into(),
        serde_json::Value::String(format!("http://{}:{}", api_state.host, api_state.port)),
    );

    Ok(response)
}

// Helper function to start the Python API service
fn start_python_api(app_handle: tauri::AppHandle, api_state_mutex: Arc<Mutex<ApiProcessState>>) {
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

        // According to dev/production environment, choose different Python paths
        let python_path = if cfg!(debug_assertions) {
            // Development environment
            "../../../../api/.venv/bin/python"
        } else {
            // Production environment - use Python from venv directory
            "./venv/bin/python" // Assuming venv is bundled relative to the executable
        };

        let sidecar_result = app_handle.shell().sidecar(python_path);

        let sidecar = match sidecar_result {
            Ok(s) => s,
            Err(e) => {
                eprintln!("无法找到sidecar: {}", e);
                if let Some(window) = app_handle.get_webview_window("main") {
                    let _ =
                        window.emit("api-process-error", Some(format!("无法找到sidecar: {}", e)));
                }
                return;
            }
        };

        // Use Tauri's resource path API to handle script path
        let script_path = if cfg!(debug_assertions) {
            // Development environment - direct relative path
            "../../api/main.py".to_string()
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
                    return;
                }
            }
        };

        println!("Python路径: {}", python_path);
        println!("脚本路径: {}", script_path);
        println!(
            "API Port: {}, Host: {}, DB Path: {}",
            port_to_use, host_to_use, db_path_to_use
        );

        let command = sidecar.args(&[
            &script_path,
            "--port",
            &port_to_use.to_string(),
            "--host",
            &host_to_use,
            "--db-path",
            &db_path_to_use,
        ]);

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
                tauri::async_runtime::spawn(async move {
                    while let Some(event) = rx.recv().await {
                        if let Some(window) = app_handle_clone.get_webview_window("main") {
                            match event {
                                CommandEvent::Stdout(line) => {
                                    let line_str = String::from_utf8_lossy(&line);
                                    println!("Python API: {}", line_str);
                                    let _ = window.emit("api-log", Some(line_str.to_string()));
                                }
                                CommandEvent::Stderr(line) => {
                                    let line_str = String::from_utf8_lossy(&line);
                                    eprintln!("Python API Error: {}", line_str);
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
                    let _ =
                        window.emit("api-process-error", Some(format!("启动API服务失败: {}", e)));
                }
            }
        }
    });
}

#[tauri::command]
fn start_api_service(
    app_handle: tauri::AppHandle,
    state: tauri::State<ApiState>,
    port: u16,
    host: String,
    db_path: String,
) -> Result<HashMap<String, serde_json::Value>, String> {
    // 更新API状态
    {
        let mut api_state_guard = state.0.lock().unwrap();
        api_state_guard.port = port;
        api_state_guard.host = host.clone();
        api_state_guard.db_path = db_path;
    }

    // 检查API服务是否已经在运行
    let already_running = {
        let api_state_guard = state.0.lock().unwrap();
        api_state_guard.process_child.is_some()
    };

    // 如果已经在运行，直接返回状态
    if already_running {
        println!("API服务已经在运行，不需要重新启动");
        return get_api_status(state);
    }

    // 启动API服务
    println!("前端请求启动API服务: port={}, host={}", port, host);
    start_python_api(app_handle, state.0.clone());

    // 返回API状态
    let mut response = HashMap::new();
    response.insert("success".into(), serde_json::Value::Bool(true));
    response.insert(
        "message".into(),
        serde_json::Value::String("API服务启动请求已发送".into()),
    );
    Ok(response)
}

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[tauri::command]
fn set_activation_policy_accessory(app: tauri::AppHandle) {
    #[cfg(target_os = "macos")]
    {
        let _ = app.set_activation_policy(tauri::ActivationPolicy::Accessory);
    }
}

#[tauri::command]
fn set_activation_policy_regular(app: tauri::AppHandle) {
    #[cfg(target_os = "macos")]
    {
        let _ = app.set_activation_policy(tauri::ActivationPolicy::Regular);
    }
}

// 添加更新API端口的命令
#[tauri::command]
fn update_api_port(
    app_handle: tauri::AppHandle,
    port: u16,
) -> Result<HashMap<String, serde_json::Value>, String> {
    if port < 1024 {
        return Err("端口号必须在1024到65535之间".into());
    }

    // 获取设置存储路径
    let store_path = match app_handle.path().app_data_dir() {
        Ok(path) => path.join("settings.json"),
        Err(e) => return Err(format!("无法获取应用数据文件夹: {}", e)),
    };

    // 加载存储
    let store = match StoreBuilder::new(&app_handle, store_path.to_str().unwrap()).build() {
        Ok(store) => store,
        Err(e) => return Err(format!("无法创建设置存储: {}", e)),
    };

    // 保存新的端口设置
    store.set("api_port", port);

    // 保存设置到文件
    if let Err(e) = store.save() {
        return Err(format!("无法保存设置: {}", e));
    }

    // 返回成功消息
    let mut response = HashMap::new();
    response.insert("success".into(), serde_json::Value::Bool(true));
    response.insert(
        "message".into(),
        serde_json::Value::String("API端口设置已保存，重启应用后生效".into()),
    );
    Ok(response)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_window_state::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_log::Builder::new().build())
        .plugin(tauri_plugin_single_instance::init(|app, args, cwd| {
            println!(
                "另一个实例已尝试启动，参数: {:?}，工作文件夹: {}",
                args, cwd
            );
            // 如果要使已经运行的窗口获得焦点，取消下面代码的注释
            if let Some(window) = app.get_webview_window("main") {
                window.show().unwrap();
                window.set_focus().unwrap();
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(tauri_plugin_macos_permissions::init())
        .setup(|app| {
            let app_handle = app.handle();
            let api_state_instance = app.state::<ApiState>();

            // Initialize store for settings
            let store_path = app_handle
                .path()
                .app_data_dir()
                .map_err(|e| e.to_string())?
                .join("settings.json");

            // 修改: 使用 v2 正确的 Store 构建方式
            let mut default_settings = HashMap::new();
            default_settings.insert("api_port".to_string(), serde_json::json!(60000));
            default_settings.insert("api_host".to_string(), serde_json::json!("127.0.0.1"));

            // 创建一个新的 store
            let store_result = StoreBuilder::new(app_handle, store_path.clone()).build();

            // 处理创建 store 的结果
            let store = match store_result {
                Ok(store) => store,
                Err(e) => {
                    eprintln!("创建配置存储失败: {:?}", e);
                    return Err(Box::new(std::io::Error::new(
                        std::io::ErrorKind::Other,
                        e.to_string(),
                    )));
                }
            };

            // 加载存储内容
            let load_result = store.reload();
            match load_result {
                Ok(()) => println!("Successfully loaded store from {:?}", store_path),
                Err(e) => {
                    eprintln!("加载配置文件失败: {:?}, 将使用默认配置", e);
                    // 设置默认值
                    for (key, value) in default_settings {
                        let _ = store.set(key, value);
                    }
                    // 保存默认配置
                    if let Err(e) = store.save() {
                        eprintln!("保存默认配置失败: {:?}", e);
                    }
                }
            }

            // Get port from store, default to 60000
            let configured_port = store
                .get("api_port")
                .and_then(|v| v.as_u64())
                .map(|p| p as u16)
                .unwrap_or(60000);

            let configured_host = store
                .get("api_host")
                .and_then(|v| v.as_str().map(|s| s.to_string()))
                .unwrap_or("127.0.0.1".to_string());

            let db_path_str = app_handle
                .path()
                .app_data_dir()
                .map_err(|e| e.to_string())?
                .join("knowledge-focus.db")
                .to_string_lossy()
                .to_string();

            {
                // Scope for MutexGuard
                let mut api_state_guard = api_state_instance.0.lock().unwrap();
                api_state_guard.port = configured_port;
                api_state_guard.host = configured_host;
                api_state_guard.db_path = db_path_str;
            }
            // Start the Python API service automatically
            start_python_api(app_handle.clone(), api_state_instance.0.clone());

            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&quit_i])?;
            let tray_icon = TrayIconBuilder::new()
                .menu(&menu)
                .show_menu_on_left_click(false) // Changed to false for right-click menu
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "quit" => {
                        println!("quit menu item was clicked");
                        app.exit(0);
                    }
                    _ => {
                        println!("menu item {:?} not handled", event.id);
                    }
                })
                .on_tray_icon_event(|tray, event| match event {
                    // Left click shows and focuses the main window
                    TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } => {
                        let app = tray.app_handle();
                        #[cfg(target_os = "macos")]
                        {
                            let _ = app.set_activation_policy(tauri::ActivationPolicy::Regular);
                            app.show().unwrap();
                            // 确保应用程序被激活
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                        #[cfg(not(target_os = "macos"))]
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    // Right click shows the menu (handled automatically because show_menu_on_left_click is false)
                    TrayIconEvent::Click {
                        button: MouseButton::Right,
                        button_state: MouseButtonState::Up,
                        ..
                    } => {
                        // Menu is shown automatically
                    }
                    _ => {
                        // Other events are ignored
                    }
                })
                .build(app)?;
            println!("Tray Icon ID: {:?}", tray_icon.id());
            Ok(())
        })
        .manage(ApiState(Arc::new(Mutex::new(ApiProcessState {
            process_child: None,
            port: 60000,
            host: "127.0.0.1".to_string(),
            db_path: String::new(),
        }))))
        .invoke_handler(tauri::generate_handler![
            greet,
            get_api_status,
            start_api_service,
            set_activation_policy_accessory,
            set_activation_policy_regular,
            update_api_port,
            commands::resolve_directory_from_path,
        ])
        .on_window_event(|window, event| match event {
            WindowEvent::Destroyed => {
                // When window is destroyed, kill the Python process
                let app = window.app_handle();
                if let Ok(mut api_state) = app.state::<ApiState>().0.lock() {
                    if let Some(child) = api_state.process_child.take() {
                        let _ = child.kill();
                    }
                }
            }
            WindowEvent::CloseRequested { api, .. } => {
                #[cfg(target_os = "macos")]
                {
                    // Prevent the default window close behavior
                    api.prevent_close();
                    // Hide the window
                    window.hide().unwrap();
                    let _ = window
                        .app_handle()
                        .set_activation_policy(tauri::ActivationPolicy::Accessory);
                }
                #[cfg(not(target_os = "macos"))]
                {
                    // On other OS, default behavior is usually fine (exit/hide based on config),
                    // but explicitly exiting might be desired if default is hide.
                    window.app_handle().exit(0);
                }
            }
            _ => {}
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
