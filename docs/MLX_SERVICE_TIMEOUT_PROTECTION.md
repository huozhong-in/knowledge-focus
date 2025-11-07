# MLX 服务超时保护机制实现总结

## 📋 实施概述

针对 MLX 底层 GPU 超时崩溃问题（`[METAL] Command buffer execution failed: GPU Timeout`），实施了**方案3：请求超时保护**。

## ✅ 已实现的改进

### 1. 非流式响应超时保护 (`builtin_openai_compat.py`)

**位置**: `_generate_non_streaming_response()` 方法

**特性**:
- ✅ **动态超时计算**：根据 `max_tokens` 和是否包含图片动态调整超时时间
  ```python
  base_timeout = 30.0                              # 基础 30 秒
  token_timeout = max_tokens * 0.2                 # 每个 token 0.2 秒
  image_timeout = 30.0 if images else 0.0          # 有图片额外 30 秒
  timeout_seconds = min(total, 180.0)              # 最大 3 分钟
  ```

- ✅ **超时后的清晰错误信息**：
  ```python
  raise Exception(
      f"Model generation timeout after {timeout_seconds:.1f} seconds. "
      "This may indicate GPU overload. The MLX service might need to be restarted."
  )
  ```

- ✅ **详细的日志记录**：包含请求参数，方便调试
  ```python
  logger.error(
      f"⚠️ Generation timeout after {timeout_seconds:.1f}s - possible GPU overload or hang. "
      f"Request params: max_tokens={max_tokens}, has_images={bool(images)}, temperature={temperature}"
  )
  ```

### 2. 流式响应超时保护 (`builtin_openai_compat.py`)

**位置**: `_stream_response()` 方法

**特性**:
- ✅ **双重超时检查**：
  1. **总超时时间**（最大 5 分钟）：防止整体请求时间过长
  2. **单个 chunk 超时**（30 秒）：防止在某个 token 上卡死

- ✅ **实时超时监控**：
  ```python
  # 检查总超时
  elapsed = time.time() - start_time
  if elapsed > timeout_seconds:
      error_chunk = {"error": {"message": f"Streaming timeout after {elapsed:.1f} seconds"}}
      yield f"data: {json.dumps(error_chunk)}\n\n"
      break
  
  # 检查单个 chunk 超时
  chunk_elapsed = time.time() - last_chunk_time
  if chunk_elapsed > chunk_timeout:
      error_chunk = {"error": {"message": f"No new token for {chunk_elapsed:.1f} seconds"}}
      yield f"data: {json.dumps(error_chunk)}\n\n"
      break
  ```

- ✅ **优雅的错误传递**：通过 SSE 格式返回错误，客户端可以正常解析

### 3. FastAPI 端点并发限制 (`mlx_service.py`)

**位置**: `/v1/chat/completions` 端点

**特性**:
- ✅ **信号量保护**：确保严格单线程处理
  ```python
  MAX_CONCURRENT_REQUESTS = 1
  request_semaphore = Semaphore(MAX_CONCURRENT_REQUESTS)
  
  @app.post("/v1/chat/completions")
  async def chat_completions(request):
      async with request_semaphore:
          # 处理请求
  ```

- ✅ **双重保护**：虽然 VLM manager 内部已有队列，但这里再加一层保险

## ⚠️ 重要限制

### 无法真正取消 MLX 的 C++ 层计算

```
Python 层         C++ 层 (MLX)
  │                   │
  ├─ 超时检测 ────────┼─ GPU 计算中...
  │                   │
  ├─ 取消任务 ────────┼─ GPU 仍在运行 ⚠️
  │                   │
  └─ 返回错误         └─ 最终可能崩溃
```

**说明**：
- ✅ Python 的 `asyncio.wait_for()` 可以取消 Python 任务
- ❌ 但**无法中断** MLX 底层的 C++ GPU 计算
- ❌ 如果 GPU 真的卡死，超时只是让 Python 不等了，GPU 可能仍在消耗资源

## 📊 超时时间配置表

| 场景 | 基础时间 | token 系数 | 图片额外 | 最大时间 |
|------|---------|-----------|---------|---------|
| **非流式** | 30s | 0.2s/token | 30s | 180s (3分钟) |
| **流式（总）** | 60s | 0.3s/token | 30s | 300s (5分钟) |
| **流式（chunk）** | - | - | - | 30s |

### 示例计算

```python
# 非流式，100 tokens，无图片
timeout = min(30 + 100*0.2, 180) = 50s

# 非流式，512 tokens，有图片
timeout = min(30 + 512*0.2 + 30, 180) = 162.4s

# 流式，200 tokens，无图片
timeout = min(60 + 200*0.3, 300) = 120s
```

## 🧪 测试验证

创建了测试脚本 `test_timeout_protection.py`，包含：

1. ✅ **正常请求测试**（100 tokens）- 应该成功完成
2. ✅ **流式请求测试**（150 tokens）- 应该成功完成
3. ⚠️ **超长请求测试**（2000 tokens）- 预期触发超时

**运行测试**：
```bash
cd api
python test_timeout_protection.py
```

**前置条件**：
- MLX 服务必须在 60316 端口运行
- 模型已下载并可用

## 🎯 预期效果

### ✅ 可以解决的问题

1. **Python 层面永久卡死**
   - 超时后 Python 任务会被取消
   - 返回清晰的错误信息
   - 释放 Python 侧资源

2. **提供问题上下文**
   - 详细日志包含请求参数
   - 为后续的进程监控提供线索
   - 帮助诊断 GPU 负载问题

3. **用户体验改善**
   - 不会无限等待
   - 得到明确的错误提示
   - 知道可能需要重启服务

### ❌ 无法解决的问题

1. **GPU 底层崩溃**
   - C++ 层的 Metal 超时仍会发生
   - 进程仍可能崩溃
   - **仍需方案1（进程监控+重启）作为主要防线**

2. **GPU 资源占用**
   - 超时后 GPU 可能仍在计算
   - 直到进程崩溃或手动重启

## 📝 后续计划

### 下一步：实现方案1 - 进程监控与自动重启

**优先级**：🔴 **必须实现**

**实施位置**：`main.py` 的 `lifespan()` 函数

**核心机制**：
```python
@app.on_event("startup")
async def start_mlx_monitor():
    asyncio.create_task(mlx_service_monitor())

async def mlx_service_monitor():
    """持续监控 MLX 服务，崩溃时自动重启"""
    while True:
        await asyncio.sleep(10)  # 每 10 秒检查一次
        
        if not is_port_in_use(60316):
            should_run, model_id = models_builtin.should_auto_load(base_dir)
            
            if should_run:
                logger.warning("MLX service is down, restarting...")
                
                # 退避策略：防止频繁重启
                if restart_too_frequent:
                    wait_time = min(2 ** restart_count, 60)
                    await asyncio.sleep(wait_time)
                
                success = models_builtin._start_mlx_service_process()
                # ...
```

**关键特性**：
- ✅ 定期检查端口占用（60316）
- ✅ 指数退避策略（防止启动风暴）
- ✅ 日志记录每次重启
- ✅ 可配置的检查间隔

### 未来优化：上层业务逻辑优化

**优先级**：🟡 **中等**

**方向**：
1. **用户控制的暂停机制**
   - 在前端添加"暂停自动打标签"按钮
   - 用户可以手动控制批量任务

2. **智能调度策略**
   - 检测 GPU 空闲状态（5 分钟无负载）
   - 每打一个标签停 10 秒
   - 再次检查 GPU 负载

3. **任务优先级动态调整**
   - 高优先级任务优先
   - 批量任务在空闲时才执行

## 📚 相关文件

- ✅ `api/builtin_openai_compat.py` - 超时保护实现
- ✅ `api/mlx_service.py` - 并发限制
- ✅ `api/test_timeout_protection.py` - 测试脚本
- 📝 `api/main.py` - 待实现进程监控（方案1）
- 📝 `tauri-app/src/nav-tagcloud.tsx` - 待添加暂停按钮

## 💡 总结

**方案3 实施评估**：

| 维度 | 评分 | 说明 |
|------|------|------|
| **实施复杂度** | ⭐⭐ (简单) | 约 80 行代码，无外部依赖 |
| **效果** | ⭐⭐⭐ (中等) | 解决 Python 层卡死，但无法阻止 C++ 崩溃 |
| **稳定性** | ⭐⭐⭐⭐ (良好) | 不引入新问题，纯防御性代码 |
| **可维护性** | ⭐⭐⭐⭐⭐ (优秀) | 逻辑清晰，易于调整参数 |

**结论**：✅ **值得实现** - 虽然不能完美解决问题，但能显著改善用户体验和问题诊断能力。

**下一步行动**：
1. ✅ 完成方案3（已完成）
2. 🔴 实现方案1（进程监控+自动重启）- **必须**
3. 🟡 优化上层业务逻辑（可选，稍后讨论）
