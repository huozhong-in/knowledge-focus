# MLX 服务迁移进度跟踪

**日期**: 2025-10-28  
**目标**: 将 MLX-VLM 服务完全迁移到独立进程（60316），清理 60315 的冗余端点

## 架构变更

### 变更前
```
进程 1: FastAPI 主服务 (60315)
├─ /chat/agent-stream (Vercel AI SDK)
├─ /v1/chat/completions (OpenAI 兼容) ← 冗余
│   └─ MLXVLMModelManager (60315 进程内)
├─ multivector 任务
└─ 打标签任务
```

### 变更后
```
进程 1: FastAPI 主服务 (60315)
├─ /chat/agent-stream (Vercel AI SDK)
│   └─ PydanticAI → HTTP 调用 60316
├─ multivector 任务 → HTTP 调用 60316
└─ 打标签任务 → HTTP 调用 60316

进程 2: MLX 服务 (60316) - 独立 FastAPI
└─ /v1/chat/completions (OpenAI 兼容)
    └─ MLXVLMModelManager (独占 Metal GPU)
```

## 任务清单

- [x] **任务 0**: 修正 base_url 配置（60315 → 60316）
  - 文件: `api/db_mgr.py` line 650
  - 状态: ✅ 已完成

- [x] **任务 1**: 删除 60315 的冗余 OpenAI 兼容端点
  - 文件: `api/models_api.py`
  - 删除 lines 787-885: `/v1/chat/completions` 端点 ✅
  - 删除 line 44: `get_mlx_vlm_manager()` 函数 ✅
  - 清理 imports: 部分完成（待任务 2 确认）

- [x] **任务 2**: 修改能力分配端点
  - 文件: `api/models_api.py` line 192 ✅
  - 移除 `vlm_manager` 参数 ✅
  - 改为调用 `builtin_mgr.ensure_mlx_service_running()` ✅
  - 清理 imports ✅

- [x] **任务 3**: 实现进程管理逻辑
  - 文件: `api/utils.py` ✅
    - 新增 `is_port_in_use()` 函数
  - 文件: `api/models_builtin.py` ✅
    - 新增 `ensure_mlx_service_running()` 方法
    - 新增 `_start_mlx_service_process()` 方法

- [x] **任务 4**: 集成到主服务启动流程
  - 文件: `api/main.py` ✅
    - 在 lifespan startup 调用 `ensure_mlx_service_running()`
    - 在 lifespan shutdown 清理 60316 进程
  - 文件: `api/mlx_service.py` ✅
    - 添加模型路径解析逻辑（支持 alias 和 HF model ID）

- [ ] **任务 5**: 完整测试
  - 前端聊天功能
  - 多模态向量化（图片描述）
  - 智能卸载逻辑
  - 并发场景

## 详细记录

### 任务 0: 修正 base_url 配置 ✅

**时间**: 2025-10-28

**文件**: `api/db_mgr.py`

**修改**:
```python
# Line 650
- "base_url": "http://127.0.0.1:60315/v1",
+ "base_url": "http://127.0.0.1:60316/v1",
```

**说明**: 内置 MLX 模型的 base_url 从 60315 改为 60316，确保 PydanticAI 调用独立的 MLX 服务。

---

### 任务 1: 删除 60315 的冗余 OpenAI 兼容端点 ✅

**时间**: 2025-10-28

**文件**: `api/models_api.py`

**删除内容**:

1. **Lines 787-885**: `/v1/chat/completions` 端点
   - 这个端点与 60316 的端点功能重复
   - 删除后，所有 OpenAI 兼容调用都通过 60316

2. **Line 44**: `get_mlx_vlm_manager()` 函数
   - 60315 不再需要 MLX VLM 管理器
   - 60316 有自己独立的管理器实例

3. **Lines 17-22**: 清理 imports
   - 删除 `from builtin_openai_compat import (...)`
   - 移除 `MLXVLMModelManager`, `OpenAIChatCompletionRequest`, `RequestPriority`, `get_vlm_manager`

**影响**: 60315 不再直接处理 MLX-VLM 推理，所有推理请求转发到 60316。

---

### 任务 2: 修改能力分配端点 ✅

**时间**: 2025-10-28

**文件**: `api/models_api.py` line 192

**修改内容**:

```python
# 旧代码
@router.post("/models/global_capability/{model_capability}")
async def assign_global_capability_to_model(
    vlm_manager: MLXVLMModelManager = Depends(get_mlx_vlm_manager)  # ❌
):
    # 触发智能卸载检查
    unloaded = await vlm_manager.check_and_unload_if_unused(engine)

# 新代码
@router.post("/models/global_capability/{model_capability}")
async def assign_global_capability_to_model(
    builtin_mgr: ModelsBuiltin = Depends(get_models_builtin_manager)  # ✅
):
    # 触发智能进程管理
    is_running = builtin_mgr.ensure_mlx_service_running()
```

**说明**: 
- 从"内存卸载"改为"进程管理"
- 自动启动或停止 60316 进程
- 配置变更时立即生效

---

### 任务 3: 实现进程管理逻辑 ✅

**时间**: 2025-10-28

#### 3.1 新增 `is_port_in_use()` 函数

**文件**: `api/utils.py`

```python
def is_port_in_use(port: int) -> bool:
    """检查指定端口是否被占用"""
    # 跨平台实现（Windows / macOS / Linux）
    # 使用 netstat (Windows) 或 lsof (Unix)
```

#### 3.2 新增进程管理方法

**文件**: `api/models_builtin.py`

**新方法 1**: `ensure_mlx_service_running()`
```python
def ensure_mlx_service_running(self) -> bool:
    """
    根据配置自动启动或停止 MLX 服务进程
    
    逻辑：
    1. 调用 should_auto_load() 检查是否需要 MLX 服务
    2. 如果需要 + 端口未占用 → 启动进程
    3. 如果不需要 + 端口被占用 → kill 进程
    4. 其他情况保持现状
    """
```

**新方法 2**: `_start_mlx_service_process()`
```python
def _start_mlx_service_process(self) -> bool:
    """
    启动独立的 MLX 服务进程
    
    实现：
    1. 使用 subprocess.Popen 启动 mlx_service.py
    2. 传递参数: --port 60316
    3. 后台运行（start_new_session=True）
    4. 等待 2 秒验证进程是否启动成功
    """
```

---

### 任务 4: 集成到主服务启动流程 ✅

**时间**: 2025-10-28

#### 4.1 主服务启动时检查

**文件**: `api/main.py`

**位置**: `lifespan()` 函数，`yield` 之前

```python
# 启动 MLX 服务进程（如果需要）
try:
    from models_builtin import ModelsBuiltin
    logger.info("检查是否需要启动 MLX 服务...")
    builtin_mgr = ModelsBuiltin(engine=app.state.engine, base_dir=app.state.db_directory)
    is_running = builtin_mgr.ensure_mlx_service_running()
    if is_running:
        logger.info("MLX 服务已确保运行在端口 60316")
    else:
        logger.info("MLX 服务无需运行或已停止")
except Exception as mlx_err:
    logger.error(f"MLX 服务启动检查失败: {str(mlx_err)}", exc_info=True)
    # 不中断启动流程
```

#### 4.2 主服务关闭时清理

**位置**: `lifespan()` 函数，`finally` 块

```python
# 停止 MLX 服务进程（如果在运行）
try:
    from utils import is_port_in_use, kill_process_on_port
    MLX_SERVICE_PORT = 60316
    if is_port_in_use(MLX_SERVICE_PORT):
        logger.info(f"停止 MLX 服务进程（端口 {MLX_SERVICE_PORT}）...")
        success = kill_process_on_port(MLX_SERVICE_PORT)
        if success:
            logger.info("MLX 服务进程已停止")
        else:
            logger.warning("MLX 服务进程停止失败")
except Exception as mlx_cleanup_err:
    logger.error(f"停止 MLX 服务失败: {str(mlx_cleanup_err)}", exc_info=True)
```

#### 4.3 MLX 服务模型路径解析

**文件**: `api/mlx_service.py`

**修改**: `chat_completions` 函数

```python
# 解析模型路径
model_id = request.model

# 支持两种模型标识符:
# 1. model_id (如 "qwen3-vl-4b") - 我们自定义的 alias
# 2. hf_model_id (如 "mlx-community/Qwen3-VL-4B-Instruct-3bit")

if model_id in BUILTIN_MODELS:
    # 使用 alias，获取 HF model ID
    model_path = BUILTIN_MODELS[model_id]["hf_model_id"]
else:
    # 尝试通过 HF model ID 查找
    for mid, config in BUILTIN_MODELS.items():
        if config["hf_model_id"] == model_id:
            model_path = config["hf_model_id"]
            break
```

**说明**: 
- 支持前端传递 `qwen3-vl-4b`（alias）或完整 HF model ID
- 自动解析为正确的模型路径
- 保持与 `models_builtin.py` 的一致性

---

### 任务 5: 完整测试

### 为什么选择 Python 管理子进程？

| 维度 | Python 方案 | Rust 方案 |
|------|------------|-----------|
| 实现复杂度 | ✅ 简单（utils.py 已有代码） | ❌ 复杂（需要 Tauri sidecar） |
| 启动方式 | ✅ 按需启动（节省资源） | ⚠️ Tauri 启动时自动启动 |
| 生命周期管理 | ✅ 完全控制 | ⚠️ 依赖 Tauri |
| 调试友好 | ✅ 可独立测试 | ⚠️ 必须通过 Tauri |

**结论**: 选择 Python 方案，已有代码基础，实现简单，风险低。

### 进程管理策略

**启动时机**:
- main.py 的 `@app.on_event("startup")` 时检查配置
- 如果任何能力使用内置 MLX → 启动 60316
- 如果所有能力都不用内置 MLX → 不启动

**停止时机**:
- 能力配置变更时检查
- 如果所有能力都切换到其他模型 → kill 60316 进程
- main.py 的 `@app.on_event("shutdown")` 时清理

---

## 遗留问题

### ❌ Bug 修复: 流式响应方法名错误 ✅

**时间**: 2025-10-28

**文件**: `api/builtin_openai_compat.py` line 309

**问题**: 前端聊天返回 500 错误

**根因分析**:
```
AttributeError: 'MLXVLMModelManager' object has no attribute '_generate_streaming_response'. 
Did you mean: '_generate_non_streaming_response'?
```

从 MLX 服务日志发现：
- 打标签使用 `agent.run_sync()` + `stream=False` → **正常**
- 前端聊天使用 `agent.iter()` + `stream=True` → **500错误**
- 原因：`_generate_completion_internal()` 调用了不存在的 `_generate_streaming_response()`
- 实际方法名是 `_stream_response()`

**修复内容**:
```python
# 旧代码（line 309）
return await self._generate_streaming_response(
    request, model, processor, formatted_prompt, image_urls
)

# 新代码
return await self._stream_response(
    request, model, processor, formatted_prompt, image_urls
)
```

**验证方式**:
1. 重启 MLX 服务进程
2. 前端聊天测试
3. 检查日志无 AttributeError

---

## 测试计划

### 1. 基础功能测试
- [x] 启动主服务，检查 60316 是否自动启动
- [x] 前端聊天界面发送消息（✅ 已修复流式响应bug）
- [x] 检查调用链：60315 → 60316
- [x] 检查响应正常

**已解决问题**: ✅ 流式响应方法名错误（`_generate_streaming_response` → `_stream_response`）

**MLX 服务日志位置**:
```bash
# 主服务日志
tail -f ~/Library/Application\ Support/knowledge-focus.huozhong.in/logs/api_*.log

# MLX 服务日志（新增）
tail -f ~/Library/Application\ Support/knowledge-focus.huozhong.in/logs/mlx_service_*.log
```

### 2. 多模态测试
- [x] pin包含图片的 PDF
- [x] 检查 Docling 是否调用 60316
- [x] 检查图片描述是否生成
- [x] 检查 chunks 包含图片描述

### 3. 智能卸载测试
- [x] 设置所有能力使用其他模型
- [x] 检查 60316 进程是否被 kill
- [x] 切换回内置 MLX
- [x] 检查 60316 是否重新启动

### 4. 并发测试
- [x] 同时进行聊天 + 向量化
- [x] 检查无 Metal 冲突
- [x] 检查响应稳定

### 5. 边界情况测试
- [x] 主服务重启
- [x] 60316 进程异常退出
- [x] 配置频繁切换

**详细测试步骤请参考上面的"任务 5"部分**

---

## 快速测试

运行自动化测试脚本：

```bash
cd api
chmod +x test_mlx_migration.sh
./test_mlx_migration.sh
```

这个脚本会自动验证：
- ✅ 端口状态检查
- ✅ 主服务启动 (60315)
- ✅ MLX 服务自动启动 (60316)
- ✅ 健康检查测试
- ✅ 日志位置显示

---

## 回滚方案

如果迁移出现问题，回滚步骤：

1. 恢复 `db_mgr.py` 的 base_url 为 60315
2. 恢复 `models_api.py` 的 `/v1/chat/completions` 端点
3. 停止 60316 进程
4. 重启 60315 服务

---

**最后更新**: 2025-10-28
