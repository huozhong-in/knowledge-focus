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
mod file_monitor;
mod file_monitor_debounced; // 新增防抖动文件监控模块
mod file_scanner; // 新增文件扫描模块
mod setup_file_monitor;
mod api_startup; // 新增API启动模块
use file_monitor_debounced::DebouncedFileMonitor; // 导入 DebouncedFileMonitor
use file_monitor::FileMonitor;
use tauri_plugin_shell::{process::CommandEvent, ShellExt};
// 导入reqwest用于API健康检查
use reqwest;

// 存储API进程的状态
struct ApiProcessState {
    process_child: Option<tauri_plugin_shell::process::CommandChild>,
    port: u16,
    host: String,
    db_path: String,
}

// API状态包装为线程安全类型
struct ApiState(Arc<Mutex<ApiProcessState>>);

// 应用配置状态，用于存储文件扫描配置
pub struct AppState {
    config: Arc<Mutex<Option<file_monitor::AllConfigurations>>>,
    file_monitor: Arc<Mutex<Option<FileMonitor>>>,
    debounced_file_monitor: Arc<Mutex<Option<DebouncedFileMonitor>>>, // 新增字段
}

impl AppState {
    fn new() -> Self {
        Self {
            config: Arc::new(Mutex::new(None)),
            file_monitor: Arc::new(Mutex::new(None)),
        debounced_file_monitor: Arc::new(Mutex::new(None)), // 初始化新字段
        }
    }

    pub async fn get_config(&self) -> Result<file_monitor::AllConfigurations, String> {
        let config_guard = self.config.lock().unwrap();
        match &*config_guard {
            Some(config) => Ok(config.clone()),
            None => Err("配置未初始化".to_string()),
        }
    }

    pub fn update_config(&self, config: file_monitor::AllConfigurations) {
        let mut config_guard = self.config.lock().unwrap();
        *config_guard = Some(config);
    }
}

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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_window_state::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(
            tauri_plugin_log::Builder::new()
                .level(log::LevelFilter::Info) // 你可以设置一个全局的默认级别，例如 Info
                .level_for("tao", log::LevelFilter::Warn) // 将 tao crate 的日志级别设为 Warn
                .level_for("notify", log::LevelFilter::Info) // Revert to INFO or desired level
                .level_for("notify_debouncer_full", log::LevelFilter::Info) // Revert to INFO or desired level
                .build()
        )
        .plugin(tauri_plugin_single_instance::init(|app, args, cwd| {
            println!(
                "另一个实例已尝试启动，参数: {:?}，工作文件夹: {}",
                args, cwd
            );
            // 使已经运行的窗口获得焦点
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
        // 创建和管理AppState
        .manage(AppState::new())
        .setup(|app| {
            let app_handle = app.handle();
            let api_state_instance = app.state::<ApiState>();
            
            // Start the Python API service automatically
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
                api_state_guard.port = 60000;
                api_state_guard.host = "127.0.0.1".to_string();
                api_state_guard.db_path = db_path_str;
            }
            
            // 启动Python API
            let app_handle_for_api = app_handle.clone();
            let api_state_for_api = api_state_instance.0.clone();
            
            // 创建一个通信通道，实现API就绪后再开始文件监控
            let (tx, rx) = tokio::sync::oneshot::channel::<bool>();
            let tx = Arc::new(Mutex::new(Some(tx)));
            
            // 启动Python API服务
            tauri::async_runtime::spawn(async move {
                let tx_for_api = Arc::clone(&tx);
                
                // 调用api_startup模块中的start_python_api函数
                // 但我们不使用它返回的接收端，因为我们已经创建了自己的通信通道
                let _ = crate::api_startup::start_python_api(app_handle_for_api.clone(), api_state_for_api.clone());
                
                // 获取API主机和端口
                let (api_host, api_port) = {
                    let api_state_guard = api_state_for_api.lock().unwrap();
                    (api_state_guard.host.clone(), api_state_guard.port)
                };
                
                // 构建API健康检查URL
                let api_url = format!("http://{}:{}/health", api_host, api_port);
                println!("开始检查API是否就绪，API健康检查地址: {}", api_url);
                
                // 使用reqwest客户端检查API健康状态
                let client = reqwest::Client::new();
                let max_retries = 30; // 最多尝试30次
                let retry_interval = std::time::Duration::from_millis(500); // 每500ms检查一次
                let mut api_ready = false;
                
                for i in 0..max_retries {
                    // 首先检查API进程是否运行
                    let api_running = {
                        let api_state_guard = api_state_for_api.lock().unwrap();
                        api_state_guard.process_child.is_some()
                    };
                    
                    if !api_running {
                        // 如果进程不存在，等待短暂时间后再次检查
                        tokio::time::sleep(retry_interval).await;
                        continue;
                    }
                    
                    // 尝试访问API健康检查端点
                    match client.get(&api_url)
                        .timeout(std::time::Duration::from_secs(1))
                        .send().await {
                        Ok(response) if response.status().is_success() => {
                            println!("第{}次尝试: API健康检查成功，API已就绪", i + 1);
                            api_ready = true;
                            break;
                        },
                        _ => {
                            // API尚未准备好，等待后重试
                            if (i + 1) % 5 == 0 { // 每5次打印一次，避免日志过多
                                println!("第{}次尝试: API尚未就绪，继续等待...", i + 1);
                            }
                            tokio::time::sleep(retry_interval).await;
                        }
                    }
                }
                
                // 发送API就绪信号
                {
                    let mut lock = tx_for_api.lock().unwrap();
                    if let Some(sender) = lock.take() {
                        let _ = sender.send(api_ready);
                        println!("已发送API就绪信号: {}", api_ready);
                    }
                }
            });
            
            // 在API启动后延迟启动文件监控
            let app_handle_for_monitor = app_handle.clone();
            let monitor_state = Arc::clone(&app.state::<Arc<Mutex<Option<FileMonitor>>>>());
            let api_state_for_monitor = api_state_instance.0.clone();
            
            // 等待API就绪信号后再启动文件监控
            tauri::async_runtime::spawn(async move {
                // 等待API就绪信号
                match rx.await {
                    Ok(true) => {
                        println!("收到API就绪信号，开始启动文件监控...");
                        // 使用setup_file_monitor模块中的函数启动文件监控，不再传递API就绪信号
                        crate::setup_file_monitor::setup_auto_file_monitoring(
                            app_handle_for_monitor,
                            monitor_state,
                            api_state_for_monitor,
                        );
                    },
                    _ => {
                        eprintln!("API未能成功启动，无法启动文件监控");
                        if let Some(window) = app_handle_for_monitor.get_webview_window("main") {
                            let _ = window.emit("file-monitor-error", "API未就绪，无法启动文件监控");
                        }
                    }
                }
            });

            // 设置托盘图标和菜单
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
        // 管理API进程状态
        .manage(ApiState(Arc::new(Mutex::new(ApiProcessState {
            process_child: None,
            port: 60000,
            host: "127.0.0.1".to_string(),
            db_path: String::new(),
        }))))
        // 管理文件监控状态
        .manage(Arc::new(Mutex::new(Option::<FileMonitor>::None)))
        .invoke_handler(tauri::generate_handler![
            get_api_status,
            // start_file_monitoring,
            commands::resolve_directory_from_path,
            commands::get_file_monitor_stats,
            commands::test_bundle_detection,
            commands::scan_directory, // 新增:添加目录后扫描目录
            file_scanner::scan_files_by_time_range,
            file_scanner::scan_files_by_type,
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
