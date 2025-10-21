# 重启 API 服务器说明

## 问题

刚才更新了 `models_api.py`，使用 `@singleton` 装饰器替代了手动管理的全局变量。但主 API 服务器还在运行旧代码，需要重启。

## 改动内容

### 之前（手动单例）
```python
# 单例模式：全局共享的 ModelsBuiltin 实例
_models_builtin_instance = None

def get_models_builtin():
    global _models_builtin_instance
    if _models_builtin_instance is None:
        from models_builtin import ModelsBuiltin
        engine = get_engine()
        _models_builtin_instance = ModelsBuiltin(engine, base_dir)
    return _models_builtin_instance
```

### 现在（使用 @singleton 装饰器）
```python
from config import singleton

@singleton
class ModelsBuiltinSingleton:
    """ModelsBuiltin 单例包装类"""
    def __init__(self):
        from models_builtin import ModelsBuiltin
        engine = get_engine()
        self.instance = ModelsBuiltin(engine, base_dir)
        logger.info("Created ModelsBuiltin singleton instance")

def get_models_builtin():
    """
    获取 ModelsBuiltin 单例实例
    
    使用 @singleton 装饰器确保服务器进程状态在所有 API 调用间共享
    """
    return ModelsBuiltinSingleton().instance
```

## 为什么这样改？

1. **一致性**: 与项目中其他管理器（如 `MultivectorMgr`）保持一致的单例模式
2. **可读性**: `@singleton` 装饰器更加清晰和符合 Python 习惯
3. **避免全局变量**: 不需要使用 `global` 关键字
4. **更安全**: 装饰器实现更加健壮，避免潜在的竞态条件

## 重启步骤

1. **停止当前的主 API 服务器**:
   ```bash
   # 在运行 main.py 的终端按 Ctrl+C
   # 或者
   pkill -f "python.*main.py"
   ```

2. **停止 MLX-VLM 服务器**（如果在运行）:
   ```bash
   pkill -f "uvicorn.*mlx_vlm"
   ```

3. **重新启动主 API 服务器**:
   ```bash
   cd /Users/dio/workspace/knowledge-focus/api
   uv run python main.py
   ```

4. **重新运行测试**:
   ```bash
   uv run test_builtin_api_phase2.py
   ```

## 预期结果

重启后，所有 API 端点应该正常工作，并且服务器状态会在所有 API 调用间正确共享。

测试输出应该显示：
- ✅ 成功获取内置模型列表
- ✅ 服务器状态查询成功
- ✅ 服务器启动成功
- ✅ 服务器状态显示运行中（PID、加载的模型等）
- ✅ 服务器停止成功
