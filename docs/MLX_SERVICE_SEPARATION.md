# MLX 服务分离方案

## 背景

当前架构中，MLX-VLM 服务和主 FastAPI 服务运行在同一进程（60315端口），导致：
1. 共享 Metal 上下文，MLX-VLM 清理不彻底时会相互影响
2. Metal Command Buffer 冲突导致崩溃
3. 调试和监控困难

## 解决方案

将 MLX-VLM 服务分离为独立进程，通过 Tauri sidecar 启动。

### 架构对比

#### 当前架构
```
FastAPI 进程 (60315)
├─ /v1/chat/completions 端点 → MLX-VLM
├─ multivector 任务 → HTTP 调用自己 → MLX-VLM
└─ 打标签任务 → HTTP 调用自己 → MLX-VLM
    ↓
    所有 MLX-VLM 操作共享同一个 Metal 上下文 ❌
```

#### 新架构
```
进程1: FastAPI (60315)
├─ multivector 任务 → HTTP → 127.0.0.1:60316
└─ 打标签任务 → HTTP → 127.0.0.1:60316

进程2: MLX 服务 (60316) ← Tauri sidecar
└─ /v1/chat/completions 端点
    └─ 优先级队列 → MLX-VLM
    └─ 独占 Metal 上下文 ✅
```

## 实施步骤

### 1. 创建独立的 MLX 服务

文件：`api/mlx_service.py`（已创建）

特点：
- 只包含 `/v1/chat/completions` 端点
- 使用优先级队列管理请求
- 独立的 Metal 上下文
- 支持健康检查

运行：
```bash
cd api
uv run python mlx_service.py --port 60316
```

### 2. 修改 Tauri 配置

#### 2.1 添加 sidecar 配置

编辑 `tauri-app/src-tauri/tauri.conf.json`：

```json
{
  "bundle": {
    "externalBin": [
      "bin/uv",
      "bin/uvx",
      "bin/bun",
      "bin/mlx-service"  // 添加
    ]
  }
}
```

#### 2.2 创建 sidecar 启动脚本

文件：`tauri-app/src-tauri/bin/mlx-service`（需要创建）

macOS/Linux:
```bash
#!/bin/bash
# 获取当前脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
RESOURCES_DIR="$SCRIPT_DIR/../Resources"

# 启动 MLX 服务
cd "$RESOURCES_DIR/api"
exec "$SCRIPT_DIR/uv" run python mlx_service.py --port 60316
```

Windows:
```batch
@echo off
set SCRIPT_DIR=%~dp0
set RESOURCES_DIR=%SCRIPT_DIR%..\Resources

cd /d %RESOURCES_DIR%\api
%SCRIPT_DIR%\uv.exe run python mlx_service.py --port 60316
```

#### 2.3 确保打包 `mlx_service.py`

编辑 `tauri-app/src-tauri/tauri.conf.json`：

```json
{
  "bundle": {
    "resources": {
      "Resources/api/mlx_service.py": "../../api/mlx_service.py",
      // ... 其他文件
    }
  }
}
```

### 3. 修改 Rust 代码启动 sidecar

编辑 `tauri-app/src-tauri/src/main.rs`：

```rust
use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            // 启动主 API 服务 (60315)
            let api_sidecar = tauri::api::process::Command::new_sidecar("main-api")?
                .spawn()?;
            
            // 启动 MLX 服务 (60316)
            let mlx_sidecar = tauri::api::process::Command::new_sidecar("mlx-service")?
                .spawn()?;
            
            // 保存引用以便后续管理
            app.manage(api_sidecar);
            app.manage(mlx_sidecar);
            
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### 4. 修改模型配置管理

#### 4.1 更新默认配置

编辑 `api/db_mgr.py`，修改内置 MLX 的 base_url：

```python
# 原来
"base_url": "http://127.0.0.1:60315/v1",

# 改为
"base_url": "http://127.0.0.1:60316/v1",
```

#### 4.2 验证配置

启动应用后，检查数据库中的模型配置：
```sql
SELECT * FROM model_configuration WHERE provider = 'builtin';
```

确保 base_url 指向 60316。

### 5. 移除不再需要的 Metal 锁

#### 5.1 移除 multivector_mgr.py 中的 Metal 锁

```python
# 删除全局锁
# _metal_gpu_lock = ProcessLock()

# 删除锁函数
# def acquire_metal_lock(operation: str): ...
# def release_metal_lock(operation: str): ...
```

#### 5.2 简化资源清理

`_release_docling_resources_without_lock` 方法可以简化：

```python
def _release_docling_resources(self):
    """释放 Docling 和 PyTorch 资源"""
    logger.info("[CLEANUP] Starting resource cleanup...")
    
    # 销毁对象
    self.converter = None
    self.chunker = None
    
    # 垃圾回收
    import gc
    gc.collect()
    gc.collect()
    
    logger.info("[CLEANUP] Resource cleanup completed")
```

#### 5.3 移除 process_document 中的锁

```python
# 原来
acquire_metal_lock("Multivector cleanup + vectorization")
try:
    self._release_docling_resources_without_lock()
    self._vectorize_and_store_without_lock(parent_chunks, child_chunks)
finally:
    release_metal_lock("Multivector cleanup + vectorization")

# 改为
self._release_docling_resources()
self._vectorize_and_store(parent_chunks, child_chunks)
```

## 优势总结

### 1. 完全隔离的 Metal 上下文 ✅
- 不同进程有独立的 Metal 资源
- MLX-VLM 残留状态不会跨进程影响

### 2. 崩溃隔离 ✅
- MLX 服务崩溃不影响主服务
- 可以独立重启 MLX 服务

### 3. 更简单的锁管理 ✅
- 不再需要 Metal 锁
- 进程隔离天然保证互斥

### 4. 更清晰的架构 ✅
- 职责分离：60315 = 业务逻辑，60316 = AI 推理
- 更容易监控和调试

### 5. 更灵活的部署 ✅
- 可以独立重启服务
- 可以根据负载调整配置

## 测试方案

### 1. 本地测试

#### 启动 MLX 服务
```bash
cd api
uv run python mlx_service.py --port 60316
```

#### 测试健康检查
```bash
curl http://127.0.0.1:60316/health
```

#### 测试 chat completions
```bash
curl -X POST http://127.0.0.1:60316/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mlx-community/Qwen3-VL-4B-Instruct-3bit",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

### 2. 集成测试

#### 启动主服务
```bash
cd api
uv run python main.py --port 60315
```

#### 测试 multivector（会自动调用 60316）
```bash
curl -X POST http://127.0.0.1:60315/pin-file \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/test.pdf"}'
```

### 3. 并发测试

同时运行：
- multivector 任务（249 chunks 生成摘要）
- 打标签任务（50 个文件）

预期：
- ✅ 无 Metal Command Buffer 错误
- ✅ 无进程崩溃
- ✅ 两个任务都成功完成

## 回滚方案

如果分离服务导致问题：

1. 恢复 `db_mgr.py` 中的 base_url 为 60315
2. 停止 MLX sidecar 服务
3. 恢复 Metal 锁相关代码

## 后续优化

### 1. 健康检查和自动重启
- 监控 60316 端口状态
- MLX 服务崩溃时自动重启

### 2. 负载均衡
- 如果请求量大，可以启动多个 MLX 服务实例
- 使用负载均衡分发请求

### 3. 资源监控
- 监控 MLX 服务的内存和 GPU 使用
- 空闲时自动卸载模型释放资源

## 参考资料

- [Tauri Sidecar Documentation](https://tauri.app/v1/guides/building/sidecar)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [MLX-VLM GitHub](https://github.com/Blaizzy/mlx-vlm)
