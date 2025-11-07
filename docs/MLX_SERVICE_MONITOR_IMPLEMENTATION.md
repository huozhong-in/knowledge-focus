# MLX 服务进程监控与自动重启实施总结

## 📋 实施概述

实现了 **方案1：supervisord 式的进程监控与自动重启机制**，这是防止 MLX 底层 GPU 超时崩溃的**主要防线**。

## ✅ 已实现的功能

### 1. 监控任务 (`mlx_service_monitor`)

**位置**: `api/main.py` (第 656 行开始)

**核心特性**:

#### 🔍 定期健康检查
- 每 10 秒检查一次端口 60316 是否在使用
- 检查是否配置了需要 MLX 服务运行
- 轻量级检测，不影响主服务性能

#### 🔄 自动重启机制
```python
if not is_port_in_use(60316):
    should_run, model_id = builtin_mgr.should_auto_load(base_dir)
    
    if should_run:
        logger.warning("MLX service is DOWN, restarting...")
        success = builtin_mgr._start_mlx_service_process()
```

#### 🛡️ 指数退避策略（防止启动风暴）
```python
# 配置参数
CHECK_INTERVAL = 10        # 检查间隔（秒）
RESTART_COOLDOWN = 60      # 重启冷却时间（秒）
MAX_RESTART_ATTEMPTS = 5   # 单位时间内最大重启次数

# 退避算法
if restart_count >= MAX_RESTART_ATTEMPTS:
    backoff_time = min(2 ** (restart_count - MAX_RESTART_ATTEMPTS + 1), 300)
    logger.error(f"Backing off for {backoff_time}s before retry")
    await asyncio.sleep(backoff_time)
```

**退避时间表**:
| 重启次数 | 退避时间 | 说明 |
|---------|---------|------|
| 1-5 | 5秒 | 正常重试 |
| 6 | 2秒 | 开始退避 |
| 7 | 4秒 | 指数增长 |
| 8 | 8秒 | |
| 9 | 16秒 | |
| 10+ | 32-300秒 | 最大 5 分钟 |

#### 📊 状态追踪与日志
```python
# 重启统计
restart_count = 0          # 当前周期内重启次数
total_restarts = 0         # 总重启次数
last_restart_time = 0.0    # 上次重启时间

# 详细日志
logger.warning("⚠️  MLX service is DOWN (port 60316 not in use)")
logger.info("🔄 Attempting to restart MLX service (attempt #3)...")
logger.info("✅ MLX service restarted successfully (total restarts: 5)")
```

#### 🔧 智能计数器重置
```python
# 场景1: 服务成功重启后部分重置
if is_port_in_use(60316):
    restart_count = max(0, restart_count - 1)  # 奖励成功重启

# 场景2: 服务稳定运行后完全重置
if current_time - last_restart_time > RESTART_COOLDOWN * 2:
    restart_count = 0
    logger.info("✅ MLX service stabilized, reset restart counter")
```

### 2. 生命周期集成

**启动流程** (`lifespan` 函数):
```python
# 1. 启动 MLX 服务
builtin_mgr.ensure_mlx_service_running()

# 2. 启动监控任务
app.state.mlx_monitor_stop_event = asyncio.Event()
app.state.mlx_monitor_task = asyncio.create_task(
    mlx_service_monitor(engine, base_dir, stop_event)
)

# 3. 正常提供服务
yield
```

**停止流程** (`finally` 块):
```python
# 1. 停止监控任务
app.state.mlx_monitor_stop_event.set()
await asyncio.wait_for(app.state.mlx_monitor_task, timeout=5.0)

# 2. 停止其他后台任务
# ...

# 3. 停止 MLX 服务
kill_process_on_port(60316)
```

## 🎯 关键设计决策

### 为什么选择 asyncio.Event 而不是 threading.Event？

```python
# ✅ 正确：使用 asyncio
app.state.mlx_monitor_stop_event = asyncio.Event()
app.state.mlx_monitor_task = asyncio.create_task(mlx_service_monitor(...))

# ❌ 错误：混用线程
# 监控任务是 async 协程，必须在 asyncio 事件循环中运行
```

**原因**:
- 监控任务是 `async def`，属于协程
- FastAPI 的 `lifespan` 是异步上下文管理器
- 可以与 FastAPI 的事件循环无缝集成

### 为什么不使用单独的线程？

虽然任务处理器使用了线程（`task_processor_thread`），但监控任务使用协程更合适：

| 特性 | 线程方式 | 协程方式 |
|------|---------|---------|
| **启动** | `threading.Thread()` | `asyncio.create_task()` |
| **停止** | `join(timeout)` | `await wait_for()` |
| **资源** | 更重（系统线程） | 更轻（用户态） |
| **集成** | 需要额外处理 | 原生集成 |

### 为什么检查间隔是 10 秒？

```python
CHECK_INTERVAL = 10  # 秒
```

**权衡考虑**:
- ✅ **足够快**：崩溃后 10-20 秒内可以重启
- ✅ **足够轻**：不会对系统造成负担
- ✅ **用户体验**：对于后台批量任务，10 秒延迟可接受
- ❌ 如果是交互式会话：用户可能等待 10 秒（但会话请求有超时保护）

**可调整场景**:
```python
# 更激进（适合高可用需求）
CHECK_INTERVAL = 5

# 更保守（适合低资源环境）
CHECK_INTERVAL = 30
```

## 📊 监控流程图

```
┌─────────────────────────────────────────────────┐
│  FastAPI 启动 (lifespan)                         │
└────────────────┬────────────────────────────────┘
                 │
                 ├─► 启动 MLX 服务 (如果需要)
                 │
                 ├─► 创建监控任务 (asyncio.create_task)
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│  监控循环 (每 10 秒)                             │
│                                                  │
│  while not stop_event.is_set():                 │
│      ┌──────────────────────────────┐           │
│      │ 检查是否需要 MLX 服务          │           │
│      └───────┬──────────────────────┘           │
│              │                                   │
│              ├─ 不需要 ──► 跳过                  │
│              │                                   │
│              └─ 需要                             │
│                  │                               │
│                  ▼                               │
│      ┌──────────────────────────────┐           │
│      │ 检查端口 60316 是否在使用      │           │
│      └───────┬──────────────────────┘           │
│              │                                   │
│              ├─ 运行中 ──► ✅ 正常               │
│              │                                   │
│              └─ 未运行 ──► ⚠️  崩溃检测到        │
│                  │                               │
│                  ▼                               │
│      ┌──────────────────────────────┐           │
│      │ 检查重启频率                  │           │
│      │ (防止启动风暴)                │           │
│      └───────┬──────────────────────┘           │
│              │                                   │
│              ├─ 太频繁 ──► ⏳ 指数退避          │
│              │                                   │
│              └─ 可重启                           │
│                  │                               │
│                  ▼                               │
│      ┌──────────────────────────────┐           │
│      │ 重启 MLX 服务                 │           │
│      └───────┬──────────────────────┘           │
│              │                                   │
│              ├─ 成功 ──► ✅ 记录日志            │
│              │                                   │
│              └─ 失败 ──► ❌ 记录错误            │
│                                                  │
│      await asyncio.sleep(CHECK_INTERVAL)        │
└─────────────────────────────────────────────────┘
                 │
                 │ (收到停止信号)
                 ▼
┌─────────────────────────────────────────────────┐
│  FastAPI 关闭 (finally)                          │
│                                                  │
│  1. 设置 stop_event                              │
│  2. 等待监控任务结束 (最多 5 秒)                  │
│  3. 清理其他资源                                 │
│  4. 停止 MLX 服务                                │
└─────────────────────────────────────────────────┘
```

## 🧪 测试验证

### 测试脚本
创建了 `test_mlx_monitor.py`，包含：

1. ✅ **服务健康检查** - 验证主服务和 MLX 服务状态
2. ✅ **监控日志查看** - 查看监控任务的运行日志
3. ✅ **崩溃检测与重启** - 模拟崩溃并验证自动重启
4. ⚠️ **频繁崩溃退避** - 验证指数退避策略（需手动确认）

### 运行测试
```bash
cd api
python test_mlx_monitor.py
```

**前置条件**:
- 主 FastAPI 服务必须运行在 60315 端口
- MLX 服务配置为启用（至少一个能力使用内置模型）

### 预期结果

**正常场景**:
```
✅ 主 API 服务运行正常
✅ MLX 服务运行正常: {'status': 'healthy', ...}
📄 最新日志文件: api_20250107.log
📋 MLX 监控相关日志:
    🔍 MLX service monitor started
    ✅ MLX service is running normally
```

**崩溃重启场景**:
```
📊 当前 MLX 服务状态: 运行中
✅ 成功模拟崩溃（杀死了进程）
⏳ 等待 15 秒，让监控任务检测并重启...
✅ 监控任务成功检测到崩溃并自动重启了服务！

📋 日志:
    ⚠️  MLX service is DOWN (port 60316 not in use)
    🔄 Attempting to restart MLX service (attempt #1)...
    ✅ MLX service restarted successfully (total restarts: 1)
```

## 📝 配置参数

所有可调整的参数都在 `mlx_service_monitor` 函数中：

```python
# 监控配置
CHECK_INTERVAL = 10        # 检查间隔（秒）- 可根据需求调整
RESTART_COOLDOWN = 60      # 重启冷却时间（秒）
MAX_RESTART_ATTEMPTS = 5   # 单位时间内最大重启次数
```

**调优建议**:

| 场景 | CHECK_INTERVAL | RESTART_COOLDOWN | MAX_RESTART_ATTEMPTS |
|------|----------------|------------------|---------------------|
| **高可用生产环境** | 5-10s | 60s | 3-5 |
| **开发测试环境** | 10-30s | 30s | 10 |
| **低资源设备** | 30-60s | 120s | 3 |

## 🎯 与方案3的协同工作

### 两层防护机制

```
用户请求
    │
    ▼
┌─────────────────────────────────┐
│  方案3: 请求超时保护              │ ◄─ 第一道防线
│  (builtin_openai_compat.py)     │
│                                  │
│  - 非流式: 最大 180s             │
│  - 流式: 最大 300s               │
│  - 超时后返回错误                 │
└──────────┬──────────────────────┘
           │ (如果超时未解决问题)
           ▼
┌─────────────────────────────────┐
│  MLX C++ 层                      │
│  可能发生 GPU Timeout 崩溃        │
└──────────┬──────────────────────┘
           │ (进程崩溃)
           ▼
┌─────────────────────────────────┐
│  方案1: 进程监控与重启            │ ◄─ 第二道防线
│  (main.py)                       │
│                                  │
│  - 每 10s 检查                   │
│  - 崩溃后 10-20s 内重启           │
│  - 指数退避防启动风暴             │
└─────────────────────────────────┘
```

### 实际工作流程

**场景1: 单次超时（方案3处理）**
```
1. 用户发起请求
2. GPU 负载高，响应慢
3. 180 秒后触发超时
4. 返回错误给用户："Request timeout"
5. Python 层取消任务
6. 进程继续运行 ✅
```

**场景2: GPU 崩溃（方案1处理）**
```
1. 用户发起请求
2. GPU 超时导致 C++ 异常
3. MLX 进程崩溃 💥
4. 监控检测到端口 60316 未使用
5. 10-20 秒内自动重启进程
6. 服务恢复正常 ✅
```

**场景3: 频繁崩溃（方案1+退避）**
```
1. 批量任务导致 GPU 持续过载
2. MLX 进程频繁崩溃 💥💥💥
3. 监控检测到频繁重启
4. 触发指数退避策略
5. 等待 2-300 秒后重试
6. 给 GPU 降温时间 ⏳
```

## 🛠️ 故障排查

### 监控任务未启动

**症状**: 日志中没有 "MLX service monitor started"

**检查**:
```bash
# 查看日志
tail -f ~/Library/Application\ Support/knowledge-focus.huozhong.in/logs/api_*.log | grep -i "mlx"

# 应该看到：
# 🔍 MLX service monitor started
```

**可能原因**:
1. FastAPI 启动失败
2. lifespan 函数异常
3. asyncio 任务创建失败

### 服务崩溃但未重启

**症状**: MLX 服务停止，但没有自动重启

**检查**:
```bash
# 检查端口
lsof -i :60316

# 检查是否配置需要 MLX 服务
# 在数据库中查询 CapabilityAssignment 和 ModelProvider
```

**可能原因**:
1. `should_auto_load()` 返回 False（没有能力配置使用内置模型）
2. 监控任务已停止
3. 重启次数超限，处于长时间退避中

### 日志中频繁出现重启

**症状**: 日志中多次出现 "Attempting to restart MLX service"

**这是正常的！** 说明监控在工作。

**但如果过于频繁**（每分钟多次）:
1. 检查 GPU 负载是否过高
2. 检查是否有大量并发请求
3. 考虑调整 `max_tokens` 参数
4. 考虑暂停批量打标签任务

## 📚 相关文件

- ✅ `api/main.py` - 核心实现（监控任务 + 生命周期集成）
- ✅ `api/test_mlx_monitor.py` - 测试脚本
- ✅ `api/models_builtin.py` - MLX 服务启动逻辑
- ✅ `api/utils.py` - 端口检查工具函数
- 📘 `docs/MLX_SERVICE_TIMEOUT_PROTECTION.md` - 方案3文档

## 💡 后续优化方向

### 1. 监控指标收集 📊
```python
# 可以添加 Prometheus 指标
mlx_service_restarts_total = Counter(...)
mlx_service_uptime_seconds = Gauge(...)
mlx_service_last_restart_timestamp = Gauge(...)
```

### 2. 健康检查增强 🏥
```python
# 不仅检查端口，还检查 /health 端点
try:
    response = await client.get("http://127.0.0.1:60316/health")
    if response.status_code != 200:
        # 服务僵死但端口仍在使用
        logger.warning("Service port in use but health check failed")
except:
    # 服务崩溃
```

### 3. 通知机制 📧
```python
# 崩溃次数过多时发送通知
if total_restarts > ALERT_THRESHOLD:
    await send_alert(f"MLX service restarted {total_restarts} times")
```

### 4. 自适应检查间隔 ⚙️
```python
# 根据服务稳定性动态调整检查间隔
if service_stable:
    CHECK_INTERVAL = 30  # 降低检查频率
else:
    CHECK_INTERVAL = 5   # 提高检查频率
```

## ✅ 实施完成总结

### 实施评估

| 维度 | 评分 | 说明 |
|------|------|------|
| **实施复杂度** | ⭐⭐⭐ (中等) | ~130 行代码，需要理解 asyncio |
| **效果** | ⭐⭐⭐⭐⭐ (优秀) | 能可靠检测并重启崩溃服务 |
| **稳定性** | ⭐⭐⭐⭐⭐ (优秀) | 指数退避防止启动风暴 |
| **可维护性** | ⭐⭐⭐⭐ (良好) | 参数可配置，日志详细 |

### 完成状态

- ✅ **方案3**: 请求超时保护（已完成）
- ✅ **方案1**: 进程监控与自动重启（已完成）
- 🟡 **上层优化**: 业务逻辑优化（待讨论）

### 核心价值

1. **可靠性提升**: 从"崩溃后需要手动重启"到"10-20秒自动恢复"
2. **用户体验**: 后台批量任务不受影响，自动重试
3. **运维简化**: 无需手动介入，服务自愈
4. **问题诊断**: 详细日志记录每次崩溃和重启

### 下一步行动

1. ✅ 完成方案1实施（已完成）
2. 🧪 在生产环境中验证监控效果
3. 📊 观察重启频率和退避行为
4. 🟡 讨论上层业务逻辑优化（可选）
   - 暂停打标签按钮
   - 智能调度策略
   - GPU 负载感知

---

**方案1实施完成！现在系统具备完整的两层防护机制。** 🎉
