use crate::file_monitor::FileMonitor;
use crate::file_monitor_debounced::DebouncedFileMonitor;
use std::sync::{Arc, Mutex};
use tauri::Manager;

use crate::AppState;

// 仅设置文件监控基础设施，不开始扫描
pub async fn setup_file_monitoring_infrastructure(
    app_handle: tauri::AppHandle,
    monitor_state: Arc<Mutex<Option<FileMonitor>>>,
    api_state: Arc<Mutex<crate::ApiProcessState>>,
) {
    println!("初始化文件监控基础设施（不启动扫描）...");

    // 先获取API主机和端口信息
    let (api_host, api_port) = {
        let api_state_guard = api_state.lock().unwrap();
        (api_state_guard.host.clone(), api_state_guard.port)
    };

    // 创建基础文件监控器（不执行任何初始化）
    let base_monitor = FileMonitor::new(api_host.clone(), api_port);

    println!("文件监控基础设施创建完成，等待前端权限检查后启动扫描");

    // 保存基础监控器实例到全局状态
    {
        let mut monitor_guard = monitor_state.lock().unwrap();
        *monitor_guard = Some(base_monitor.clone());
    }

    // 保存监控器实例到 AppState
    {
        let app_state = app_handle.state::<AppState>();
        // 保存基础监控器到 AppState.file_monitor
        {
            let mut app_monitor_guard = app_state.file_monitor.lock().unwrap();
            *app_monitor_guard = Some(base_monitor.clone());
            println!("[基础设施] 已将文件监控器实例保存到 AppState.file_monitor");
        }

        // 创建但不启动防抖动监控器
        let base_monitor_arc = Arc::new(base_monitor.clone());
        let debounced_monitor =
            DebouncedFileMonitor::new(Arc::clone(&base_monitor_arc), Some(app_handle.clone()));
        {
            let mut debounced_monitor_guard = app_state.debounced_file_monitor.lock().unwrap();
            *debounced_monitor_guard = Some(debounced_monitor);
            println!("[基础设施] 已创建防抖动监控器实例（未启动）");
        }
    }

    println!("[基础设施] 文件监控基础设施已就绪，等待前端显式启动扫描命令");
}
