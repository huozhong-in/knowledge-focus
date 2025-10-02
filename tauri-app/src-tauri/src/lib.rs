mod api_startup; // API启动模块
mod commands;
mod event_buffer;
mod file_monitor;
mod file_monitor_debounced; // 防抖动文件监控模块
mod file_scanner; // 文件扫描模块
mod setup_file_monitor; // 事件缓冲模块

use file_monitor::FileMonitor;
use file_monitor_debounced::DebouncedFileMonitor;
use reqwest;
use std::sync::{Arc, Mutex};
use tauri::Emitter;
use tauri::Manager;
use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem, Submenu},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    WindowEvent,
};
use tokio::time::{sleep, Duration};

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

impl ApiProcessManager {
    /// 实例清理方法，执行完整的清理逻辑
    pub fn cleanup(&self) {
        println!("执行ApiProcessManager完整清理");
        eprintln!("执行ApiProcessManager完整清理"); // 同时输出到 stderr

        // 尝试获取并终止 API 进程
        if let Ok(mut api_state) = self.api_state.lock() {
            if let Some(child) = api_state.process_child.take() {
                println!("通过实例方法终止 uv 和 Python API 进程树");

                // 由于使用 uv 启动，需要终止整个进程树
                // 先尝试获取进程ID用于进程树清理
                let child_pid = child.pid();
                println!("uv 进程 PID: {}", child_pid);

                // 尝试终止 uv 进程（这会终止直接子进程，但不一定终止孙进程）
                match child.kill() {
                    Ok(_) => {
                        println!("发送终止信号到 uv 进程成功");

                        // 等待短暂时间让进程响应信号
                        std::thread::sleep(std::time::Duration::from_millis(1000));
                    }
                    Err(e) => {
                        eprintln!("终止 uv 进程失败: {}", e);
                    }
                }

                // // 在Unix系统上，强制清理整个进程树和相关进程
                // #[cfg(unix)]
                // {
                //     println!("开始清理 uv 和 Python 进程树");

                //     // 1. 首先尝试通过进程组终止（如果 uv 创建了进程组）
                //     println!("尝试终止进程组...");
                //     let _ = std::process::Command::new("pkill")
                //         .args(["-g", &child_pid.to_string()])
                //         .status();

                //     // 2. 使用 pgrep 找到所有 uv 相关的子进程并终止
                //     println!("查找并终止 uv 的所有子进程...");
                //     if let Ok(output) = std::process::Command::new("pgrep")
                //         .args(["-P", &child_pid.to_string()])
                //         .output() {
                //         let children_pids = String::from_utf8_lossy(&output.stdout);
                //         for pid_str in children_pids.lines() {
                //             if let Ok(pid) = pid_str.parse::<u32>() {
                //                 println!("终止子进程 PID: {}", pid);
                //                 let _ = std::process::Command::new("kill")
                //                     .args(["-TERM", &pid.to_string()])
                //                     .status();
                //             }
                //         }
                //     }

                //     // 3. 等待一下后强制终止
                //     std::thread::sleep(std::time::Duration::from_millis(500));

                //     // 4. 使用精确的进程命令行匹配来清理 Python 进程
                //     println!("使用命令行匹配清理 Python 进程...");
                //     let cleanup_patterns = [
                //         "main.py --host 127.0.0.1 --port 60315",
                //         "/api/main.py",
                //         "knowledge-focus.db",
                //     ];

                //     for pattern in &cleanup_patterns {
                //         println!("清理匹配模式: {}", pattern);
                //         // 先发送 SIGTERM
                //         let _ = std::process::Command::new("pkill")
                //             .args(["-f", pattern])
                //             .status();
                //     }

                //     // 5. 等待后强制终止
                //     std::thread::sleep(std::time::Duration::from_millis(1000));
                //     for pattern in &cleanup_patterns {
                //         let _ = std::process::Command::new("pkill")
                //             .args(["-9", "-f", pattern])
                //             .status();
                //     }

                //     // 6. 最后清理 uv 进程本身（以防还在运行）
                //     println!("最终清理 uv 进程: {}", child_pid);
                //     let _ = std::process::Command::new("kill")
                //         .args(["-9", &child_pid.to_string()])
                //         .status();

                //     println!("进程树清理完成");
                // }

                println!("API 进程树终止完成");
            } else {
                println!("没有需要终止的 API 进程");
            }
        } else {
            eprintln!("无法获取 API 状态互斥锁");
        }

        // 执行静态清理作为后备
        Self::cleanup_processes_static();
    }

    /// 静态清理方法，可以在任何地方调用（后备清理）
    pub fn cleanup_processes() {
        Self::cleanup_processes_static();
    }

    /// 静态清理的实际实现
    fn cleanup_processes_static() {
        println!("执行静态进程清理");
        eprintln!("执行静态进程清理"); // 同时输出到 stderr

        // 在Unix系统上，强制清理所有相关的进程
        #[cfg(unix)]
        {
            println!("开始强制清理所有相关的 uv 和 Python 进程");

            // 使用多种模式确保清理干净，包括 uv 进程
            let cleanup_patterns = [
                "uv run --directory",
                "main.py --host 127.0.0.1 --port 60315",
                "/api/main.py",
                "knowledge-focus.db",
            ];

            for pattern in &cleanup_patterns {
                println!("清理模式: {}", pattern);

                // 先发送SIGTERM
                match std::process::Command::new("pkill")
                    .args(["-f", pattern])
                    .status()
                {
                    Ok(status) => {
                        println!("SIGTERM 发送结果: {:?}", status);
                    }
                    Err(e) => {
                        println!("SIGTERM 发送失败: {}", e);
                    }
                }

                // 等待一秒后发送SIGKILL
                std::thread::sleep(std::time::Duration::from_millis(1000));
                match std::process::Command::new("pkill")
                    .args(["-9", "-f", pattern])
                    .status()
                {
                    Ok(status) => {
                        println!("SIGKILL 发送结果: {:?}", status);
                    }
                    Err(e) => {
                        println!("SIGKILL 发送失败: {}", e);
                    }
                }
            }

            println!("静态进程清理完成");
            eprintln!("静态进程清理完成");
        }
    }
}

// 实现 Drop trait，在应用退出时自动终止 API 进程
impl Drop for ApiProcessManager {
    fn drop(&mut self) {
        println!("应用程序退出，ApiProcessManager.drop() 被调用");
        eprintln!("应用程序退出，ApiProcessManager.drop() 被调用"); // 同时输出到 stderr

        // 调用实例清理方法
        self.cleanup();
    }
}

// API状态包装为线程安全类型
struct ApiState(Arc<Mutex<ApiProcessState>>);

// 应用配置状态，用于存储文件扫描配置
pub struct AppState {
    config: Arc<Mutex<Option<file_monitor::AllConfigurations>>>,
    simplified_config: Arc<Mutex<Option<file_monitor::FileScanningConfig>>>, // 新增简化配置
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
            simplified_config: Arc::new(Mutex::new(None)), // 初始化简化配置
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

    // 新增：管理简化配置的方法
    pub async fn get_simplified_config(&self) -> Result<file_monitor::FileScanningConfig, String> {
        let config_guard = self.simplified_config.lock().unwrap();
        match &*config_guard {
            Some(config) => Ok(config.clone()),
            None => Err("简化配置未初始化".to_string()),
        }
    }

    pub fn update_simplified_config(&self, config: file_monitor::FileScanningConfig) {
        let mut config_guard = self.simplified_config.lock().unwrap();
        *config_guard = Some(config);
    }

    // 刷新简化配置（从API获取最新配置）
    pub async fn refresh_simplified_config(&self) -> Result<(), String> {
        println!("[CONFIG] 开始刷新简化配置");

        // 创建临时的FileMonitor实例来获取配置
        let temp_monitor = file_monitor::FileMonitor::new("127.0.0.1".to_string(), 60315);

        match temp_monitor.fetch_file_scanning_config().await {
            Ok(config) => {
                println!(
                    "[CONFIG] 成功获取简化配置: 扩展名映射={}, Bundle扩展名={}",
                    config.extension_mappings.len(),
                    config.bundle_extensions.len()
                );
                self.update_simplified_config(config);
                Ok(())
            }
            Err(e) => {
                println!("[CONFIG] 获取简化配置失败: {}", e);
                Err(format!("获取简化配置失败: {}", e))
            }
        }
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

        println!(
            "[CONFIG_QUEUE] 开始处理 {} 个待处理的配置变更",
            changes.len()
        );

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
                    eprintln!(
                        "[CONFIG_QUEUE] 刷新监控配置失败 ({}/{}): {}",
                        retry, max_retries, e
                    );
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
            eprintln!(
                "[CONFIG_QUEUE] 注意: {} 个配置变更执行失败，可能需要用户手动操作",
                failed_changes.len()
            );
            // 这里可以实现更多的失败处理逻辑，例如通知用户
        }
    }

    /// 执行单个配置变更
    async fn execute_single_config_change(
        change: &ConfigChangeRequest,
        monitor: &FileMonitor,
    ) -> Result<(), String> {
        match change {
            ConfigChangeRequest::DeleteFolder {
                folder_path,
                is_blacklist,
                ..
            } => {
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
                            }
                            Err(e) => {
                                last_error = e.to_string();
                                retry_count += 1;
                                if retry_count < max_retries {
                                    println!(
                                        "[CONFIG_QUEUE] 清理粗筛数据失败，将重试 ({}/{}): {}",
                                        retry_count, max_retries, last_error
                                    );
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
                            println!(
                                "[CONFIG_QUEUE] 成功清理黑名单路径 {} 的粗筛数据",
                                folder_path
                            );
                            break;
                        }
                        Err(e) => {
                            last_error = e.to_string();
                            retry_count += 1;
                            if retry_count < max_retries {
                                println!(
                                    "[CONFIG_QUEUE] 清理黑名单粗筛数据失败，将重试 ({}/{}): {}",
                                    retry_count, max_retries, last_error
                                );
                                sleep(Duration::from_millis(500 * retry_count)).await;
                            }
                        }
                    }
                }

                if retry_count == max_retries {
                    return Err(format!("清理黑名单粗筛数据失败: {}", last_error));
                }

                println!(
                    "[CONFIG_QUEUE] 黑名单文件夹添加变更处理完成: {}",
                    folder_path
                );
                Ok(())
            }

            ConfigChangeRequest::ToggleFolder {
                folder_path,
                is_blacklist,
                ..
            } => {
                if *is_blacklist {
                    // 转为黑名单时清理粗筛数据
                    Self::cleanup_screening_data_for_path(folder_path, monitor).await?;
                } else {
                    // 转为白名单时执行增量扫描
                    monitor.scan_single_directory(folder_path, None).await?;
                }
                println!("[CONFIG_QUEUE] 文件夹状态切换变更处理完成: {}", folder_path);
                Ok(())
            }

            ConfigChangeRequest::AddWhitelist { folder_path, .. } => {
                // 新增白名单文件夹时执行增量扫描
                monitor.scan_single_directory(folder_path, None).await?;
                println!(
                    "[CONFIG_QUEUE] 白名单文件夹添加变更处理完成: {}",
                    folder_path
                );
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
        let api_url = format!(
            "http://{}:{}/screening/clean-by-path",
            monitor.get_api_host(),
            monitor.get_api_port()
        );

        println!("[CLEANUP] 开始清理路径 {} 的粗筛数据", folder_path);

        // 创建一个更长超时设置的客户端
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(30)) // 设置30秒超时
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
            let result = response
                .json::<serde_json::Value>()
                .await
                .map_err(|e| format!("解析清理响应失败: {}", e))?;

            // 从响应中提取删除的记录数
            let deleted_count = result.get("deleted").and_then(|v| v.as_i64()).unwrap_or(0);

            println!(
                "[CLEANUP] 成功清理路径 {} 的粗筛数据，删除 {} 条记录",
                folder_path, deleted_count
            );

            // 额外的验证: 如果应该有记录被删除但返回0，可能要警告
            if folder_path.contains("Pictures") && deleted_count == 0 {
                println!("[CLEANUP] 警告: 清理图片目录相关的粗筛数据，但未删除任何记录");
            }

            Ok(())
        } else {
            // 处理错误响应
            let error_text = response
                .text()
                .await
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_window_state::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(
            tauri_plugin_log::Builder::new()
                .level(log::LevelFilter::Info) // 你可以设置一个全局的默认级别，例如 Info
                .level_for("tao", log::LevelFilter::Warn) // 将 tao crate 的日志级别设为 Warn
                .level_for("notify", log::LevelFilter::Info) // Revert to INFO or desired level
                // .level_for("notify_debouncer_full", log::LevelFilter::Info) // Revert to INFO or desired level
                .build(),
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
        .plugin(tauri_plugin_screenshots::init())
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

            // 注册全局 panic hook 用于清理
            let prev_hook = std::panic::take_hook();
            std::panic::set_hook(Box::new(move |panic_info| {
                println!("Panic detected, executing cleanup: {:?}", panic_info);
                ApiProcessManager::cleanup_processes();
                prev_hook(panic_info);
            }));

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
                let _ = crate::api_startup::start_python_api(
                    app_handle_for_api.clone(),
                    api_state_for_api.clone(),
                );

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
                let max_retries = 10000; // 最多尝试次数，足够长让用户看到详细日志
                let retry_interval = std::time::Duration::from_millis(1000); // 毫秒
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
                    match client
                        .get(&api_url)
                        .timeout(std::time::Duration::from_secs(1))
                        .send()
                        .await
                    {
                        Ok(response) if response.status().is_success() => {
                            println!("第{}次尝试: API健康检查成功，API已就绪", i + 1);
                            api_ready = true;
                            break;
                        }
                        _ => {
                            // API尚未准备好，等待后重试
                            if (i + 1) % 5 == 0 {
                                // 每5次打印一次，避免日志过多
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

            // 等待API就绪信号后再准备文件监控基础设施
            let app_handle_for_monitor = app_handle.clone();
            let monitor_state = app
                .state::<Arc<Mutex<Option<FileMonitor>>>>()
                .inner()
                .clone();
            let api_state_for_monitor = api_state_instance.0.clone();

            tauri::async_runtime::spawn(async move {
                // 等待API就绪信号
                match rx.await {
                    Ok(true) => {
                        println!("收到API就绪信号，准备文件监控基础设施（不开始扫描）...");
                        // 初始化文件监控基础设施，但不开始自动扫描
                        crate::setup_file_monitor::setup_file_monitoring_infrastructure(
                            app_handle_for_monitor.clone(),
                            monitor_state,
                            api_state_for_monitor,
                        )
                        .await;

                        // 初始化简化配置
                        println!("开始初始化简化配置...");
                        let app_state = app_handle_for_monitor.state::<AppState>();
                        match app_state.refresh_simplified_config().await {
                            Ok(()) => {
                                println!("简化配置初始化成功");
                                if let Some(window) =
                                    app_handle_for_monitor.get_webview_window("main")
                                {
                                    let _ = window.emit("simplified-config-ready", true);
                                }
                            }
                            Err(e) => {
                                eprintln!("简化配置初始化失败: {}", e);
                                if let Some(window) =
                                    app_handle_for_monitor.get_webview_window("main")
                                {
                                    let _ = window.emit(
                                        "simplified-config-error",
                                        format!("简化配置初始化失败: {}", e),
                                    );
                                }
                            }
                        }
                    }
                    _ => {
                        eprintln!("API未能成功启动，无法初始化文件监控基础设施");
                        if let Some(window) = app_handle_for_monitor.get_webview_window("main") {
                            let _ =
                                window.emit("file-monitor-error", "API未就绪，无法初始化文件监控");
                        }
                    }
                }
            });

            // 创建应用菜单（仅在 macOS 上显示）
            #[cfg(target_os = "macos")]
            {
                // 创建菜单项
                let settings_item =
                    MenuItem::with_id(app, "settings", "Settings", true, Some("cmd+,"))?;
                let about_item =
                    MenuItem::with_id(app, "about", "About Knowledge Focus", true, None::<&str>)?;
                let separator = PredefinedMenuItem::separator(app)?;
                let quit_item = PredefinedMenuItem::quit(app, Some("Quit Knowledge Focus"))?;

                // 创建窗口定位菜单项
                let move_left_item =
                    MenuItem::with_id(app, "move_left", "Move Left", true, Some("cmd+shift+left"))?;
                let move_right_item = MenuItem::with_id(
                    app,
                    "move_right",
                    "Move Right",
                    true,
                    Some("cmd+shift+right"),
                )?;

                // 创建应用菜单
                let app_menu = Submenu::with_id_and_items(
                    app,
                    "app",
                    "Knowledge Focus",
                    true,
                    &[
                        &about_item,
                        &separator,
                        &settings_item,
                        &separator,
                        &quit_item,
                    ],
                )?;

                // 创建编辑菜单（标准的剪切、复制、粘贴功能）
                let edit_menu = Submenu::with_id_and_items(
                    app,
                    "edit",
                    "Edit",
                    true,
                    &[
                        &PredefinedMenuItem::undo(app, None)?,
                        &PredefinedMenuItem::redo(app, None)?,
                        &PredefinedMenuItem::separator(app)?,
                        &PredefinedMenuItem::cut(app, None)?,
                        &PredefinedMenuItem::copy(app, None)?,
                        &PredefinedMenuItem::paste(app, None)?,
                        &PredefinedMenuItem::select_all(app, None)?,
                    ],
                )?;

                // 创建窗口菜单（包含 macOS 标准窗口管理项目和自定义定位功能）
                let window_menu = Submenu::with_id_and_items(
                    app,
                    "window",
                    "Window",
                    true,
                    &[
                        &PredefinedMenuItem::minimize(app, None)?,
                        &PredefinedMenuItem::separator(app)?,
                        &move_left_item,
                        &move_right_item,
                        &PredefinedMenuItem::separator(app)?,
                        &PredefinedMenuItem::close_window(app, None)?,
                    ],
                )?;

                // 创建主菜单栏
                let menu = Menu::with_items(app, &[&app_menu, &edit_menu, &window_menu])?;

                // 设置应用菜单
                app.set_menu(menu)?;

                // 处理菜单事件
                app.on_menu_event(move |app, event| {
                    match event.id().as_ref() {
                        "settings" => {
                            println!("Settings 菜单项被点击");
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.emit("menu-settings", "general");
                            }
                        }
                        "about" => {
                            println!("About 菜单项被点击");
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.emit("menu-settings", "about");
                            }
                        }
                        "move_left" => {
                            println!("Move Left 菜单项被点击");
                            if let Some(window) = app.get_webview_window("main") {
                                // 获取屏幕尺寸并将窗口移动到左半屏
                                if let Ok(monitor) = window.current_monitor() {
                                    if let Some(monitor) = monitor {
                                        let screen_size = monitor.size();
                                        let screen_position = monitor.position();

                                        let window_width = screen_size.width / 2;
                                        // 窗口高度保持不变
                                        let window_height =
                                            window.outer_size().unwrap_or_default().height;
                                        // 窗口y值不变
                                        let window_y =
                                            window.outer_position().unwrap_or_default().y;

                                        // 设置窗口位置和大小
                                        let _ = window.set_position(tauri::Position::Physical(
                                            tauri::PhysicalPosition {
                                                x: screen_position.x,
                                                y: window_y,
                                            },
                                        ));
                                        let _ = window.set_size(tauri::Size::Physical(
                                            tauri::PhysicalSize {
                                                width: window_width,
                                                height: window_height,
                                            },
                                        ));
                                    }
                                }
                            }
                        }
                        "move_right" => {
                            println!("Move Right 菜单项被点击");
                            if let Some(window) = app.get_webview_window("main") {
                                // 获取屏幕尺寸并将窗口移动到右半屏
                                if let Ok(monitor) = window.current_monitor() {
                                    if let Some(monitor) = monitor {
                                        let screen_size = monitor.size();
                                        let screen_position = monitor.position();

                                        let window_width = screen_size.width / 2;
                                        // 窗口高度保持不变
                                        let window_height =
                                            window.outer_size().unwrap_or_default().height;
                                        // 窗口y值不变
                                        let window_y =
                                            window.outer_position().unwrap_or_default().y;

                                        // 设置窗口位置和大小
                                        let _ = window.set_position(tauri::Position::Physical(
                                            tauri::PhysicalPosition {
                                                x: screen_position.x
                                                    + (screen_size.width / 2) as i32,
                                                y: window_y,
                                            },
                                        ));
                                        let _ = window.set_size(tauri::Size::Physical(
                                            tauri::PhysicalSize {
                                                width: window_width,
                                                height: window_height,
                                            },
                                        ));
                                    }
                                }
                            }
                        }
                        _ => {}
                    }
                });
            }

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

                        // 在退出前执行完整清理
                        println!("执行完整进程清理");

                        // 尝试获取ApiProcessManager并执行完整清理
                        if let Some(api_manager) = app.try_state::<ApiProcessManager>() {
                            api_manager.cleanup();
                            println!("通过ApiProcessManager实例执行了完整清理");
                        } else {
                            println!("无法获取ApiProcessManager，使用静态清理");
                            ApiProcessManager::cleanup_processes();
                        }

                        // 终止所有资源并退出应用
                        app.exit(0);
                    }
                    _ => {
                        // println!("menu item {:?} not handled", event.id);
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
            commands::refresh_monitoring_config,         // 刷新监控配置
            commands::refresh_simplified_config,         // 刷新简化配置
            commands::read_directory,                    // 读取目录内容
            commands::get_tag_cloud_data,                // 获取标签云数据
            commands::search_files_by_tags,              // 按标签搜索文件
            commands::queue_add_blacklist_folder,        // 添加黑名单文件夹
            commands::queue_delete_folder,               // 删除文件夹
            commands::queue_toggle_folder_status,        // 切换文件夹状态（黑名单/白名单）
            commands::queue_add_whitelist_folder,        // 添加白名单文件夹
            commands::queue_get_status,                  // 获取队列状态
            file_scanner::start_backend_scanning,        // 后端扫描启动命令
            file_scanner::scan_files_by_time_range,      // 按时间范围扫描文件
            file_scanner::scan_files_by_type,            // 按类型扫描文件
            file_scanner::scan_files_simplified_command, // 简化扫描命令（支持Bundle和新配置）
        ])
        .on_window_event(|window, event| match event {
            WindowEvent::Destroyed => {
                // 获取窗口的标牌，区分是哪个窗口被销毁
                let window_label = window.label();

                println!("窗口被销毁: {}", window_label);

                // 如果是主窗口被销毁，执行清理
                if window_label == "main" {
                    println!("主窗口被销毁，执行完整进程清理");

                    // 尝试获取ApiProcessManager并执行完整清理
                    if let Some(api_manager) = window.app_handle().try_state::<ApiProcessManager>()
                    {
                        api_manager.cleanup();
                        println!("通过ApiProcessManager实例执行了完整清理");
                    } else {
                        println!("无法获取ApiProcessManager，使用静态清理");
                        ApiProcessManager::cleanup_processes();
                    }
                }
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
        .build(tauri::generate_context!())
        .expect("error while running tauri application")
        .run(|app_handle, event| {
            // 获取事件名称用于调试
            let event_name = match &event {
                tauri::RunEvent::ExitRequested { .. } => "ExitRequested",
                tauri::RunEvent::Exit => "Exit",
                tauri::RunEvent::WindowEvent { event, .. } => match event {
                    tauri::WindowEvent::CloseRequested { .. } => "WindowEvent::CloseRequested",
                    tauri::WindowEvent::Destroyed => "WindowEvent::Destroyed",
                    _ => "WindowEvent::Other",
                },
                _ => "Other",
            };

            // 只在重要事件时打印，减少输出噪音
            if matches!(
                event,
                tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit
            ) {
                println!("=== 收到重要运行事件: {} ===", event_name);
            }

            match event {
                tauri::RunEvent::ExitRequested { .. } => {
                    // 应用退出请求时终止API进程
                    println!("ExitRequested 事件：开始清理API进程");

                    // 尝试获取ApiProcessManager并执行完整清理
                    if let Some(api_manager) = app_handle.try_state::<ApiProcessManager>() {
                        api_manager.cleanup();
                        println!("通过ApiProcessManager实例执行了完整清理");
                    } else {
                        println!("无法获取ApiProcessManager，使用静态清理");
                        ApiProcessManager::cleanup_processes();
                    }

                    println!("ExitRequested 事件：资源清理完毕");
                }
                tauri::RunEvent::Exit => {
                    // 应用最终退出时的备用清理
                    println!("Exit 事件：进行备用API进程清理");
                    ApiProcessManager::cleanup_processes();
                    println!("Exit 事件：备用清理完毕");
                }
                _ => {
                    // 其他事件不做处理
                }
            }
        });
}
