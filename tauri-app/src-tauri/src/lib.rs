// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use tauri::path::BaseDirectory;
use tauri::Emitter;
use tauri::Manager;
use tauri_plugin_shell::{process::CommandEvent, ShellExt};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent}, 
    WindowEvent
};

// 存储API进程的状态
struct ApiProcessState {
    process_child: Option<tauri_plugin_shell::process::CommandChild>,
    port: u16,
    host: String,
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

// 启动API服务的命令
#[tauri::command]
async fn start_api_service(
    app: tauri::AppHandle,
    state: tauri::State<'_, ApiState>,
    port: Option<u16>,
    host: Option<String>,
) -> Result<HashMap<String, serde_json::Value>, String> {
    let mut api_state = state.0.lock().unwrap();

    if api_state.process_child.is_some() {
        let mut response = HashMap::new();
        response.insert("running".into(), serde_json::Value::Bool(true));
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
        response.insert(
            "message".into(),
            serde_json::Value::String("API服务已在运行中".into()),
        );
        return Ok(response);
    }

    let port = port.unwrap_or(api_state.port);
    let host = host.unwrap_or_else(|| api_state.host.clone());

    api_state.port = port;
    api_state.host = host.clone();

    // 根据开发/生产环境选择不同的Python路径
    let python_path = if cfg!(debug_assertions) {
        // 开发环境
        "../../../../api/.venv/bin/python"
    } else {
        // 生产环境 - 使用venv目录中的Python
        "./venv/bin/python"
    };

    let sidecar = app
        .shell()
        .sidecar(python_path)
        .map_err(|e| format!("无法找到sidecar: {}", e))?;

    // 使用Tauri的资源路径API处理脚本路径
    let script_path = if cfg!(debug_assertions) {
        // 开发环境 - 直接使用相对路径
        "../../api/main.py".to_string()
    } else {
        // 生产环境 - 使用资源路径API
        let resource_path = app
            .path()
            .resolve("api/main.py", BaseDirectory::Resource)
            .map_err(|e| format!("无法解析资源路径: {}", e))?;

        resource_path.to_string_lossy().to_string()
    };

    println!("Python路径: {}", python_path);
    println!("脚本路径: {}", script_path);

    let command = sidecar.args(&[&script_path, "--port", &port.to_string(), "--host", &host]);

    let (mut rx, child) = command
        .spawn()
        .map_err(|e| format!("启动API服务失败: {}", e))?;

    api_state.process_child = Some(child);

    let window = app.get_webview_window("main").unwrap();

    let app_handle = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    let line_str = String::from_utf8_lossy(&line);
                    println!("Python API: {}", line_str);
                    let _ = window.emit("api-log", Some(line_str.to_string()));
                }
                CommandEvent::Stderr(line) => {
                    let line_str = String::from_utf8_lossy(&line);
                    eprintln!("Python API: {}", line_str);
                    let _ = window.emit("api-error", Some(line_str.to_string()));
                }
                CommandEvent::Error(err) => {
                    eprintln!("进程错误: {}", err);
                    let _ = window.emit("api-process-error", Some(err.to_string()));
                    if let Ok(mut state) = app_handle.state::<ApiState>().0.lock() {
                        state.process_child = None;
                    }
                }
                CommandEvent::Terminated(status) => {
                    println!("API进程已终止，状态码: {}", status.code.unwrap_or(-1));
                    let _ = window.emit("api-terminated", Some(status.code));
                    if let Ok(mut state) = app_handle.state::<ApiState>().0.lock() {
                        state.process_child = None;
                    }
                }
                _ => {}
            }
        }
    });

    let mut response = HashMap::new();
    response.insert("running".into(), serde_json::Value::Bool(true));
    response.insert("port".into(), serde_json::Value::Number(port.into()));
    response.insert("host".into(), serde_json::Value::String(host));
    response.insert(
        "url".into(),
        serde_json::Value::String(format!("http://{}:{}", api_state.host, api_state.port)),
    );
    response.insert(
        "message".into(),
        serde_json::Value::String("API服务已启动".into()),
    );

    Ok(response)
}

// 停止API服务的命令
#[tauri::command]
fn stop_api_service(
    state: tauri::State<ApiState>,
) -> Result<HashMap<String, serde_json::Value>, String> {
    let mut api_state = state.0.lock().unwrap();

    if let Some(child) = api_state.process_child.take() {
        match child.kill() {
            Ok(_) => {
                let mut response = HashMap::new();
                response.insert(
                    "message".into(),
                    serde_json::Value::String("API服务已停止".into()),
                );
                Ok(response)
            }
            Err(e) => Err(format!("无法停止API服务: {}", e)),
        }
    } else {
        let mut response = HashMap::new();
        response.insert(
            "message".into(),
            serde_json::Value::String("API服务未运行".into()),
        );
        Ok(response)
    }
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            // app.set_activation_policy(tauri::ActivationPolicy::Accessory);
            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&quit_i])?;
            let tray_icon = TrayIconBuilder::new()
                // .icon(app.default_window_icon().unwrap().clone())
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
                  }).build(app)?;
            let home_dir_path = app.path().home_dir().expect("failed to get home dir");
            let path = app.path().resolve("knowledge-focus", BaseDirectory::Config)?;
            println!("home dir path: {:?}", home_dir_path);
            println!("path: {:?}", path);
            println!("Tray Icon ID: {:?}", tray_icon.id());
            Ok(())
        })
        .plugin(tauri_plugin_single_instance::init(|app, args, cwd| {
            println!("另一个实例已尝试启动，参数: {:?}，工作目录: {}", args, cwd);
            // 如果要使已经运行的窗口获得焦点，取消下面代码的注释
            if let Some(window) = app.get_webview_window("main") {
                window.show().unwrap();
                window.set_focus().unwrap();
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .manage(ApiState(Arc::new(Mutex::new(ApiProcessState {
            process_child: None,
            port: 60000,
            host: "127.0.0.1".to_string(),
        }))))
        .invoke_handler(tauri::generate_handler![
            greet,
            start_api_service,
            stop_api_service,
            get_api_status,
            set_activation_policy_accessory,
            set_activation_policy_regular
        ])
        .on_window_event(|window, event| match event {
            WindowEvent::CloseRequested { api, .. } => {
                #[cfg(target_os = "macos")]
                {
                    // Prevent the default window close behavior
                    api.prevent_close();
                    // Hide the window
                    window.hide().unwrap();
                    let _ = window.app_handle().set_activation_policy(tauri::ActivationPolicy::Accessory);
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
