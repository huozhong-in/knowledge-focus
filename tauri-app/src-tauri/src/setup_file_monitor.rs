use crate::file_monitor::FileMonitor;
use std::sync::{Arc, Mutex};
use std::time::Duration;
// 添加 Emitter trait 用于发送事件
use tauri::{
    Manager, 
    Emitter, 
    // State
};
use tokio::time::sleep;

use crate::AppState; // Import AppState

// 在 App 启动后自动启动文件监控的函数
pub fn setup_auto_file_monitoring(
    app_handle: tauri::AppHandle,
    monitor_state: Arc<Mutex<Option<FileMonitor>>>,
    api_state: Arc<Mutex<crate::ApiProcessState>>,
) {
    // 打印诊断信息
    println!("启动自动文件监控配置...");

    tauri::async_runtime::spawn(async move {
        // 等待10秒，确保API已经启动
        sleep(Duration::from_secs(10)).await;

        // 检查API是否在运行并获取API信息
        let (api_running, api_host, api_port) = {
            let api_state_guard = api_state.lock().unwrap();
            let running = api_state_guard.process_child.is_some();
            let host = api_state_guard.host.clone();
            let port = api_state_guard.port;
            (running, host, port)
        };

        if api_running {
            // 创建并启动文件监控
            let mut monitor = FileMonitor::new(api_host, api_port);

            // Start monitoring and then handle the result
            let result = monitor.start_monitoring().await;

            match result {
                Ok(_) => {
                    println!("文件监控已自动启动");
                    if let Some(window) = app_handle.get_webview_window("main") {
                        let _ = window.emit("file-monitor-started", ());
                    }

                    // 先获取配置，再保存监控实例
                    let config = monitor.get_configurations();

                    // Save monitor instance
                    {
                        let mut monitor_guard = monitor_state.lock().unwrap(); // Corrected variable name
                        *monitor_guard = Some(monitor);
                    }

                    // Update AppState with config information
                    if let Some(cfg) = config {
                        // Access AppState using app_handle.state()
                        let app_state = app_handle.state::<AppState>();
                        app_state.update_config(cfg);
                        println!("已更新应用配置状态");
                    }
                }
                Err(e) => {
                    eprintln!("自动启动文件监控失败: {}", e);
                    if let Some(window) = app_handle.get_webview_window("main") {
                        let _ = window.emit("file-monitor-error", e.to_string());
                    }
                }
            }
        }
    });
}
