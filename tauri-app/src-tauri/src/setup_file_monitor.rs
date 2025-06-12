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
// 导入reqwest用于API健康检查
use reqwest;

use crate::AppState; // Import AppState

// 在 App 启动后自动启动文件监控的函数
// 在此版本中我们不使用API就绪信号，为保持原有功能暂时使用原来的方法
pub fn setup_auto_file_monitoring(
    app_handle: tauri::AppHandle,
    monitor_state: Arc<Mutex<Option<FileMonitor>>>,
    api_state: Arc<Mutex<crate::ApiProcessState>>,
) {
    // 打印诊断信息
    println!("启动自动文件监控配置...");

    tauri::async_runtime::spawn(async move {
        // 不再使用固定等待时间，而是采用轮询方式检查API是否准备就绪
        let max_retries = 30; // 最多尝试30次
        let retry_interval = Duration::from_millis(500); // 每500ms检查一次
        let api_url;
        
        // 先获取API主机和端口信息
        let (api_host, api_port) = {
            let api_state_guard = api_state.lock().unwrap();
            (api_state_guard.host.clone(), api_state_guard.port)
        };
        
        api_url = format!("http://{}:{}/health", api_host, api_port);
        println!("开始检查API是否就绪，API地址: {}", api_url);
        
        // 使用reqwest客户端检查API健康状态
        let client = reqwest::Client::new();
        let mut api_ready = false;
        
        for i in 0..max_retries {
            // 首先检查API进程是否运行
            let api_running = {
                let api_state_guard = api_state.lock().unwrap();
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
        
        if !api_ready {
            eprintln!("API启动失败或未就绪，无法启动文件监控");
            if let Some(window) = app_handle.get_webview_window("main") {
                let _ = window.emit("file-monitor-error", "API未就绪，无法启动文件监控".to_string());
            }
            return;
        }
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

                        // 保存监控器实例到 AppState（用于配置队列处理）
                        {
                            let app_state = app_handle.state::<AppState>();
                            // 保存基础监控器到 AppState.file_monitor
                            {
                                let mut app_monitor_guard = app_state.file_monitor.lock().unwrap();
                                *app_monitor_guard = Some((*base_monitor_arc).clone());
                                println!("[CONFIG_QUEUE] 已将文件监控器实例保存到 AppState.file_monitor");
                            }
                            // 保存防抖动监控器到 AppState.debounced_file_monitor
                            {
                                let mut debounced_monitor_guard = app_state.debounced_file_monitor.lock().unwrap();
                                *debounced_monitor_guard = Some(debounced_monitor); // 将 debounced_monitor 移动到 AppState
                            }
                        }
                        
                        // 更新应用配置状态
                        if let Some(cfg) = config {
                            let app_state = app_handle.state::<AppState>();
                            app_state.update_config(cfg);
                            println!("已更新应用配置状态");
                        }
                        
                        // 启动初始扫描完成监听器
                        let app_handle_for_scan_completion = app_handle.clone();
                        let base_monitor_arc_for_completion = Arc::clone(&base_monitor_arc);
                        tokio::spawn(async move {
                            // 更精确的初始扫描完成检测
                            let max_wait_time = Duration::from_secs(60); // 最大等待时间60秒
                            let check_interval = Duration::from_millis(500); // 每500ms检查一次
                            let start_time = std::time::Instant::now();
                            
                            println!("[CONFIG_QUEUE] 开始监控初始扫描完成状态...");
                            
                            loop {
                                tokio::time::sleep(check_interval).await;
                                
                                // 检查是否超时
                                if start_time.elapsed() >= max_wait_time {
                                    println!("[CONFIG_QUEUE] 等待初始扫描完成超时，强制设置为完成状态");
                                    break;
                                }
                                
                                // 获取监控器统计信息来判断扫描是否完成
                                let stats = base_monitor_arc_for_completion.get_monitor_stats();
                                
                                // 基于文件处理统计来判断扫描是否稳定
                                // 如果已经处理了一些文件，并且在最近几秒内没有新的处理活动，认为扫描完成
                                if stats.processed_files > 0 {
                                    // 等待一段时间确认没有新的文件处理活动
                                    let checkpoint_files = stats.processed_files;
                                    tokio::time::sleep(Duration::from_secs(3)).await;
                                    
                                    let new_stats = base_monitor_arc_for_completion.get_monitor_stats();
                                    if new_stats.processed_files == checkpoint_files {
                                        // 文件处理数量没有变化，认为初始扫描已完成
                                        println!("[CONFIG_QUEUE] 初始扫描完成检测 - 处理文件: {}, 扫描稳定", new_stats.processed_files);
                                        break;
                                    } else {
                                        println!("[CONFIG_QUEUE] 初始扫描进行中 - 处理文件: {} -> {}", checkpoint_files, new_stats.processed_files);
                                    }
                                } else {
                                    // 还没有开始处理文件，等待一段时间后再检查
                                    if start_time.elapsed() > Duration::from_secs(5) {
                                        println!("[CONFIG_QUEUE] 等待初始扫描开始...");
                                    }
                                }
                            }
                            
                            // 设置初始扫描完成状态并处理队列
                            let app_state = app_handle_for_scan_completion.state::<AppState>();
                            app_state.set_initial_scan_completed(true);
                            println!("[CONFIG_QUEUE] 初始扫描完成，开始处理配置变更队列");
                        });
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
    });
}
