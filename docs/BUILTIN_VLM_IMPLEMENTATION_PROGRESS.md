# 内置视觉模型(MLX-VLM)实现进度

## 📋 项目概述

为 Knowledge Focus 添加内置的 MLX-VLM 视觉模型支持，使用 Apple MLX 框架在本地运行小型视觉语言模型，无需依赖 ollama/lm-studio 等外部工具，**真正实现"开箱即用"的隐私保护体验**。

**目标模型**: Qwen3-VL-4B-Instruct-3bit (2.6GB)  
**运行方式**: 集成到主 FastAPI 服务器  
**接口标准**: OpenAI Compatible API (`/v1/chat/completions`)  
**应用场景**: 四种核心能力（VISION/TEXT/STRUCTURED_OUTPUT/TOOL_USE）  
**产品定位**: 强隐私保护，不下载成功不允许进入App

---

## 🎯 核心设计决策（2025-10-18 更新）

### 1. 架构设计

- ✅ **单进程架构**: MLX-VLM 集成到主 FastAPI 进程，通过 `/v1/chat/completions` 端点提供服务
- ✅ **OpenAI 兼容**: 完全兼容 OpenAI Chat Completion API 格式（支持 streaming）
- ✅ **按需加载**: 首次请求时自动加载模型，使用 `asyncio.Lock` 防止并发加载
- ✅ **优先级队列**: 实现 `asyncio.PriorityQueue`，确保用户会话请求优先于批量任务
- ✅ **智能卸载**: 当四项能力全部切换到其他模型时，自动卸载释放内存

### 2. 数据库设计

- ✅ **Provider 记录**: 已在 `db_mgr.py:643-652` 预置 `[Builtin]` provider
  - `provider_type`: "openai"
  - `source_type`: "builtin"
  - `base_url`: "http://127.0.0.1:60315/v1"  （注：与主API共享端口）
- ✅ **Model Configuration**: 已在 `db_mgr.py:782-792` 预置模型配置
  - `model_identifier`: "mlx-community/Qwen3-VL-4B-Instruct-3bit"
  - `display_name`: "Qwen3-VL 4B (3-bit)"
  - `capabilities_json`: ["vision", "text", "structured_output", "tool_use"]
- ✅ **能力绑定**: 已在 `db_mgr.py:800-820` 初始化时自动绑定四项能力
  - `CapabilityAssignment` 表中预置四条记录
  - 用户后续可手动切换到其他模型

### 3. 启动流程（优化设计 2025-10-20）⭐

**核心改进**：
- ✅ **并行启动**: uv 环境初始化与 Splash 界面同时进行，无需等待
- ✅ **权限延后**: 将权限检查移到模型下载后，避免重启中断 uv
- ✅ **简洁交互**: 正常流程只显示阶段提示，异常时智能展开详细日志
- ✅ **智能容错**: 超时检测 + 镜像切换建议 + 清晰错误指引

**优化后的启动流程**：
```
App 启动
  ↓ (并行进行)
  ├─ Tauri sidecar 启动 uv sync (30-90s，首次需下载依赖)
  └─ 显示 Splash 界面
  ↓
[阶段1] Python 环境初始化
  显示: "Initializing Python environment..."
  超时: 30s → 显示日志 + 环境变量重启提示
  ↓ [uv sync 完成]
[阶段2] API 服务器启动
  显示: "Starting API server..."
  超时: 90s (首次启动需编译 __pycache__)
  ↓ [FastAPI 就绪]
[阶段3] 内置模型检查与下载
  3a) 检查: "Checking builtin model..."
  3b) 已下载 → 跳到阶段4
  3c) 下载中: 进度条 (0-100%) + 镜像选择器(仅error显示)
  3d) 失败: 显示错误 + 镜像切换 + 重试按钮
  ↓ [下载成功]
[阶段4] 磁盘访问权限检查 (新位置！)
  显示: "Checking disk access permission..."
  失败: 显示请求权限按钮 + 重启提示
  ↓ [权限通过]
[阶段5] 后端文件扫描启动
  显示: "Starting file scanning..."
  调用: start_backend_scanning()
  ↓
进入主界面 ✨
```

**关键设计决策**：
1. **权限延后的合理性**：
   - 完全磁盘访问权限只影响文件扫描功能
   - 不影响：Python 环境、API 启动、模型下载
   - 延后避免重启时中断 uv，提升稳定性

2. **超时时间设置**：
   - uv sync: 30s (正常) / 90s (网络慢)
   - API 启动: 90s (首次启动需编译 Python 字节码)
   - 模型下载: 无固定超时 (大文件，显示进度即可)

3. **日志显示策略**：
   - 默认：只显示阶段性提示 + loading 动画
   - 超时：自动展开详细日志 + 解决方案
   - 可选："查看详细日志"按钮（折叠/展开）

### 4. 模型生命周期管理

#### 4.1 加载策略（Lazy Loading）
- **触发时机**: 首次收到 `/v1/chat/completions` 请求时
- **加载位置**: `MLXVLMModelManager.ensure_loaded()`
- **并发保护**: 使用 `asyncio.Lock` 确保只加载一次
- **加载流程**:
  ```python
  async with self._lock:
      if model already loaded:
          return
      model, processor = load(model_path, trust_remote_code=True)
      self._model_cache = {"model": model, "processor": processor, ...}
      start queue processor
  ```

#### 4.2 卸载策略（Smart Unloading）
- **触发时机**: 用户在场景配置中切换能力绑定后
- **检查逻辑**: 
  1. 查询 `CapabilityAssignment` 表
  2. 检查 VISION/TEXT/STRUCTURED_OUTPUT/TOOL_USE 四项能力
  3. 如果**全部四项**都不再绑定到内置模型 → 卸载
- **卸载操作**:
  ```python
  self._model_cache.clear()
  gc.collect()  # 强制垃圾回收
  ```

### 5. 请求优先级队列（新增）⭐

**设计目标**: 防止批量打标签任务阻塞用户会话

#### 5.1 优先级定义
```python
class RequestPriority(IntEnum):
    HIGH = 1    # 会话界面请求（用户主动发起）
    LOW = 10    # 批量任务请求（后台自动）
```

#### 5.2 队列实现
- **队列类型**: `asyncio.PriorityQueue`
- **入队方法**: `enqueue_request(request, model_path, priority)`
- **处理器**: 后台任务循环处理队列，优先处理 HIGH 优先级请求
- **超时策略**: 队列空闲 60 秒后自动停止处理器（节省资源）

#### 5.3 API 集成
```python
@router.post("/v1/chat/completions")
async def openai_chat_completions(
    request: dict,
    priority: int = Query(default=10)  # 1=HIGH, 10=LOW
):
    response = await manager.enqueue_request(
        openai_request, 
        model_path,
        RequestPriority(priority)
    )
    return response
```

### 6. 下载机制

#### 6.1 多镜像支持
- **镜像列表**:
  - `https://huggingface.co` (全球)
  - `https://hf-mirror.com` (中国镜像)
- **用户选择**: Splash 页面提供下拉选择
- **自动重试**: 单个镜像失败后不自动切换，由用户手动选择并重试

#### 6.2 进度推送（Bridge Events）
- **事件名称**: `builtin-model-download-progress`
- **Payload 格式**:
  ```json
  {
    "model_id": "qwen3-vl-4b",
    "progress": 45,           // 0-100
    "status": "downloading",  // downloading | completed | failed
    "message": "Downloading... 1.2GB / 2.6GB",
    "speed_mbps": 5.2         // 可选
  }
  ```
- **节流策略**: 每秒最多推送 1 次进度事件

#### 6.3 断点续传
- **原生支持**: `huggingface_hub.snapshot_download()` 自带断点续传
- **缓存位置**: `{base_dir}/builtin_models/models--mlx-community--Qwen3-VL-4B-Instruct-3bit/`

### 7. 简化的架构（相比原方案）

**已删除的复杂逻辑**:
- ❌ MLX Server 子进程管理（端口 60316）
- ❌ 服务器启动/停止/健康检查 API
- ❌ 模型配置页的 Builtin Tab
- ❌ useBuiltinModels Hook 和下载管理 UI
- ❌ 简单的 refcount 卸载逻辑
- ❌ "跳过下载" 降级选项
- ❌ Pin/Unpin UI

**保留的核心功能**:
- ✅ `/v1/chat/completions` OpenAI 兼容端点
- ✅ MLXVLMModelManager 单例模式
- ✅ 下载进度 Bridge Events
- ✅ 数据库能力绑定

---

## 📐 技术实现细节

### 1. 文件结构

```
api/
├── builtin_openai_compat.py       # OpenAI 兼容层 + 优先级队列
│   ├── MLXVLMModelManager         # 模型管理（单例）
│   │   ├── ensure_loaded()        # 按需加载 + 并发保护
│   │   ├── unload_model()         # 卸载模型
│   │   ├── check_and_unload_if_unused()  # 智能卸载检查
│   │   ├── enqueue_request()      # 入队请求
│   │   └── _process_queue()       # 队列处理器
│   ├── RequestPriority            # 优先级枚举
│   └── OpenAI 数据模型
├── models_builtin.py              # 模型下载管理
│   ├── download_model_with_events()  # 异步下载 + 事件推送
│   ├── is_model_downloaded()      # 检查下载状态
│   └── get_model_path()           # 获取模型路径
└── models_api.py                  # API 路由
    ├── POST /models/builtin/initialize      # Splash 调用
    ├── GET  /models/builtin/download-status # 状态查询
    └── POST /v1/chat/completions            # OpenAI 兼容端点

tauri-app/src/
└── splash.tsx                     # 启动页 + 模型下载 UI
    ├── modelStage: checking/downloading/ready/error
    ├── 进度条组件
    ├── 镜像切换下拉框
    └── 重试按钮
```

### 2. 关键代码片段

#### 2.1 Splash 页面状态机
```tsx
type ModelStage = 'checking' | 'downloading' | 'ready' | 'error';

// 状态转换:
// checking → downloading → ready → 进入主界面
//         ↓               ↓
//         error ← ─ ─ ─ ─ ┘
//           ↓ [重试]
//         checking
```

#### 2.2 优先级队列处理
```python
# 高优先级请求（会话）
await manager.enqueue_request(req, path, RequestPriority.HIGH)

# 低优先级请求（批量）
await manager.enqueue_request(req, path, RequestPriority.LOW)

# 队列自动按优先级排序，HIGH 先处理
```

#### 2.3 智能卸载检查
```python
# 在场景配置 API 中调用
@router.post("/models/capabilities/{capability}/assign")
async def assign_capability_to_model(...):
    # 更新绑定
    update_assignment(...)
    
    # 检查是否需要卸载
    vlm_manager = get_vlm_manager()
    await vlm_manager.check_and_unload_if_unused(engine)
```

---

## 📝 实施计划

### Phase 1: 后端核心功能（优先级最高）

#### Task 2.1: Bridge Events 集成
- [x] 修改 `models_builtin.py`
  - 新增 `download_model_with_events()` 异步方法
  - 集成 `bridge_events.push_bridge_event()`
  - 支持镜像参数 (`mirror: str`)
- [x] 新增 API 端点（`models_api.py`）
  - `POST /models/builtin/initialize`
  - `GET /models/builtin/download-status`

#### Task 2.2: 按需加载与并发保护
- [x] 修改 `builtin_openai_compat.py`
  - 在 `MLXVLMModelManager` 中添加 `asyncio.Lock`
  - 实现 `ensure_loaded()` 方法
  - 在 `/v1/chat/completions` 请求入口调用

#### Task 2.3: 优先级队列
- [x] 修改 `builtin_openai_compat.py`
  - 添加 `RequestPriority` 枚举
  - 实现 `asyncio.PriorityQueue`
  - 实现 `enqueue_request()` 和 `_process_queue()`
- [x] 修改 `/v1/chat/completions` API
  - 添加 `priority` 查询参数
  - 改为调用 `enqueue_request()`

#### Task 2.4: 智能卸载
- [ ] 修改 `builtin_openai_compat.py`
  - 实现 `check_and_unload_if_unused()`
  - 实现 `unload_model()`
- [ ] 修改场景配置 API
  - 在能力绑定变更后调用卸载检查

### Phase 2: 前端集成

#### Task 1.1: Splash 页面改造（优化版 2025-10-20）

**Phase 1: 快速改进（已完成基础实现，待优化）** ⚡
- [x] 添加模型下载相关状态管理
  - `modelStage`: checking/downloading/ready/error
  - `downloadProgress`: 0-100
  - `downloadMessage`: 下载详情
  - `selectedMirror`: huggingface/hf-mirror
- [x] 集成 bridge events 监听
  - `model-download-progress`: 更新进度
  - `model-download-completed`: 设置 ready
  - `model-download-failed`: 显示错误
- [x] 添加下载进度 UI 组件
  - 进度条（蓝色，百分比显示）
  - 错误面板（红色，错误信息）
  - 重试按钮

**Phase 2: 体验优化（进行中）** ✨
- [ ] **调整权限检查位置**（30分钟）
  - 将权限检查从初始化移到模型下载成功后
  - 修改 useEffect 依赖顺序
  - 确保不影响 uv 启动流程
  
- [ ] **优化镜像选择器显示**（10分钟）
  - 下载中（downloading）隐藏镜像选择器
  - 仅在 error 状态显示
  - 添加禁用状态提示
  
- [ ] **添加日志折叠功能**（30分钟）
  - 新增 `showDetailedLogs` 状态
  - 添加"查看详细日志"按钮
  - 默认折叠，超时或错误时自动展开
  
- [ ] **简化阶段提示信息**（20分钟）
  - 定义清晰的阶段消息映射
  - 移除技术术语，使用用户友好的文案
  - 各阶段提示：
    - "Initializing Python environment..."
    - "Starting API server..."
    - "Checking builtin model..."
    - "Downloading model... (XX%)"
    - "Checking disk access permission..."
    - "Starting file scanning..."

- [ ] **添加超时检测**（可选，1-2小时）
  - uv 超时检测（30s）
  - API 启动超时检测（90s）
  - 超时后显示环境变量重启提示
  - 超时后自动展开详细日志

**Phase 3: 错误处理增强**（可选） 🎯
- [ ] 添加网络连接检测
- [ ] 优化错误提示文案（中英文）
- [ ] 添加常见问题链接

**实现细节**:
- 使用 `listen()` 监听三个 bridge events
- 在 API 就绪后调用 `/models/builtin/initialize`
- 根据返回的 status ('ready'/'downloading'/'error') 设置 modelStage
- downloading 时显示进度条（下载中隐藏镜像选择器）
- error 时显示错误信息、镜像切换、重试按钮
- ready 后检查权限，权限通过后启动后端扫描

### Phase 3: 代码清理

#### Task 6.1: 删除废弃代码
- [x] `models_builtin.py`: 删除子进程管理代码
- [x] `models_api.py`: 删除旧的 builtin 管理端点
- [ ] `settings-ai-models.tsx`: 删除 `useBuiltinModels` 和 `BuiltinModelsTab`

### Phase 4: 测试与验证

#### Task 7.1: 端到端测试
- [ ] 全新安装测试（删除 DB + 模型文件）
- [ ] 下载失败 + 镜像切换测试
- [ ] 优先级队列测试（并发会话 + 批量任务）
- [ ] 智能卸载测试（切换四项能力）

---

## 🔍 故障排查指南

### 问题 1: 下载卡在 0% 不动

**可能原因**:
- 网络连接问题
- 镜像站点不可访问
- huggingface_hub 依赖未安装

**排查步骤**:
1. 检查 API 日志: `~/Library/Application Support/knowledge-focus.huozhong.in/logs/*.log`
2. 搜索关键字: "download" 或 "builtin-model"
3. 尝试切换镜像站点
4. 检查终端能否访问: `curl -I https://huggingface.co`

### 问题 2: 下载完成但无法进入主界面

**可能原因**:
- 模型文件损坏
- 缓存记录不一致

**解决方案**:
```bash
# 删除模型和缓存
rm -rf ~/Library/Application\ Support/knowledge-focus.huozhong.in/builtin_models/

# 重启 App，重新下载
```

### 问题 3: 推理请求超时或无响应

**可能原因**:
- 模型未加载
- 队列处理器未启动
- 内存不足

**排查步骤**:
1. 检查日志中是否有 "Loading model" 或 "Model loaded"
2. 检查内存占用: `Activity Monitor` → 搜索 "Knowledge Focus"
3. 检查队列状态: 日志中搜索 "Processing request with priority"

### 问题 4: 会话请求仍然被批量任务阻塞

**可能原因**:
- 前端未传递 `priority=1` 参数
- 队列未正确实现优先级排序

**验证方法**:
```bash
# 测试高优先级请求
curl -X POST http://127.0.0.1:60315/v1/chat/completions?priority=1 \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3-vl-4b", "messages": [...]}'
```

---

## 📊 性能指标

### 目标指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 模型加载时间 | < 10 秒 | 首次加载耗时 |
| 单次推理延迟 | < 3 秒 | 纯文本对话 |
| 图片推理延迟 | < 5 秒 | 单图问答 |
| 内存占用 | < 3 GB | 模型加载后 |
| 队列处理延迟 | < 100 ms | 高优先级请求排队时间 |

### 监控方法

```python
# 在日志中记录关键指标
logger.info(f"Model loaded in {duration:.2f}s")
logger.info(f"Request processed in {duration:.2f}s, priority={priority}")
logger.info(f"Queue size: {queue.qsize()}")
```

---

## 🔗 相关文档

- [PRD.md](./PRD.md) - 产品需求文档
- [mlx-vlm GitHub](https://github.com/Blaizzy/mlx-vlm) - MLX-VLM 官方文档
- [db_mgr.py](../api/db_mgr.py) - 数据库模型定义
- [models_api.py](../api/models_api.py) - 模型 API 路由
- [builtin_openai_compat.py](../api/builtin_openai_compat.py) - OpenAI 兼容层
- [splash.tsx](../tauri-app/src/splash.tsx) - 启动页面

---

## 📅 更新历史

- **2025-10-18**: 重大设计变更
  - 将下载流程移至 Splash 页面（阻塞式）
  - 删除"跳过下载"选项（强化隐私保护定位）
  - 新增优先级队列机制
  - 优化卸载策略（基于四项能力绑定检查）
  - 简化架构（移除子进程管理）
