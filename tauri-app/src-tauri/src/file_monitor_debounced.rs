use crate::file_monitor::FileMonitor;
use notify::event::{CreateKind, ModifyKind, RemoveKind, RenameMode};
use notify::{EventKind, RecursiveMode, Watcher};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc as std_mpsc;
use std::sync::Arc;
use std::time::Duration;
use tauri::Emitter;
use tokio::sync::mpsc::{self, Sender};
use tokio::sync::Mutex;

// 定义简化的文件事件类型
#[derive(Debug, Clone, PartialEq, Eq)]
#[allow(dead_code)] // 显式允许枚举定义被保留，即使当前未使用
pub enum SimpleFileEvent {
    Added(PathBuf),   // 文件新增（包括创建和移入）
    Removed(PathBuf), // 文件删除（包括删除和移出）
}

/// 防抖动文件监控器
#[derive(Clone)]
pub struct DebouncedFileMonitor {
    /// 指向基础FileMonitor的引用，用于处理文件元数据和规则
    file_monitor: Arc<FileMonitor>,
    /// 事件发送通道，用于处理处理后的文件变更
    event_tx: Option<Sender<(PathBuf, notify::EventKind)>>,
    /// 防抖事件缓冲区 (仅保留用于扩展但当前未使用)
    #[allow(dead_code)]
    debounce_buffer: Arc<Mutex<HashMap<PathBuf, notify::EventKind>>>,
    /// 保存监控路径到其停止发送器的映射，用于停止特定路径的监控 (仅保留用于扩展但当前未使用)
    #[allow(dead_code)]
    watch_stop_channels: Arc<Mutex<HashMap<String, std_mpsc::Sender<()>>>>,
    /// Tauri应用程序句柄，用于发射事件到前端
    app_handle: Option<tauri::AppHandle>,
}

impl DebouncedFileMonitor {
    /// 创建新的防抖动文件监控器
    pub fn new(file_monitor: Arc<FileMonitor>, app_handle: Option<tauri::AppHandle>) -> Self {
        DebouncedFileMonitor {
            file_monitor,
            event_tx: None,
            debounce_buffer: Arc::new(Mutex::new(HashMap::new())),
            watch_stop_channels: Arc::new(Mutex::new(HashMap::new())),
            app_handle,
        }
    }

    /// Helper function to set up a debounced watch for a single directory.
    /// This function spawns a task that owns the debouncer after successful setup.
    async fn setup_single_debounced_watch(
        dir_path_str: String, // Owned String
        debounce_time: Duration,
        tx_to_central_handler: Sender<(PathBuf, notify::EventKind)>,
        stop_tx_sender: Option<std_mpsc::Sender<std_mpsc::Sender<()>>>, // 可选的停止通道发送器
    ) -> std::result::Result<(), String> {
        println!(
            "[防抖监控] Setting up watch for directory: {}",
            dir_path_str
        );

        // 使用标准 notify 库而不是 debouncer
        println!("[文件监控] 直接使用 notify 库进行监控，增加自定义防抖机制");

        // 创建事件缓冲区和防抖处理通道
        let (debounce_tx, mut debounce_rx) = mpsc::channel::<(PathBuf, notify::EventKind)>(100);

        // 克隆一个 sender 用于回调函数
        let dir_path_for_watcher = dir_path_str.clone();

        // 创建一个同步通道用于保持通信
        let (init_tx, init_rx) = std_mpsc::channel();
        // 创建停止通道
        let (stop_tx, stop_rx) = std_mpsc::channel::<()>();

        // 创建一个共享的停止标志
        let should_stop = Arc::new(AtomicBool::new(false));
        let should_stop_clone = should_stop.clone();

        // 在单独的线程中监听停止信号
        std::thread::spawn(move || {
            if let Ok(_) = stop_rx.recv() {
                should_stop_clone.store(true, Ordering::SeqCst);
            }
        });

        // 如果提供了停止通道发送器，则发送停止通道
        if let Some(tx_sender) = stop_tx_sender {
            if let Err(e) = tx_sender.send(stop_tx.clone()) {
                println!("[防抖监控] 无法注册停止通道: {:?}", e);
                // 继续执行，但停止机制将无法工作
            } else {
                println!("[防抖监控] 已注册停止通道");
            }
        }

        // 在单独的线程中创建和运行 watcher
        // 这样避免了异步上下文的复杂性
        std::thread::spawn(move || {
            println!("[文件监控-线程] 启动 watcher 线程");

            // 创建 watcher
            let mut watcher = match notify::recommended_watcher(
                move |res: std::result::Result<notify::Event, notify::Error>| {
                    println!("🔔🔔🔔 NOTIFY EVENT CALLBACK 🔔🔔🔔");

                    match res {
                        Ok(event) => {
                            println!("🔔 Event Type: {:?}", event.kind);
                            println!("🔔 Paths: {:?}", event.paths);

                            // 将事件发送到防抖队列
                            let paths = event.paths.clone();
                            let kind = event.kind.clone();

                            // 使用 tokio 当前线程运行时来处理异步发送
                            let rt = tokio::runtime::Builder::new_current_thread()
                                .enable_all()
                                .build()
                                .unwrap();

                            rt.block_on(async {
                                // 对每个路径发送事件到防抖缓冲区
                                for path in paths {
                                    let debounce_tx = debounce_tx.clone();

                                    // 简化事件种类: Create, Remove 或 Modify
                                    // 对于文件路径，我们需要处理实际存在与否
                                    let processed_kind = match &kind {
                                        EventKind::Create(_) => kind.clone(),
                                        EventKind::Remove(_) => kind.clone(),
                                        _ => {
                                            // 对于其他事件类型，检查文件是否存在
                                            if path.exists() && path.is_file() {
                                                // 文件存在，当作新增处理
                                                EventKind::Create(CreateKind::File)
                                            } else {
                                                // 文件不存在，当作删除处理
                                                EventKind::Remove(RemoveKind::File)
                                            }
                                        }
                                    };

                                    // 发送到防抖队列
                                    if let Err(e) =
                                        debounce_tx.send((path.clone(), processed_kind)).await
                                    {
                                        eprintln!("🔔❌ 发送到防抖队列失败: {}", e);
                                    } else {
                                        println!(
                                            "🔔✅ 事件已发送到防抖队列: {:?} -> {:?}",
                                            processed_kind, path
                                        );
                                    }
                                }
                            });
                        }
                        Err(e) => {
                            eprintln!("🔔❌ 监控错误: {:?}", e);
                        }
                    }
                    println!("🔔🔔🔔 NOTIFY CALLBACK END 🔔🔔🔔");
                },
            ) {
                Ok(w) => w,
                Err(e) => {
                    eprintln!("[文件监控-线程] 创建 watcher 失败: {:?}", e);
                    let _ = init_tx.send(Err(format!("Failed to create watcher: {:?}", e)));
                    return;
                }
            };

            // 检查路径是否存在
            let watch_path = Path::new(&dir_path_for_watcher);
            println!("[文件监控-线程] Path exists: {}", watch_path.exists());
            println!("[文件监控-线程] Path is dir: {}", watch_path.is_dir());

            // 设置监控，检查是否为macOS bundle文件夹决定监控模式
            let watch_mode = if crate::file_monitor::FileMonitor::is_macos_bundle_folder(watch_path)
            {
                println!(
                    "[文件监控-线程] 检测到 Bundle 文件夹，使用非递归模式监控: {}",
                    dir_path_for_watcher
                );
                RecursiveMode::NonRecursive
            } else {
                RecursiveMode::Recursive
            };

            match watcher.watch(watch_path, watch_mode) {
                Ok(_) => {
                    println!(
                        "[文件监控-线程] ✅ 成功设置监控: {} (模式: {:?})",
                        dir_path_for_watcher, watch_mode
                    );
                    let _ = init_tx.send(Ok(()));
                }
                Err(e) => {
                    eprintln!("[文件监控-线程] ❌ 监控设置失败: {:?}", e);
                    let _ = init_tx.send(Err(format!("Failed to watch: {:?}", e)));
                    return;
                }
            };

            // 保持 watcher 活跃
            println!("[文件监控-线程] 开始保持 watcher 活跃");
            // let mut tick_count = 0;

            loop {
                // 让线程休眠10秒
                std::thread::sleep(Duration::from_secs(10));
                // tick_count += 1;
                // println!("[文件监控-心跳] #{} Watcher for '{}' is still alive",
                //         tick_count, &dir_path_for_watcher);

                // 确保 watcher 保持活跃
                let _ = &watcher;
            }
        });

        // 启动防抖处理
        let tx_for_debounce = tx_to_central_handler.clone();
        tokio::spawn(async move {
            // 创建防抖缓冲区
            let mut debounce_buffer: HashMap<PathBuf, notify::EventKind> = HashMap::new();
            let mut interval = tokio::time::interval(debounce_time);

            // 用于接收停止信号的变量
            let mut continue_running = true;
            let dir_path_clone = dir_path_str.clone();

            while continue_running {
                tokio::select! {
                    // 当有新事件时加入缓冲区
                    Some((path, kind)) = debounce_rx.recv() => {
                        println!("[防抖处理] 收到原始事件: {:?} -> {:?}", kind, path);
                        // 对于同一路径，后来的事件覆盖先前的事件
                        debounce_buffer.insert(path, kind);
                    }

                    // 定时处理缓冲区
                    _ = interval.tick() => {
                        if !debounce_buffer.is_empty() {
                            println!("[防抖处理] 处理 {} 个缓冲事件", debounce_buffer.len());

                            // 取出所有事件并处理
                            let events_to_process = std::mem::take(&mut debounce_buffer);

                            for (path, kind) in events_to_process {
                                // 发送处理后的事件到中央处理器
                                let tx_clone = tx_for_debounce.clone();
                                if let Err(e) = tx_clone.send((path.clone(), kind.clone())).await {
                                    eprintln!("[防抖处理] 发送到中央处理器失败: {}", e);
                                } else {
                                    println!("[防抖处理] 发送防抖后事件: {:?} -> {:?}", kind, path);
                                }
                            }
                        }
                    }

                    // 检查停止信号
                    _ = tokio::time::sleep(Duration::from_millis(10)) => {
                        // 检查共享的停止标志
                        if should_stop.load(Ordering::SeqCst) {
                            println!("[防抖处理] 收到停止信号，退出监控线程: {}", dir_path_clone);
                            continue_running = false;
                            // 处理剩余的缓冲区事件
                            if !debounce_buffer.is_empty() {
                                println!("[防抖处理] 处理退出前的 {} 个缓冲事件", debounce_buffer.len());
                                for (path, kind) in std::mem::take(&mut debounce_buffer) {
                                    if let Err(e) = tx_for_debounce.send((path.clone(), kind.clone())).await {
                                        eprintln!("[防抖处理] 退出前发送失败: {}", e);
                                    }
                                }
                            }
                        }
                    }
                }
            }

            println!("[防抖处理] 线程已完全退出: {}", dir_path_clone);
        });

        // 等待初始化完成
        match init_rx.recv() {
            Ok(Ok(())) => {
                println!("[防抖监控] ✅ 监控线程已成功启动");
                Ok(())
            }
            Ok(Err(e)) => {
                println!("[防抖监控] ❌ 监控线程启动失败: {}", e);
                Err(e)
            }
            Err(e) => {
                println!("[防抖监控] ❌ 无法接收监控线程状态: {:?}", e);
                Err(format!(
                    "Failed to receive status from watcher thread: {:?}",
                    e
                ))
            }
        }
    }

    /// 启动对多个目录的监控
    pub async fn start_monitoring(
        &mut self,
        directories: Vec<String>,
        debounce_time: Duration,
    ) -> std::result::Result<(), String> {
        // 先清理所有现有通道和状态
        let _ = self.stop_monitoring().await;

        // 创建事件处理通道
        let (event_tx_for_central_handler, mut event_rx_for_central_handler) =
            mpsc::channel::<(PathBuf, EventKind)>(100);
        self.event_tx = Some(event_tx_for_central_handler.clone()); // Store the sender for dynamic additions

        // This Arc<FileMonitor> will be used by the central "防抖处理器" task
        let file_monitor_for_processing = Arc::clone(&self.file_monitor);

        // 为每个目录创建停止通道接收器
        let (stop_tx_sender, stop_tx_receiver) = std_mpsc::channel();

        // 启动各个目录的监控
        for dir_path_str in directories {
            if let Err(e) = Self::setup_single_debounced_watch(
                dir_path_str.clone(), // Pass owned string
                debounce_time,
                event_tx_for_central_handler.clone(),
                Some(stop_tx_sender.clone()), // 传递停止通道发送器
            )
            .await
            {
                eprintln!(
                    "[防抖监控] Failed to setup watch for directory {}: {}",
                    dir_path_str, e
                );
                // Optionally, decide if one failure should stop all, or just log and continue
            }
        }

        // 启动事件处理器
        let app_handle_for_processor = self.app_handle.clone();
        let _processor_handle = tokio::spawn(async move {
            let fm_processor = file_monitor_for_processing; // Use the cloned Arc<FileMonitor>

            println!("[防抖处理器] 开始处理事件流");
            while let Some((path, kind)) = event_rx_for_central_handler.recv().await {
                println!("[防抖处理器] 收到事件 {:?} 路径 {:?}", kind, path);

                // 简化事件处理：将所有事件归类为"新增"或"删除"两种类型
                let simplified_kind = match kind {
                    EventKind::Create(_) => {
                        println!("[防抖处理器] 将事件简化为: 文件新增");
                        EventKind::Create(CreateKind::File)
                    }
                    EventKind::Remove(_) => {
                        println!("[防抖处理器] 将事件简化为: 文件删除");
                        EventKind::Remove(RemoveKind::File)
                    }
                    EventKind::Modify(ModifyKind::Name(RenameMode::Both)) => {
                        // 重命名事件：当前路径是目标文件名，认为是新增
                        println!("[防抖处理器] 重命名事件，处理为: 文件新增");
                        EventKind::Create(CreateKind::File)
                    }
                    EventKind::Modify(ModifyKind::Name(RenameMode::To)) => {
                        // 文件移入目录：当作新增
                        println!("[防抖处理器] 文件移入事件，处理为: 文件新增");
                        EventKind::Create(CreateKind::File)
                    }
                    EventKind::Modify(ModifyKind::Name(RenameMode::From)) => {
                        // 文件移出目录：当作删除
                        println!("[防抖处理器] 文件移出事件，处理为: 文件删除");
                        EventKind::Remove(RemoveKind::File)
                    }
                    _ => {
                        // 对于任何其他事件类型，检查文件是否存在
                        if path.exists() && path.is_file() {
                            println!("[防抖处理器] 其他事件类型，文件存在，处理为: 文件新增");
                            EventKind::Create(CreateKind::File)
                        } else {
                            println!("[防抖处理器] 其他事件类型，文件不存在，处理为: 文件删除");
                            EventKind::Remove(RemoveKind::File)
                        }
                    }
                };

                // 使用原始FileMonitor中的process_file_event处理简化后的事件
                // 检查是否为bundle内部文件，如果是，则将事件归因于bundle本身
                let processed_path = if let Some(bundle_path) =
                    crate::file_monitor::FileMonitor::is_inside_macos_bundle(&path)
                {
                    println!(
                        "[防抖处理器] 检测到Bundle内部文件，归因于Bundle本身: {:?}",
                        bundle_path
                    );
                    bundle_path
                } else {
                    path.clone()
                };
                if let Some(ref app_handle) = app_handle_for_processor {
                    if let Some(metadata) = fm_processor
                        .process_file_event(processed_path.clone(), simplified_kind, app_handle)
                        .await
                    {
                        println!("[防抖处理器] 处理文件元数据: {:?}", metadata.file_path);

                        // 获取元数据发送通道并发送元数据
                        if let Some(sender) = fm_processor.get_metadata_sender() {
                            if let Err(e) = sender.send(metadata.clone()).await {
                                eprintln!("[防抖处理器] 发送元数据失败: {}", e);
                            } else {
                                println!(
                                    "[防抖处理器] ✅ 元数据已成功发送: {}",
                                    metadata.file_path
                                );
                            }
                        } else {
                            // 如果元数据发送通道未初始化，尝试手动发送元数据到API
                            // 这是一个临时的解决方案，防止文件被漏掉
                            eprintln!("[防抖处理器] 元数据发送通道未初始化，尝试直接调用API发送元数据: {}", metadata.file_path);
                            // 使用独立的HTTP客户端发送元数据到API
                            let api_host = fm_processor.get_api_host();
                            let api_port = fm_processor.get_api_port();
                            let api_url =
                                format!("http://{}:{}/file-screening/batch", api_host, api_port);

                            // 创建临时客户端
                            let temp_client = reqwest::Client::builder()
                                .timeout(std::time::Duration::from_secs(10))
                                .build();

                            if let Ok(client) = temp_client {
                                // 在新的异步任务中发送请求，避免阻塞主处理流程
                                let metadata_clone = metadata.clone();
                                let app_handle_clone = app_handle_for_processor.clone();
                                tokio::spawn(async move {
                                    // 构建与批处理API兼容的请求格式
                                    let mut request_body = serde_json::Map::new();
                                    let data_list = vec![metadata_clone.clone()];
                                    request_body.insert(
                                        "data_list".to_string(),
                                        serde_json::to_value(&data_list).unwrap_or_default(),
                                    );
                                    request_body.insert(
                                        "auto_create_tasks".to_string(),
                                        serde_json::Value::Bool(true),
                                    );

                                    match client.post(&api_url).json(&request_body).send().await {
                                        Ok(response) if response.status().is_success() => {
                                            println!(
                                                "[防抖处理器] ✅ 成功通过直接API调用发送元数据: {}",
                                                metadata_clone.file_path
                                            );
                                            // 发射 screening-result-updated 事件
                                            if let Some(ref app_handle) = app_handle_clone {
                                                let payload = serde_json::json!({
                                                    "message": "文件筛选成功",
                                                    "file_path": metadata_clone.file_path,
                                                    "timestamp": chrono::Utc::now().to_rfc3339()
                                                });

                                                if let Err(e) = app_handle
                                                    .emit("screening-result-updated", &payload)
                                                {
                                                    eprintln!("[防抖监控] 发射screening-result-updated事件失败: {}", e);
                                                } else {
                                                    println!("[防抖监控] 发射screening-result-updated事件: 文件筛选成功 - {}", metadata_clone.file_path);
                                                }
                                            }
                                        }
                                        Ok(response) => {
                                            let status = response.status();
                                            let body = response.text().await.unwrap_or_default();
                                            eprintln!(
                                                "[防抖处理器] API返回错误: {} - {} - 响应: {}",
                                                status,
                                                metadata_clone.file_path,
                                                &body[..std::cmp::min(body.len(), 200)]
                                            );
                                        }
                                        Err(e) => {
                                            eprintln!(
                                                "[防抖处理器] 直接API调用失败: {} - {}",
                                                e, metadata_clone.file_path
                                            );
                                        }
                                    }
                                });
                            } else {
                                eprintln!("[防抖处理器] 无法创建临时HTTP客户端");
                            }
                        }
                    } else {
                        println!("[防抖处理器] 文件 {:?} 未生成元数据", path);
                    }
                }
            }

            println!("[防抖处理器] 事件处理通道已关闭，退出");
        });

        // 收集所有目录的停止通道
        tokio::spawn(async move {
            let mut watch_stop_channels = HashMap::new();

            // 接收所有注册的停止通道
            while let Ok(stop_tx) = stop_tx_receiver.recv() {
                let dir_id = format!("watch_{}", watch_stop_channels.len() + 1);
                println!("[防抖监控] 收到停止通道 #{}", dir_id);
                watch_stop_channels.insert(dir_id, stop_tx);
            }

            println!(
                "[防抖监控] 停止通道收集器已退出，共收集 {} 个停止通道",
                watch_stop_channels.len()
            );
        });

        Ok(())
    }

    /// 完全停止所有目录的监控
    ///
    /// 这个方法会:
    /// 1. 停止所有监控线程
    /// 2. 清理所有资源
    /// 3. 释放所有通道
    ///
    /// 调用此方法后，必须通过 `start_monitoring` 重新启动监控
    pub async fn stop_monitoring(&mut self) -> std::result::Result<(), String> {
        // 记录操作开始
        println!("[防抖监控] 开始停止所有监控线程...");

        // 1. 尝试通过停止通道发送停止信号
        let watch_channels = {
            let mut channels = self.watch_stop_channels.lock().await;
            std::mem::take(&mut *channels)
        };

        let mut stop_errors = Vec::new();

        // 发送停止信号给每个监控线程
        for (path, stop_tx) in watch_channels.iter() {
            if let Err(e) = stop_tx.send(()) {
                let error_msg = format!(
                    "[防抖监控] 无法发送停止信号到 '{}' 的监控线程: {:?}",
                    path, e
                );
                println!("{}", error_msg);
                stop_errors.push(error_msg);
            } else {
                println!("[防抖监控] 已发送停止信号到 '{}' 的监控线程", path);
            }
        }

        // 2. 清除事件发送通道
        self.event_tx = None;

        // 3. 清空防抖缓冲区
        {
            let mut buffer = self.debounce_buffer.lock().await;
            buffer.clear();
        }

        // 返回结果
        if stop_errors.is_empty() {
            println!("[防抖监控] ✅ 成功停止所有监控线程");
            Ok(())
        } else {
            let msg = format!("[防抖监控] ⚠️ 停止监控时发生 {} 个错误", stop_errors.len());
            println!("{}", msg);
            Err(msg)
        }
    }

    /// 平滑重启监控
    ///
    /// 该方法会:
    /// 1. 停止现有所有监控
    /// 2. 获取最新的监控目录列表
    /// 3. 重新启动监控所有目录
    ///
    /// 调用此方法可以在配置更改后无缝切换监控
    pub async fn _restart_monitoring(
        &mut self,
        debounce_time: Duration,
    ) -> std::result::Result<(), String> {
        println!("[防抖监控] 开始平滑重启监控...");

        // 1. 停止现有监控
        if let Err(e) = self.stop_monitoring().await {
            println!("[防抖监控] 警告：停止监控时发生错误: {}", e);
            // 继续执行，尝试重新启动
        }

        // 2. 获取最新的监控目录
        let directories_to_monitor = {
            let monitor = &self.file_monitor;
            monitor.get_monitored_dirs()
        };

        // 3. 重新启动监控
        if directories_to_monitor.is_empty() {
            println!("[防抖监控] 没有发现需要监控的目录，监控器处于空闲状态");
            return Ok(());
        }

        println!(
            "[防抖监控] 重新启动监控 {} 个目录",
            directories_to_monitor.len()
        );
        self.start_monitoring(directories_to_monitor, debounce_time)
            .await?;

        println!("[防抖监控] ✅ 监控器已平滑重启");
        Ok(())
    }
}
