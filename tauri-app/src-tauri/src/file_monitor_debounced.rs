use notify::{EventKind, RecursiveMode, Watcher};
use notify::event::{ModifyKind, RemoveKind, RenameMode, CreateKind};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc::{self, Sender};
use crate::file_monitor::FileMonitor;
use std::collections::HashMap;
use tokio::sync::Mutex;
use std::sync::mpsc as std_mpsc;

// 定义简化的文件事件类型
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SimpleFileEvent {
    Added(PathBuf),    // 文件新增（包括创建和移入）
    Removed(PathBuf),  // 文件删除（包括删除和移出）
}

/// 防抖动文件监控器，基于 `notify_debouncer_full` 库实现
#[derive(Clone)]
pub struct DebouncedFileMonitor {
    /// 指向基础FileMonitor的引用，用于处理文件元数据和规则
    file_monitor: Arc<FileMonitor>,
    /// 事件发送通道，用于处理处理后的文件变更
    event_tx: Option<Sender<(PathBuf, notify::EventKind)>>,
    /// 防抖事件缓冲区
    debounce_buffer: Arc<Mutex<HashMap<PathBuf, notify::EventKind>>>,
}

impl DebouncedFileMonitor {
    /// 创建新的防抖动文件监控器
    pub fn new(file_monitor: Arc<FileMonitor>) -> Self {
        DebouncedFileMonitor {
            file_monitor,
            event_tx: None,
            debounce_buffer: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    /// Helper function to set up a debounced watch for a single directory.
    /// This function spawns a task that owns the debouncer after successful setup.
    async fn setup_single_debounced_watch(
        dir_path_str: String, // Owned String
        debounce_time: Duration,
        tx_to_central_handler: Sender<(PathBuf, notify::EventKind)>,
    ) -> std::result::Result<(), String> {
        println!("[防抖监控] Setting up watch for directory: {}", dir_path_str);

        // 使用标准 notify 库而不是 debouncer
        println!("[文件监控] 直接使用 notify 库进行监控，增加自定义防抖机制");
        
        // 创建事件缓冲区和防抖处理通道
        let (debounce_tx, mut debounce_rx) = mpsc::channel::<(PathBuf, notify::EventKind)>(100);
        
        // 克隆一个 sender 用于回调函数
        let dir_path_for_watcher = dir_path_str.clone();
        
        // 创建一个同步通道用于保持通信
        let (init_tx, init_rx) = std_mpsc::channel();
        
        // 在单独的线程中创建和运行 watcher
        // 这样避免了异步上下文的复杂性
        std::thread::spawn(move || {
            println!("[文件监控-线程] 启动 watcher 线程");
            
            // 创建 watcher
            let mut watcher = match notify::recommended_watcher(move |res: std::result::Result<notify::Event, notify::Error>| {
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
                                if let Err(e) = debounce_tx.send((path.clone(), processed_kind)).await {
                                    eprintln!("🔔❌ 发送到防抖队列失败: {}", e);
                                } else {
                                    println!("🔔✅ 事件已发送到防抖队列: {:?} -> {:?}", processed_kind, path);
                                }
                            }
                        });
                    }
                    Err(e) => {
                        eprintln!("🔔❌ 监控错误: {:?}", e);
                    }
                }
                println!("🔔🔔🔔 NOTIFY CALLBACK END 🔔🔔🔔");
            }) {
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
            
            // 设置监控
            match watcher.watch(watch_path, RecursiveMode::Recursive) {
                Ok(_) => {
                    println!("[文件监控-线程] ✅ 成功设置监控: {}", dir_path_for_watcher);
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
            let mut tick_count = 0;
            loop {
                // 让线程休眠10秒
                std::thread::sleep(Duration::from_secs(10));
                tick_count += 1;
                println!("[文件监控-心跳] #{} Watcher for '{}' is still alive", 
                        tick_count, &dir_path_for_watcher);
                
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
            
            loop {
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
                }
            }
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
                Err(format!("Failed to receive status from watcher thread: {:?}", e))
            }
        }
    }

    /// 启动对多个目录的监控
    pub async fn start_monitoring(
        &mut self, 
        directories: Vec<String>, 
        debounce_time: Duration
    ) -> std::result::Result<(), String> {
        // 创建事件处理通道
        let (event_tx_for_central_handler, mut event_rx_for_central_handler) = mpsc::channel::<(PathBuf, EventKind)>(100);
        self.event_tx = Some(event_tx_for_central_handler.clone()); // Store the sender for dynamic additions
        
        // This Arc<FileMonitor> will be used by the central "防抖处理器" task
        let file_monitor_for_processing = Arc::clone(&self.file_monitor);
        
        // 启动各个目录的监控
        for dir_path_str in directories {
            if let Err(e) = Self::setup_single_debounced_watch(
                dir_path_str.clone(), // Pass owned string
                debounce_time,
                event_tx_for_central_handler.clone(),
            ).await {
                eprintln!("[防抖监控] Failed to setup watch for directory {}: {}", dir_path_str, e);
                // Optionally, decide if one failure should stop all, or just log and continue
            }
        }
        
        // 启动事件处理器
        tokio::spawn(async move {
            let fm_processor = file_monitor_for_processing; // Use the cloned Arc<FileMonitor>
            
            println!("[防抖处理器] 开始处理事件流");
            while let Some((path, kind)) = event_rx_for_central_handler.recv().await {
                println!("[防抖处理器] 收到事件 {:?} 路径 {:?}", kind, path);
                
                // 简化事件处理：将所有事件归类为"新增"或"删除"两种类型
                let simplified_kind = match kind {
                    EventKind::Create(_) => {
                        println!("[防抖处理器] 将事件简化为: 文件新增");
                        EventKind::Create(CreateKind::File)
                    },
                    EventKind::Remove(_) => {
                        println!("[防抖处理器] 将事件简化为: 文件删除");
                        EventKind::Remove(RemoveKind::File)
                    },
                    EventKind::Modify(ModifyKind::Name(RenameMode::Both)) => {
                        // 重命名事件：当前路径是目标文件名，认为是新增
                        println!("[防抖处理器] 重命名事件，处理为: 文件新增");
                        EventKind::Create(CreateKind::File)
                    },
                    EventKind::Modify(ModifyKind::Name(RenameMode::To)) => {
                        // 文件移入目录：当作新增
                        println!("[防抖处理器] 文件移入事件，处理为: 文件新增");
                        EventKind::Create(CreateKind::File)
                    },
                    EventKind::Modify(ModifyKind::Name(RenameMode::From)) => {
                        // 文件移出目录：当作删除
                        println!("[防抖处理器] 文件移出事件，处理为: 文件删除");
                        EventKind::Remove(RemoveKind::File)
                    },
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
                if let Some(metadata) = fm_processor.process_file_event(path.clone(), simplified_kind).await {
                    println!("[防抖处理器] 处理文件元数据: {:?}", metadata.file_path);
                    
                    // 获取元数据发送通道并发送元数据
                    if let Some(sender) = fm_processor.get_metadata_sender() {
                        if let Err(e) = sender.send(metadata).await {
                            eprintln!("[防抖处理器] 发送元数据失败: {}", e);
                        }
                    } else {
                        eprintln!("[防抖处理器] 无法获取元数据发送通道 from FileMonitor");
                    }
                } else {
                    println!("[防抖处理器] 文件 {:?} 未生成元数据", path);
                }
            }
            
            println!("[防抖处理器] 事件处理通道已关闭，退出");
        });
        
        Ok(())
    }

    /// Adds a new directory to be monitored with debouncing.
    pub async fn add_directory_to_watch(&self, dir_path: String, debounce_time: Duration) -> std::result::Result<(), String> {
        let tx_to_central_handler = match self.event_tx.as_ref() {
            Some(tx) => tx.clone(),
            None => return Err("DebouncedFileMonitor's event_tx is not initialized. Call start_monitoring first.".to_string()),
        };

        // Call the static setup function
        Self::setup_single_debounced_watch(
            dir_path, // dir_path is already String
            debounce_time,
            tx_to_central_handler,
        ).await?;

        Ok(())
    }
}
