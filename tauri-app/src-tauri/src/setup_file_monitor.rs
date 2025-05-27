use crate::file_monitor::FileMonitor;
use crate::file_monitor_debounced::DebouncedFileMonitor;
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
            // 创建基础文件监控器
            let mut base_monitor = FileMonitor::new(api_host.clone(), api_port);
            
            // 首先获取配置和连接到API
            let result = base_monitor.start_monitoring_setup_and_initial_scan().await;

            match result {
                Ok(_) => {
                    println!("基础文件监控模块初始化成功，准备创建防抖动监控器");
                    
                    // 获取配置信息
                    let config = base_monitor.get_configurations();
                    let directories: Vec<String> = base_monitor.get_monitored_directories()
                        .into_iter()
                        .map(|dir| dir.path)
                        .collect();
                    
                    // 创建防抖动文件监控器
                    let base_monitor_arc = Arc::new(base_monitor);
                    let mut debounced_monitor = DebouncedFileMonitor::new(Arc::clone(&base_monitor_arc));
                    
                    // 启动防抖动监控
                    match debounced_monitor.start_monitoring(directories, Duration::from_millis(2_000)).await {
                        Ok(_) => {
                            println!("防抖动文件监控已自动启动");
                            if let Some(window) = app_handle.get_webview_window("main") {
                                let _ = window.emit("file-monitor-started", ());
                            }

                            // 保存基础监控器实例到全局状态
                            {
                                let mut monitor_guard = monitor_state.lock().unwrap();
                                *monitor_guard = Some((*base_monitor_arc).clone());
                            }

                            // 保存防抖动监控器实例到全局状态
                            {
                                let app_state = app_handle.state::<AppState>();
                                let mut debounced_monitor_guard = app_state.debounced_file_monitor.lock().unwrap();
                                *debounced_monitor_guard = Some(debounced_monitor); // 将 debounced_monitor 移动到 AppState
                            }
                            
                            // 更新应用配置状态
                            if let Some(cfg) = config {
                                let app_state = app_handle.state::<AppState>();
                                app_state.update_config(cfg);
                                println!("已更新应用配置状态");
                            }
                        },
                        Err(e) => {
                            eprintln!("自动启动防抖动文件监控失败: {}", e);
                            if let Some(window) = app_handle.get_webview_window("main") {
                                let _ = window.emit("file-monitor-error", e.to_string());
                            }
                        }
                    }
                },
                Err(e) => {
                    eprintln!("自动启动基础文件监控失败: {}", e);
                    if let Some(window) = app_handle.get_webview_window("main") {
                        let _ = window.emit("file-monitor-error", e.to_string());
                    }
                }
            }
        }
    });
}
