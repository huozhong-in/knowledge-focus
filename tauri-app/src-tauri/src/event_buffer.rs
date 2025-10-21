use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter};
use tokio::sync::RwLock;
use tokio::time::interval;

/// 桥接事件数据结构
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct BridgeEventData {
    pub event: String,
    pub payload: serde_json::Value,
}

/// 事件缓冲策略类型
#[derive(Debug, Clone, Copy)]
pub enum EventBufferStrategy {
    /// 立即转发，不缓冲
    Immediate,
    /// 延迟合并，在指定时间窗口内只发送最后一次
    DelayedMerge(Duration),
    /// 节流，限制发送频率
    Throttle(Duration),
}

/// 缓冲的事件项
#[derive(Debug, Clone)]
struct BufferedEvent {
    data: BridgeEventData,
    last_time: Instant,
    count: u32,
}
/// 智能事件缓冲器
pub struct EventBuffer {
    app_handle: AppHandle,
    buffered_events: Arc<RwLock<HashMap<String, BufferedEvent>>>,
    strategies: HashMap<String, EventBufferStrategy>,
}

impl EventBuffer {
    /// 创建新的事件缓冲器
    pub fn new(app_handle: AppHandle) -> Self {
        let mut strategies = HashMap::new();

        // 配置不同事件的缓冲策略
        Self::configure_strategies(&mut strategies);
        let buffer = Self {
            app_handle,
            buffered_events: Arc::new(RwLock::new(HashMap::new())),
            strategies,
        };

        // 启动定期清理任务
        buffer.start_flush_task();

        buffer
    }

    /// 配置各种事件的缓冲策略
    fn configure_strategies(strategies: &mut HashMap<String, EventBufferStrategy>) {
        use EventBufferStrategy::*;

        // === 立即转发类（高时效性） ===
        // 错误事件必须立即通知用户
        strategies.insert("error-occurred".to_string(), Immediate);
        // 系统状态变化需要立即反映
        strategies.insert("system-status".to_string(), Immediate);
        // 模型状态变化影响用户操作，需要立即通知
        strategies.insert("model-status-changed".to_string(), Immediate);
        // 标签生成模型缺失需要立即通知用户
        strategies.insert("tagging-model-missing".to_string(), Immediate);
        // 多模态向量化关键状态变化需要立即通知
        strategies.insert("multivector-started".to_string(), Immediate);
        strategies.insert("multivector-completed".to_string(), Immediate);
        strategies.insert("multivector-failed".to_string(), Immediate);
        // OAuth 登录成功事件需要立即通知前端
        strategies.insert("oauth-login-success".to_string(), Immediate);

        // === 延迟合并类（可缓冲，适合批量场景） ===
        // 标签更新：用户首次启动或大量文件处理时会频繁更新，5秒内合并
        strategies.insert(
            "tags-updated".to_string(),
            DelayedMerge(Duration::from_secs(5)),
        );
        // 数据库更新：批量操作时会频繁触发，3秒内合并
        strategies.insert(
            "database-updated".to_string(),
            DelayedMerge(Duration::from_secs(3)),
        );
        // 任务完成：避免批量任务完成时的事件风暴，2秒内合并
        strategies.insert(
            "task-completed".to_string(),
            DelayedMerge(Duration::from_secs(2)),
        );

        // === 节流类（控制频率，适合进度更新） ===
        // 解析进度：避免UI更新过于频繁，最多每秒1次
        strategies.insert(
            "file-tagging-progress".to_string(),
            Throttle(Duration::from_secs(1)),
        );
        // 筛选结果更新：避免频繁通知，最多每5秒一次
        strategies.insert(
            "screening-result-updated".to_string(),
            Throttle(Duration::from_secs(5)),
        );
        // 文件处理：批量处理时控制通知频率，每2秒最多一次
        strategies.insert(
            "file-processed".to_string(),
            Throttle(Duration::from_secs(2)),
        );
        // 多模态向量化进度：控制UI更新频率，最多每秒1次
        strategies.insert(
            "multivector-progress".to_string(),
            Throttle(Duration::from_secs(1)),
        );
        
        // === 模型下载事件 ===
        // 模型下载进度：节流处理，避免UI更新过于频繁，最多每秒1次
        strategies.insert(
            "model-download-progress".to_string(),
            Throttle(Duration::from_secs(1)),
        );
        // 模型下载完成：立即通知用户
        strategies.insert("model-download-completed".to_string(), Immediate);
        // 模型下载失败：立即通知用户
        strategies.insert("model-download-failed".to_string(), Immediate);

        // === 工具通道事件（立即转发，保证实时性） ===
        // 工具调用请求：需要立即传递给前端执行
        strategies.insert("tool-call-request".to_string(), Immediate);
        // 工具调用响应：通过HTTP API处理，这里不需要特殊配置
        strategies.insert("tool-call-response".to_string(), Immediate);
        // 工具调用错误：需要立即通知
        strategies.insert("tool-call-error".to_string(), Immediate);

        // === RAG相关事件 ===
        // RAG检索结果：需要立即发送到观察窗
        strategies.insert("rag-retrieval-result".to_string(), Immediate);
        // RAG错误：需要立即通知用户
        strategies.insert("rag-error".to_string(), Immediate);
        // RAG进度：节流处理，避免过于频繁的更新
        strategies.insert(
            "rag-progress".to_string(),
            Throttle(Duration::from_millis(500)),
        );

        // 注意：未在此配置的事件类型将使用默认策略（500ms延迟合并）
    }

    /// 处理incoming事件
    pub async fn handle_event(&self, event_data: BridgeEventData) {
        let strategy = self.strategies.get(&event_data.event).copied().unwrap_or(
            EventBufferStrategy::DelayedMerge(Duration::from_millis(500)),
        ); // 默认策略

        match strategy {
            EventBufferStrategy::Immediate => {
                // 立即发送
                println!("⚡ 立即转发事件: {}", event_data.event);
                self.emit_event(&event_data).await;
            }
            EventBufferStrategy::DelayedMerge(duration) => {
                // 延迟合并处理
                println!(
                    "🔄 延迟合并事件: {} ({}秒窗口)",
                    event_data.event,
                    duration.as_secs()
                );
                self.handle_delayed_merge(event_data, duration).await;
            }
            EventBufferStrategy::Throttle(duration) => {
                // 节流处理
                println!(
                    "⏱️  节流处理事件: {} ({}秒间隔)",
                    event_data.event,
                    duration.as_secs()
                );
                self.handle_throttle(event_data, duration).await;
            }
        }
    }

    /// 处理延迟合并事件
    async fn handle_delayed_merge(&self, event_data: BridgeEventData, _duration: Duration) {
        let mut events = self.buffered_events.write().await;
        let now = Instant::now();

        let event_key = event_data.event.clone();

        if let Some(buffered) = events.get_mut(&event_key) {
            // 更新existing缓冲事件
            buffered.data = event_data; // 保持最新的payload
            buffered.last_time = now;
            buffered.count += 1;
        } else {
            // 创建新的缓冲事件
            events.insert(
                event_key,
                BufferedEvent {
                    data: event_data,
                    last_time: now,
                    count: 1,
                },
            );
        }
    }

    /// 处理节流事件
    async fn handle_throttle(&self, event_data: BridgeEventData, duration: Duration) {
        let mut events = self.buffered_events.write().await;
        let now = Instant::now();
        let event_key = event_data.event.clone();

        if let Some(buffered) = events.get(&event_key) {
            // 检查是否超过了节流间隔
            if now.duration_since(buffered.last_time) < duration {
                // 还在节流期内，更新数据但不发送
                let mut updated = buffered.clone();
                updated.data = event_data;
                updated.last_time = now;
                updated.count += 1;
                events.insert(event_key, updated);
                return;
            }
        }

        // 超过节流间隔或是首次发送，立即发送并更新记录
        events.insert(
            event_key,
            BufferedEvent {
                data: event_data.clone(),
                last_time: now,
                count: 1,
            },
        );

        // 发送事件
        drop(events); // 提前释放锁
        self.emit_event(&event_data).await;
    }

    /// 发送事件到前端
    async fn emit_event(&self, event_data: &BridgeEventData) {
        if let Err(e) = self.app_handle.emit(&event_data.event, &event_data.payload) {
            eprintln!("❌ 发送桥接事件到前端失败: {} - {}", event_data.event, e);
        } else {
            println!(
                "📤 桥接事件已发送到前端: {} (payload: {}字节)",
                event_data.event,
                serde_json::to_string(&event_data.payload)
                    .unwrap_or_default()
                    .len()
            );
        }
    }

    /// 启动定期flush任务
    fn start_flush_task(&self) {
        let buffered_events = self.buffered_events.clone();
        let app_handle = self.app_handle.clone();

        tokio::spawn(async move {
            let mut interval = interval(Duration::from_millis(1000)); // 每秒检查一次

            loop {
                interval.tick().await;

                let mut events_to_send = Vec::new();
                let now = Instant::now();

                // 获取需要发送的事件
                {
                    let mut events = buffered_events.write().await;
                    let mut keys_to_remove = Vec::new();

                    for (key, buffered) in events.iter() {
                        let age = now.duration_since(buffered.last_time);

                        // 如果事件超过一定时间未更新，就发送它
                        let should_send = match key.as_str() {
                            "tags-updated" | "database-updated" => age >= Duration::from_secs(5),
                            "task-completed" => age >= Duration::from_secs(2),
                            "file-processed" => age >= Duration::from_secs(2),
                            _ => age >= Duration::from_secs(1), // 默认1秒
                        };

                        if should_send {
                            events_to_send.push(buffered.data.clone());
                            keys_to_remove.push(key.clone());
                        }
                    }

                    // 移除已发送的事件
                    for key in keys_to_remove {
                        events.remove(&key);
                    }
                }

                // 发送事件（在锁外部进行）
                for event_data in events_to_send {
                    if let Err(e) = app_handle.emit(&event_data.event, &event_data.payload) {
                        eprintln!("❌ 定期flush时发送事件失败: {} - {}", event_data.event, e);
                    } else {
                        println!("⏰ 定期flush发送桥接事件: {} (延迟发送)", event_data.event);
                    }
                }
            }
        });
    }
}
