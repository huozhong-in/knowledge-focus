# 内置模型功能集成总结

## 已完成的改进

### 问题背景

用户指出我们应该利用现有的**统一桥接器机制**来实现模型下载进度通知，而不是重新实现一套 `ProgressReporter`。

统一桥接器机制的优势：
1. **零配置**: 不需要额外的网络端口或配置
2. **实时推送**: Python → stdout → Rust → Tauri IPC → TypeScript
3. **已有基础设施**: `bridge_events.py`, `event_buffer.rs`, `useBridgeEvents.ts` 已经完善
4. **与现有功能一致**: 标签更新、RAG 检索、多模态向量化都使用相同机制

### 完成的改进

#### 1. Python 端 (models_builtin.py)

**改进前**: 使用自定义的 `ProgressReporter` 类，通过回调函数传递进度

**改进后**: 集成 `BridgeEventSender`，通过统一桥接器推送事件

```python
# 在 download_model() 中
from bridge_events import BridgeEventSender
bridge_events = BridgeEventSender(source="models_builtin")

class ProgressReporter(tqdm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bridge = bridge_events  # 保存桥接器引用
        
    def update(self, n=1):
        super().update(n)
        if self.total:
            # 通过统一桥接器发送进度
            self.bridge.model_download_progress(
                model_name=self.model_name,
                current=self.n,
                total=self.total,
                message=f"正在下载 {self.desc}: {progress_pct}%",
                stage="downloading"
            )
```

**关键变化**:
- ✅ 保留了 `progress_callback` 参数供测试使用
- ✅ 主要进度通知通过 `bridge_events.model_download_progress()` 发送
- ✅ 完成时调用 `bridge_events.model_download_completed()`
- ✅ 失败时调用 `bridge_events.model_download_failed()`

#### 2. Rust 端 (event_buffer.rs)

**新增配置**: 为模型下载事件添加缓冲策略

```rust
// 模型下载进度：节流处理，避免UI更新过于频繁，最多每秒1次
strategies.insert(
    "model-download-progress".to_string(),
    Throttle(Duration::from_secs(1)),
);

// 模型下载完成：立即通知用户
strategies.insert("model-download-completed".to_string(), Immediate);

// 模型下载失败：立即通知用户
strategies.insert("model-download-failed".to_string(), Immediate);
```

**策略说明**:
- **进度事件**: 节流策略，每秒最多发送1次（避免UI过度刷新）
- **完成/失败事件**: 立即转发策略（用户需要立刻知道结果）

#### 3. TypeScript 前端 (useBridgeEvents.ts)

**新增事件类型定义**:

```typescript
interface EventHandlers {
  // ... 其他事件
  'model-download-progress'?: (payload: BridgeEventPayload) => void;
  'model-download-completed'?: (payload: BridgeEventPayload) => void;
  'model-download-failed'?: (payload: BridgeEventPayload) => void;
}
```

**新增 Toast 通知处理**:

```typescript
case 'model-download-progress':
  // 进度事件一般不弹toast，由UI组件自己处理进度条
  if (data.stage === 'starting' || data.stage === 'connecting') {
    toast.info('模型下载', { description: data.message });
  }
  break;

case 'model-download-completed':
  toast.success('模型下载完成', {
    description: data.message || `${data.model_name} 已成功下载`,
    duration: 4000
  });
  break;

case 'model-download-failed':
  toast.error('模型下载失败', {
    description: data.error_message,
    duration: 6000
  });
  break;
```

#### 4. API 端点 (models_api.py)

**简化下载端点**: 移除了本地进度跟踪，依赖桥接事件

```python
@router.post("/models/builtin/{model_id}/download")
async def download_builtin_model(model_id: str):
    """
    下载进度通过统一桥接器事件推送到前端：
    - model-download-progress: 下载进度更新（节流，每秒最多1次）
    - model-download-completed: 下载完成
    - model-download-failed: 下载失败
    """
    def download_task():
        try:
            # 下载进度会自动通过 bridge_events 推送到前端
            models_builtin.download_model(model_id)
        except Exception as e:
            logger.error(f"Download failed: {e}", exc_info=True)
    
    thread = Thread(target=download_task, daemon=True)
    thread.start()
    
    return {"success": True, "message": "Download started"}
```

## 事件流程图

```
用户点击"下载模型"按钮
  ↓
前端 POST /models/builtin/{model_id}/download
  ↓
API 在后台线程启动下载
  ↓
ModelsBuiltin.download_model()
  ├─> 每下载一块数据
  │   └─> ProgressReporter.update()
  │       └─> bridge_events.model_download_progress()
  │           └─> print(JSON) to stdout
  │               └─> Rust event_buffer (节流：1秒最多1次)
  │                   └─> window.emit('model-download-progress', payload)
  │                       └─> useBridgeEvents() 监听器
  │                           └─> 更新 React state (进度条)
  │
  ├─> 下载完成
  │   └─> bridge_events.model_download_completed()
  │       └─> Rust event_buffer (立即转发)
  │           └─> Toast 通知 + 刷新模型列表
  │
  └─> 下载失败
      └─> bridge_events.model_download_failed()
          └─> Rust event_buffer (立即转发)
              └─> Toast 错误通知
```

## 优势总结

### 1. 架构一致性
- 与标签更新、RAG 检索、多模态向量化等功能使用相同机制
- 减少代码重复，降低维护成本

### 2. 性能优化
- Rust 端节流策略避免了频繁的 IPC 调用
- 前端只需监听事件，无需轮询

### 3. 用户体验
- 实时进度反馈（1秒刷新一次）
- 自动 Toast 通知（可选）
- 无缝集成到现有 UI

### 4. 可测试性
- Python 端保留 `progress_callback` 参数供单元测试使用
- 桥接事件独立于测试框架，可以通过捕获 stdout 验证

## 下一步：前端 UI 集成

已创建详细的集成指南：`BUILTIN_MODEL_DOWNLOAD_EVENTS.md`

包含：
- 完整的事件 Payload 结构说明
- React 组件集成示例（带进度条）
- Toast 通知行为说明
- 最佳实践和调试建议

## 相关文件列表

### 后端
- `api/models_builtin.py` - 模型管理核心逻辑
- `api/bridge_events.py` - 桥接事件发送器（新增 model_download_* 方法）
- `api/models_api.py` - REST API 端点

### 桥接层
- `tauri-app/src-tauri/src/event_buffer.rs` - 事件缓冲和转发策略

### 前端
- `tauri-app/src/hooks/useBridgeEvents.ts` - 事件监听 Hook
- (待实现) Settings 页面 - 模型下载 UI 组件

### 文档
- `docs/UNIFY_BRIDGE.md` - 统一桥接器机制说明
- `docs/BUILTIN_MODEL_DOWNLOAD_EVENTS.md` - 前端集成指南
- `docs/BUILTIN_MODEL_INTEGRATION_SUMMARY.md` - 本文档

## 测试验证

### 已有测试
- `test_models_builtin_phase1_3.py` - 下载功能测试（使用 progress_callback）
- `test_builtin_api_phase2.py` - API 端点测试

### 需要添加的测试
- 前端集成测试：监听桥接事件并更新 UI
- E2E 测试：完整的下载流程（从点击按钮到显示完成）

## 待办事项 (Phase 3)

1. **前端 Settings 页面实现**
   - [ ] 创建 BuiltinModelsSection 组件
   - [ ] 实现 ModelCard 组件（带进度条）
   - [ ] 集成 useBridgeEvents 监听下载事件
   - [ ] 实现下载按钮和状态管理

2. **测试和验证**
   - [ ] 测试下载进度实时更新
   - [ ] 测试 Toast 通知显示
   - [ ] 测试多个模型同时下载（如果支持）
   - [ ] 测试网络错误和重试机制

3. **文档完善**
   - [ ] 为 Settings 页面添加用户指南
   - [ ] 更新 README 添加内置模型功能说明
