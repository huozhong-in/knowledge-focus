use std::collections::HashMap;
use std::sync::{Arc, Mutex};
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
use reqwest; // 导入reqwest用于API健康检查

// 存储API进程的状态
struct ApiProcessState {
    process_child: Option<tauri_plugin_shell::process::CommandChild>,
    port: u16,
    host: String,
    db_path: String,
}

// 新增：API进程管理器，用于应用退出时自动清理资源
struct ApiProcessManager {
    api_state: Arc<Mutex<ApiProcessState>>,
}

// 实现 Drop trait，在应用退出时自动终止 API 进程
impl Drop for ApiProcessManager {
    fn drop(&mut self) {
        println!("应用程序退出，ApiProcessManager.drop() 被调用");
        // 尝试获取并终止 API 进程
        if let Ok(mut api_state) = self.api_state.lock() {
            if let Some(child) = api_state.process_child.take() {
                println!("通过 Drop trait 自动终止 Python API 进程");
                let _ = child.kill();
                println!("Python API 进程已终止");
            } else {
                println!("没有需要终止的 Python API 进程");
            }
        } else {
            eprintln!("无法获取 API 状态互斥锁");
        }
    }
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
            
            // 创建 ApiProcessManager 并注册到应用，用于应用退出时自动清理 API 进程
            let api_manager = ApiProcessManager {
                api_state: api_state_instance.0.clone(),
            };
            app_handle.manage(api_manager);
            println!("已注册 ApiProcessManager，将在应用退出时自动清理 API 进程");
            
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
                api_state_guard.port = 60315;
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
                        
                        // API 准备就绪，通知 splashscreen 并处理窗口切换
                        if api_ready {
                            // 获取窗口句柄
                            let splashscreen_window = app_handle_for_api.get_webview_window("splashscreen");
                            let main_window = app_handle_for_api.get_webview_window("main");
                            
                            if let (Some(splash), Some(main)) = (splashscreen_window, main_window) {
                                // 向 splashscreen 发送就绪事件
                                let _ = splash.emit("api-ready", true);
                                
                                // 延迟一小段时间后关闭 splashscreen 并显示主窗口
                                let splash_clone = splash.clone();
                                let main_clone = main.clone();
                                tauri::async_runtime::spawn(async move {
                                    // 给 splashscreen 一点时间展示 API 已就绪的消息
                                    tokio::time::sleep(std::time::Duration::from_millis(800)).await;
                                    
                                    // 显示主窗口并关闭 splashscreen
                                    if let Err(e) = main_clone.show() {
                                        eprintln!("显示主窗口失败: {}", e);
                                    }
                                    
                                    // 再延迟一点时间后关闭 splashscreen，确保主窗口已显示
                                    tokio::time::sleep(std::time::Duration::from_millis(200)).await;
                                    if let Err(e) = splash_clone.close() {
                                        eprintln!("关闭 splashscreen 失败: {}", e);
                                    }
                                });
                            }
                        }
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
            // 在托盘菜单事件中处理退出操作
            let tray_icon = TrayIconBuilder::new()
                .menu(&menu)
                .show_menu_on_left_click(false) // Changed to false for right-click menu
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "quit" => {
                        println!("退出菜单项被点击");
                        
                        // 终止所有资源并退出应用
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
            port: 60315,
            host: "127.0.0.1".to_string(),
            db_path: String::new(),
        }))))
        // 管理文件监控状态
        .manage(Arc::new(Mutex::new(Option::<FileMonitor>::None)))
        .invoke_handler(tauri::generate_handler![
            get_api_status,
            commands::resolve_directory_from_path,
            commands::get_file_monitor_stats,
            commands::test_bundle_detection,
            commands::scan_directory, // 新增:添加目录后扫描目录
            file_scanner::scan_files_by_time_range,
            file_scanner::scan_files_by_type,
        ])
        .on_window_event(|window, event| match event {
            WindowEvent::Destroyed => {
                // 获取窗口的标签，区分是哪个窗口被销毁
                let window_label = window.label();
                
                // 我们不再需要在这里手动终止 API 进程，因为 ApiProcessManager 的 Drop 实现会在应用退出时自动处理
                // 只记录窗口被销毁的事件
                println!("窗口被销毁: {}", window_label);
            }
            WindowEvent::CloseRequested { api, .. } => {
                // 获取窗口的标签，用于区分不同窗口
                let window_label = window.label();
                
                // 针对不同窗口采取不同的关闭策略
                match window_label {
                    // 对于启动画面，允许正常关闭
                    "splashscreen" => {
                        // 不阻止默认关闭行为，让 splashscreen 能够正常关闭
                        println!("关闭启动画面");
                    }
                    // 对于主窗口，使用隐藏而不是关闭的逻辑
                    "main" => {
                        #[cfg(target_os = "macos")]
                        {
                            // Prevent the default window close behavior
                            api.prevent_close();
                            // Hide the window
                            println!("隐藏主窗口而不是关闭");
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
                    // 对于其他窗口，采用默认行为
                    _ => {
                        println!("关闭其他窗口: {}", window_label);
                    }
                }
            }
            _ => {}
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
