use std::env;
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::time::sleep;

mod file_monitor;
use file_monitor::{DirectoryAuthStatus, FileMonitor, MonitoredDirectory};

// 用于测试的控制台打印宏
macro_rules! test_log {
    ($($arg:tt)*) => {{
        let timestamp = chrono::Local::now().format("%H:%M:%S%.3f");
        println!("[TEST {}] {}", timestamp, format!($($arg)*));
    }};
}

#[tokio::main]
async fn main() {
    // 从命令行参数获取要监控的目录
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: {} <directory_to_monitor>", args[0]);
        std::process::exit(1);
    }
    
    let dir_to_monitor = &args[1];
    if !Path::new(dir_to_monitor).exists() {
        eprintln!("Error: Directory '{}' does not exist", dir_to_monitor);
        std::process::exit(1);
    }
    
    test_log!("Starting file_monitor test with directory: {}", dir_to_monitor);
    
    // 模拟API服务器配置 (实际测试中需要启动一个真实的API服务器)
    let api_host = "127.0.0.1";
    let api_port = 5000;
    
    test_log!("Creating FileMonitor instance with API at {}:{}", api_host, api_port);
    
    // 创建FileMonitor实例
    let mut monitor = FileMonitor::new(api_host.to_string(), api_port);
    
    // 添加要监控的目录
    let monitored_dir = MonitoredDirectory {
        id: Some(1),
        path: dir_to_monitor.to_string(),
        alias: Some("Test Directory".to_string()),
        is_blacklist: false,
        auth_status: DirectoryAuthStatus::Authorized,
    };
    
    test_log!("Adding test directory to monitoring list");
    monitor.add_monitored_directory(monitored_dir);
    
    // 打印debug信息的自定义实现
    // 这将替换或增强FileMonitor上的方法，使其打印更多调试信息
    apply_debug_patches(&mut monitor);
    
    test_log!("Starting file monitoring");
    
    // 启动文件监控
    match monitor.start_monitoring().await {
        Ok(_) => test_log!("Monitoring started successfully"),
        Err(e) => {
            test_log!("Failed to start monitoring: {}", e);
            std::process::exit(1);
        }
    }
    
    test_log!("Monitoring active. Press Ctrl+C to stop...");
    
    // 保持程序运行，直到用户按下Ctrl+C
    let running = Arc::new(Mutex::new(true));
    let r = running.clone();
    
    ctrlc::set_handler(move || {
        let mut running = r.lock().unwrap();
        *running = false;
    })
    .expect("Error setting Ctrl-C handler");
    
    // 每10秒打印一次状态信息
    while *running.lock().unwrap() {
        sleep(Duration::from_secs(10)).await;
        test_log!("Still monitoring...");
    }
    
    test_log!("Test completed.");
}

// 为FileMonitor应用调试补丁，增加更多日志输出
fn apply_debug_patches(monitor: &mut FileMonitor) {
    // 这个函数会被实现为修改FileMonitor的行为，
    // 注入更多打印语句，但现在我们先留空
    // 实际补丁将在后续实现
}
