mod commands;
mod file_monitor;
mod file_monitor_debounced; // 防抖动文件监控模块
mod file_scanner; // 文件扫描模块
mod setup_file_monitor;
mod api_startup; // API启动模块
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use tauri::Emitter;
use tauri::Manager;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    WindowEvent,
};
use tokio::time::{sleep, Duration};
use file_monitor::FileMonitor;
use file_monitor_debounced::DebouncedFileMonitor;
use reqwest;
// use serde::{Deserialize, Serialize};
// use futures_util::StreamExt;
// use tauri::Window;

// #[derive(Serialize, Deserialize, Debug, Clone)]
// struct Message {
//     id: String,
//     role: String,
//     content: String,
// }

// #[tauri::command]
// async fn ask_ai_stream_bridge(window: Window, messages: Vec<Message>) -> Result<(), String> {
//     let client = reqwest::Client::new();
//     // Your Python Sidecar address
//     let sidecar_url = "http://127.0.0.1:60315/chat/stream";

//     let mut stream = client.post(sidecar_url)
//         .json(&messages)
//         .send().await.map_err(|e| e.to_string())?
//         .bytes_stream();

//     while let Some(item) = stream.next().await {
//         match item {
//             Ok(bytes) => {
//                 if let Ok(chunk) = std::str::from_utf8(&bytes) {
//                     // Emit each chunk as an event
//                     window.emit("ai_chunk", chunk).unwrap();
//                 }
//             },
//             Err(e) => {
//                 eprintln!("Error in stream: {}", e);
//                 break;
//             }
//         }
//     }

//     // Notify the frontend that the stream has ended
//     window.emit("ai_stream_end", ()).unwrap();
//     Ok(())
// }


// 存储API进程的状态
struct ApiProcessState {
    process_child: Option<tauri_plugin_shell::process::CommandChild>,
    port: u16,
    host: String,
    db_path: String,
}

// API进程管理器，用于应用退出时自动清理资源
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
    debounced_file_monitor: Arc<Mutex<Option<DebouncedFileMonitor>>>,
    // 配置变更队列管理
    pending_config_changes: Arc<Mutex<Vec<ConfigChangeRequest>>>,
    initial_scan_completed: Arc<Mutex<bool>>,
}

impl AppState {
    fn new() -> Self {
        Self {
            config: Arc::new(Mutex::new(None)),
            file_monitor: Arc::new(Mutex::new(None)),
            debounced_file_monitor: Arc::new(Mutex::new(None)), // 初始化新字段
            pending_config_changes: Arc::new(Mutex::new(Vec::new())), // 初始化配置变更队列
            initial_scan_completed: Arc::new(Mutex::new(false)), // 初始化扫描完成标志
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
    
    // 配置变更队列管理方法
    
    /// 检查首次扫描是否已完成
    pub fn is_initial_scan_completed(&self) -> bool {
        let completed = self.initial_scan_completed.lock().unwrap();
        *completed
    }
    
    /// 设置首次扫描完成状态
    pub fn set_initial_scan_completed(&self, completed: bool) {
        let mut scan_completed = self.initial_scan_completed.lock().unwrap();
        *scan_completed = completed;
        
        // 如果扫描完成，处理待处理的配置变更
        if completed {
            println!("[CONFIG_QUEUE] 首次扫描完成，开始处理待处理的配置变更");
            self.process_pending_config_changes();
        }
    }
    
    /// 添加配置变更请求到队列
    pub fn add_pending_config_change(&self, change: ConfigChangeRequest) {
        let mut pending_changes = self.pending_config_changes.lock().unwrap();
        pending_changes.push(change.clone());
        println!("[CONFIG_QUEUE] 添加配置变更到队列: {:?}", change);
    }
    
    /// 检查是否有待处理的配置变更
    pub fn has_pending_config_changes(&self) -> bool {
        let pending_changes = self.pending_config_changes.lock().unwrap();
        !pending_changes.is_empty()
    }
    
    /// 获取待处理的配置变更数量
    pub fn get_pending_config_changes_count(&self) -> usize {
        let pending_changes = self.pending_config_changes.lock().unwrap();
        pending_changes.len()
    }
    
    /// 处理所有待处理的配置变更（由Rust端调用Python API）
    pub fn process_pending_config_changes(&self) {
        let changes = {
            let mut pending_changes = self.pending_config_changes.lock().unwrap();
            let changes = pending_changes.clone();
            pending_changes.clear(); // 清空队列
            changes
        };
        
        if changes.is_empty() {
            return;
        }
        
        println!("[CONFIG_QUEUE] 开始处理 {} 个待处理的配置变更", changes.len());
        
        // 在独立的异步任务中处理配置变更
        let changes_clone = changes.clone();
        let file_monitor = self.file_monitor.clone();
        
        tauri::async_runtime::spawn(async move {
            Self::execute_config_changes(changes_clone, file_monitor).await;
        });
    }
    
    /// 执行配置变更（静态方法，可在异步任务中调用）
    async fn execute_config_changes(
        changes: Vec<ConfigChangeRequest>,
        file_monitor: Arc<Mutex<Option<FileMonitor>>>,
    ) {
        println!("[CONFIG_QUEUE] 开始执行 {} 个配置变更", changes.len());
        
        // 获取文件监控器
        let monitor = {
            let guard = file_monitor.lock().unwrap();
            match &*guard {
                Some(monitor) => monitor.clone(),
                None => {
                    eprintln!("[CONFIG_QUEUE] 文件监控器未初始化，无法执行配置变更");
                    return;
                }
            }
        };
        
        // 记录执行失败的变更，以便后续处理
        let mut failed_changes = Vec::new();
        
        // 执行所有变更
        for change in changes {
            match Self::execute_single_config_change(&change, &monitor).await {
                Ok(_) => {
                    println!("[CONFIG_QUEUE] 成功执行配置变更: {:?}", change);
                }
                Err(e) => {
                    eprintln!("[CONFIG_QUEUE] 执行配置变更失败: {:?}, 错误: {}", change, e);
                    failed_changes.push((change, e));
                }
            }
            
            // 每个变更之间短暂暂停，避免请求过于密集
            sleep(Duration::from_millis(200)).await;
        }
        
        // 执行完所有变更后，刷新监控配置（增加重试逻辑）
        let mut refresh_success = false;
        let max_retries = 3;
        
        for retry in 1..=max_retries {
            // 保证在刷新配置前有足够的暂停时间让API服务器恢复
            sleep(Duration::from_secs(1)).await;
            
            println!("[CONFIG_QUEUE] 尝试刷新配置 ({}/{})", retry, max_retries);
            match monitor.refresh_all_configurations().await {
                Ok(_) => {
                    println!("[CONFIG_QUEUE] 所有配置变更执行完成，监控配置已刷新");
                    refresh_success = true;
                    break;
                }
                Err(e) => {
                    eprintln!("[CONFIG_QUEUE] 刷新监控配置失败 ({}/{}): {}", retry, max_retries, e);
                    if retry < max_retries {
                        println!("[CONFIG_QUEUE] 将在 {} 秒后重试刷新配置", retry);
                        sleep(Duration::from_secs(retry)).await;
                    }
                }
            }
        }
        
        if !refresh_success {
            eprintln!("[CONFIG_QUEUE] 严重警告: 配置刷新失败，系统可能处于不一致状态！");
            // 这里可以添加额外的恢复步骤或通知用户
        }
        
        // 报告失败的变更
        if !failed_changes.is_empty() {
            eprintln!("[CONFIG_QUEUE] 注意: {} 个配置变更执行失败，可能需要用户手动操作", failed_changes.len());
            // 这里可以实现更多的失败处理逻辑，例如通知用户
        }
    }
    
    /// 执行单个配置变更
    async fn execute_single_config_change(
        change: &ConfigChangeRequest,
        monitor: &FileMonitor,
    ) -> Result<(), String> {
        match change {
            ConfigChangeRequest::DeleteFolder { folder_path, is_blacklist, .. } => {
                // 如果删除的是黑名单文件夹，清理相关粗筛数据
                if *is_blacklist {
                    // 添加重试逻辑确保清理操作完成
                    let max_retries = 3;
                    let mut retry_count = 0;
                    let mut last_error = String::new();
                    
                    while retry_count < max_retries {
                        match Self::cleanup_screening_data_for_path(folder_path, monitor).await {
                            Ok(_) => {
                                println!("[CONFIG_QUEUE] 成功清理路径 {} 的粗筛数据", folder_path);
                                break;
                            },
                            Err(e) => {
                                last_error = e.to_string();
                                retry_count += 1;
                                if retry_count < max_retries {
                                    println!("[CONFIG_QUEUE] 清理粗筛数据失败，将重试 ({}/{}): {}", 
                                             retry_count, max_retries, last_error);
                                    sleep(Duration::from_millis(500 * retry_count)).await;
                                }
                            }
                        }
                    }
                    
                    if retry_count == max_retries {
                        return Err(format!("清理粗筛数据失败: {}", last_error));
                    }
                }
                
                // 对于文件夹删除，主要工作已在前端完成，这里主要是确保监控状态同步
                println!("[CONFIG_QUEUE] 文件夹删除变更处理完成: {}", folder_path);
                Ok(())
            }
            
            ConfigChangeRequest::AddBlacklist { folder_path, .. } => {
                // 清理新增黑名单路径的粗筛数据，同样添加重试机制
                let max_retries = 3;
                let mut retry_count = 0;
                let mut last_error = String::new();
                
                while retry_count < max_retries {
                    match Self::cleanup_screening_data_for_path(folder_path, monitor).await {
                        Ok(_) => {
                            println!("[CONFIG_QUEUE] 成功清理黑名单路径 {} 的粗筛数据", folder_path);
                            break;
                        },
                        Err(e) => {
                            last_error = e.to_string();
                            retry_count += 1;
                            if retry_count < max_retries {
                                println!("[CONFIG_QUEUE] 清理黑名单粗筛数据失败，将重试 ({}/{}): {}", 
                                         retry_count, max_retries, last_error);
                                sleep(Duration::from_millis(500 * retry_count)).await;
                            }
                        }
                    }
                }
                
                if retry_count == max_retries {
                    return Err(format!("清理黑名单粗筛数据失败: {}", last_error));
                }
                
                println!("[CONFIG_QUEUE] 黑名单文件夹添加变更处理完成: {}", folder_path);
                Ok(())
            }
            
            ConfigChangeRequest::ToggleFolder { folder_path, is_blacklist, .. } => {
                if *is_blacklist {
                    // 转为黑名单时清理粗筛数据
                    Self::cleanup_screening_data_for_path(folder_path, monitor).await?;
                } else {
                    // 转为白名单时执行增量扫描
                    monitor.scan_single_directory(folder_path).await?;
                }
                println!("[CONFIG_QUEUE] 文件夹状态切换变更处理完成: {}", folder_path);
                Ok(())
            }
            
            ConfigChangeRequest::AddWhitelist { folder_path, .. } => {
                // 新增白名单文件夹时执行增量扫描
                monitor.scan_single_directory(folder_path).await?;
                println!("[CONFIG_QUEUE] 白名单文件夹添加变更处理完成: {}", folder_path);
                Ok(())
            }
            
            ConfigChangeRequest::BundleExtensionChange => {
                // Bundle扩展名变更通常需要重启生效，这里只记录
                println!("[CONFIG_QUEUE] Bundle扩展名变更处理完成，重启应用后生效");
                Ok(())
            }
        }
    }
    
    /// 清理指定路径的粗筛数据（调用Python API）
    async fn cleanup_screening_data_for_path(
        folder_path: &str,
        monitor: &FileMonitor,
    ) -> Result<(), String> {
        let api_url = format!("http://{}:{}/screening/clean-by-path", monitor.get_api_host(), monitor.get_api_port());
        
        println!("[CLEANUP] 开始清理路径 {} 的粗筛数据", folder_path);
        
        // 创建一个更长超时设置的客户端
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(30))  // 设置30秒超时
            .build()
            .map_err(|e| format!("创建HTTP客户端失败: {}", e))?;
            
        let response = client
            .post(&api_url)
            .json(&serde_json::json!({ 
                "path": folder_path,
                // 添加额外的请求元数据，帮助调试
                "request_time": chrono::Utc::now().to_rfc3339(),
                "client_id": "rust_file_monitor"
            }))
            .send()
            .await
            .map_err(|e| format!("清理粗筛数据请求失败: {}", e))?;
        
        let status = response.status();
        if status.is_success() {
            // 获取响应体并解析
            let result = response.json::<serde_json::Value>().await
                .map_err(|e| format!("解析清理响应失败: {}", e))?;
            
            // 从响应中提取删除的记录数
            let deleted_count = result.get("deleted")
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
                
            println!("[CLEANUP] 成功清理路径 {} 的粗筛数据，删除 {} 条记录", 
                folder_path, deleted_count);
                
            // 额外的验证: 如果应该有记录被删除但返回0，可能要警告
            if folder_path.contains("Pictures") && deleted_count == 0 {
                println!("[CLEANUP] 警告: 清理图片目录相关的粗筛数据，但未删除任何记录");
            }
            
            Ok(())
        } else {
            // 处理错误响应
            let error_text = response.text().await
                .unwrap_or_else(|_| "无法读取错误响应".to_string());
                
            let error_msg = format!("清理粗筛数据失败 (状态码: {}): {}", status, error_text);
            eprintln!("[CLEANUP] {}", error_msg);
            Err(error_msg)
        }
    }
}

// 配置变更请求类型
#[derive(Debug, Clone)]
pub enum ConfigChangeRequest {
    // 添加黑名单文件夹
    AddBlacklist {
        parent_id: i32,
        folder_path: String,
        folder_alias: Option<String>,
    },
    // 删除文件夹
    DeleteFolder {
        folder_id: i32,
        folder_path: String,
        is_blacklist: bool,
    },
    // 添加白名单文件夹
    AddWhitelist {
        folder_path: String,
        folder_alias: Option<String>,
    },
    // 切换文件夹黑白名单状态
    ToggleFolder {
        folder_id: i32,
        is_blacklist: bool,
        folder_path: String,
    },
    // Bundle扩展名变更
    BundleExtensionChange,
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
                
                // 简化的 API 就绪信号发送逻辑
                // 发送信号到内部通道 (用于文件监控启动等)
                let _api_ready_sent = {
                    let mut lock = tx_for_api.lock().unwrap();
                    if let Some(sender) = lock.take() {
                        let send_result = sender.send(api_ready);
                        println!("已发送内部API就绪信号: {}", api_ready);
                        send_result.is_ok() && api_ready
                    } else {
                        false
                    }
                };
                
                // API 就绪时发送给主窗口，简化了条件检查
                if api_ready {
                    println!("Python API 已完全就绪，向主窗口发送 API 就绪信号");
                    
                    // 获取主窗口句柄并发送就绪事件
                    if let Some(main) = app_handle_for_api.get_webview_window("main") {
                        // 向主窗口发送 API 就绪事件，这里是唯一发送位置
                        let _ = main.emit("api-ready", true);
                        println!("已向主窗口发送 API 就绪信号");
                    } else {
                        eprintln!("找不到主窗口，无法发送 API 就绪信号");
                    }
                }
            });
            
            // 等待API就绪信号后再初始化文件监控基础设施（但不开始扫描）
            let app_handle_for_monitor = app_handle.clone();
            let monitor_state = Arc::clone(&app.state::<Arc<Mutex<Option<FileMonitor>>>>());
            let api_state_for_monitor = api_state_instance.0.clone();
            
            // 等待API就绪信号后再准备文件监控基础设施
            tauri::async_runtime::spawn(async move {
                // 等待API就绪信号
                match rx.await {
                    Ok(true) => {
                        println!("收到API就绪信号，准备文件监控基础设施（不开始扫描）...");
                        // 初始化文件监控基础设施，但不开始自动扫描
                        crate::setup_file_monitor::setup_file_monitoring_infrastructure(
                            app_handle_for_monitor,
                            monitor_state,
                            api_state_for_monitor,
                        ).await;
                    },
                    _ => {
                        eprintln!("API未能成功启动，无法初始化文件监控基础设施");
                        if let Some(window) = app_handle_for_monitor.get_webview_window("main") {
                            let _ = window.emit("file-monitor-error", "API未就绪，无法初始化文件监控");
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
            commands::chat,
            commands::resolve_directory_from_path,
            commands::get_file_monitor_stats,
            commands::scan_directory, // 添加目录后扫描目录
            commands::stop_monitoring_directory, // 停止监控指定目录
            commands::restart_file_monitoring, // 重启文件监控系统
            // 文件夹层级管理命令
            commands::add_blacklist_folder,
            commands::remove_blacklist_folder,
            commands::get_folder_hierarchy,
            // 配置刷新管理命令
            commands::refresh_monitoring_config,
            commands::get_bundle_extensions,
            commands::get_configuration_summary,
            commands::read_directory, // 读取目录内容
            // 标签管理命令
            commands::get_tag_cloud_data, // 获取标签云数据
            // 配置变更队列管理命令（新版：使用queue_前缀）
            commands::queue_add_blacklist_folder,
            commands::queue_delete_folder,
            commands::queue_toggle_folder_status, 
            commands::queue_add_whitelist_folder,
            commands::queue_get_status,
            // 配置变更队列管理命令（兼容旧版）
            commands::add_blacklist_folder_queued,
            commands::remove_folder_queued,
            commands::toggle_folder_status_queued,
            commands::add_whitelist_folder_queued,
            commands::get_config_queue_status,
            file_scanner::scan_files_by_time_range,
            file_scanner::scan_files_by_type,
            file_scanner::start_backend_scanning, // 后端扫描启动命令
            commands::search_files_by_tags,
            commands::ask_ai_stream_bridge,
        ])
        .on_window_event(|window, event| match event {
            WindowEvent::Destroyed => {
                // 获取窗口的标牌，区分是哪个窗口被销毁
                let window_label = window.label();
                
                // 我们不再需要在这里手动终止 API 进程，因为 ApiProcessManager 的 Drop 实现会在应用退出时自动处理
                // 只记录窗口被销毁的事件
                println!("窗口被销毁: {}", window_label);
            }
            WindowEvent::CloseRequested { api, .. } => {
                // 获取窗口的标牌，用于区分不同窗口
                let window_label = window.label();
                
                // 针对不同窗口采取不同的关闭策略
                match window_label {
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
