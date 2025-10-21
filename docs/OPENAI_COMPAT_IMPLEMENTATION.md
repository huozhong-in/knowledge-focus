# OpenAI 兼容层实现文档

## 概述

本次重构实现了两个关键改进：
1. **OpenAI API 兼容**：提供标准的 `/v1/chat/completions` 接口
2. **统一进程管理**：将 MLX-VLM 服务器合并到主 API 进程中

## 架构变更

### 之前的架构 ❌

```
主 API (60315端口)
    └── subprocess 启动 MLX-VLM Server (60316端口)
            └── FastAPI 独立进程
                └── /responses 接口（非标准）
```

**问题**：
- 需要管理两个进程的生命周期
- 应用退出时清理困难
- 使用非标准 `/responses` 接口
- 测试代码无法代表真实使用场景

### 现在的架构 ✅

```
主 API (60315端口)
    └── /v1/chat/completions 接口（标准 OpenAI 格式）
            └── builtin_openai_compat.py（兼容层）
                    └── MLX-VLM 核心库（直接导入）
                            ├── generate()
                            ├── stream_generate()
                            └── load()
```

**优势**：
- ✅ 单进程架构，统一生命周期管理
- ✅ 完全兼容 OpenAI API（可直接使用 OpenAI SDK）
- ✅ 共享模型缓存，节省内存
- ✅ 应用退出时自动清理资源

## 核心文件说明

### 1. `builtin_openai_compat.py`

OpenAI 兼容层核心实现。

**主要组件**：

#### 数据模型
```python
class OpenAIChatCompletionRequest(BaseModel):
    """标准 OpenAI 请求格式"""
    model: str
    messages: List[ChatMessage]
    temperature: float = 0.7
    max_tokens: Optional[int] = 512
    top_p: float = 1.0
    stream: bool = False

class OpenAIChatCompletionResponse(BaseModel):
    """标准 OpenAI 响应格式"""
    id: str
    object: Literal["chat.completion"]
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage
```

#### 模型管理器
```python
class MLXVLMModelManager:
    """单例模式的模型管理器"""
    
    def get_model(self, model_path: str) -> tuple:
        """
        加载或获取缓存的模型
        - 自动切换模型
        - 管理内存缓存
        """
```

#### 核心转换逻辑
```python
def _extract_images_from_messages(messages):
    """从 OpenAI 格式提取图片 URL"""
    
def _prepare_mlx_prompt(messages, processor, config, num_images):
    """转换为 MLX-VLM 格式的 prompt"""
    
def _create_chat_completion_response(...):
    """构造 OpenAI 格式的响应"""
```

#### 生成逻辑
```python
async def generate_chat_completion(request, model_path):
    """
    统一的生成入口点
    - 支持流式和非流式
    - 自动资源清理
    - 完整错误处理
    """
```

### 2. `models_api.py` 新增端点

```python
@router.post("/v1/chat/completions", tags=["models", "openai-compat"])
async def openai_chat_completions(request: dict):
    """
    OpenAI 兼容接口
    
    功能:
    1. 解析 OpenAI 格式请求
    2. 查找模型路径（支持 model_id 和 hf_model_id）
    3. 委托给 generate_chat_completion()
    4. 返回 OpenAI 格式响应
    """
```

## 使用方式

### 方式1：使用 OpenAI SDK（推荐）

```python
from openai import OpenAI

# 创建客户端（指向本地 API）
client = OpenAI(
    base_url="http://127.0.0.1:60315/v1",
    api_key="dummy"  # 内置模型不需要真实 key
)

# 纯文本对话
response = client.chat.completions.create(
    model="qwen3-vl-4b",  # 使用 model_id
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"}
    ],
    max_tokens=50,
    temperature=0.7
)

print(response.choices[0].message.content)

# 视觉问答（多模态）
response = client.chat.completions.create(
    model="qwen3-vl-4b",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image."},
                {
                    "type": "image_url",
                    "image_url": {"url": "/path/to/image.jpg"}
                }
            ]
        }
    ]
)

# 流式响应
stream = client.chat.completions.create(
    model="qwen3-vl-4b",
    messages=[{"role": "user", "content": "Tell me a story"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### 方式2：直接 HTTP 请求

```python
import httpx

response = httpx.post(
    "http://127.0.0.1:60315/v1/chat/completions",
    json={
        "model": "qwen3-vl-4b",
        "messages": [
            {"role": "user", "content": "Hello!"}
        ],
        "max_tokens": 50,
        "temperature": 0.7
    }
)

result = response.json()
print(result["choices"][0]["message"]["content"])
```

## 模型标识符支持

接口支持两种模型标识符：

### 1. model_id（简短形式）
```python
model="qwen3-vl-4b"  # 直接使用 BUILTIN_MODELS 的 key
```

### 2. hf_model_id（完整形式）
```python
model="mlx-community/Qwen2.5-VL-3B-Instruct-4bit"  # HuggingFace 完整路径
```

API 会自动识别并转换为本地模型路径。

## 测试

运行测试脚本：

```bash
cd api
python test_openai_compat.py
```

测试覆盖：
1. ✅ 纯文本对话
2. ✅ 视觉问答（多模态）
3. ✅ 流式响应

## 错误处理

### 模型未下载
```json
{
    "error": {
        "message": "Model qwen3-vl-4b not downloaded. Please download it first.",
        "type": "model_not_found",
        "code": "model_not_downloaded"
    }
}
```

### 模型不存在
```json
{
    "error": {
        "message": "Model xxx not found in builtin models",
        "type": "invalid_request_error",
        "code": "model_not_found"
    }
}
```

### 生成失败
```json
{
    "error": {
        "message": "Error details...",
        "type": "internal_server_error",
        "code": "generation_failed"
    }
}
```

## 资源管理

### 模型缓存
- 使用单例 `MLXVLMModelManager` 管理模型缓存
- 切换模型时自动清理旧模型
- 调用 `gc.collect()` 和 `mx.clear_cache()` 释放内存

### 进程生命周期
- 不再需要独立的 MLX-VLM 服务器进程
- 应用退出时自动清理所有资源
- 无需手动管理 subprocess

## 与旧实现的对比

| 特性 | 旧实现 (subprocess) | 新实现 (导入包装) |
|------|---------------------|-------------------|
| 进程数量 | 2 个（主 API + MLX Server） | 1 个（主 API） |
| 端口 | 60315 + 60316 | 仅 60315 |
| API 格式 | `/responses`（非标准） | `/v1/chat/completions`（标准） |
| 兼容性 | 需自定义客户端 | 可用 OpenAI SDK |
| 资源清理 | 需手动管理 subprocess | 自动清理 |
| 内存共享 | 独立进程，无法共享 | 单进程，共享缓存 |
| 测试难度 | 需启动两个服务 | 统一测试环境 |

## 下一步计划

1. ✅ **已完成**：OpenAI 兼容层实现
2. ✅ **已完成**：统一进程架构
3. ⏳ **待完成**：更新 `models_builtin.py` 移除 subprocess 相关代码
4. ⏳ **待完成**：更新前端调用逻辑使用新接口
5. ⏳ **待完成**：完整的端到端测试

## 注意事项

1. **模型必须先下载**：使用前需通过 `/models/builtin/{model_id}/download` 下载模型
2. **路径格式**：图片路径支持本地绝对路径（多模态场景）
3. **流式响应**：使用 SSE (Server-Sent Events) 格式，需正确处理
4. **错误格式**：遵循 OpenAI 错误响应格式，便于客户端统一处理
