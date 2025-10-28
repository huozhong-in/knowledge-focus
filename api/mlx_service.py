"""
独立的 MLX-VLM 服务

专门提供 OpenAI 兼容的 /v1/chat/completions 接口
使用 Tauri sidecar 方式启动，与主 FastAPI 服务隔离

优势：
- 完全独立的 Metal 上下文，避免冲突
- 崩溃隔离，不影响主服务
- 更简单的资源管理
"""
import logging
import sys
import argparse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
# 导入 OpenAI 兼容层和内置模型配置
from builtin_openai_compat import (
    get_vlm_manager,
    OpenAIChatCompletionRequest,
    RequestPriority
)
from models_builtin import BUILTIN_MODELS

# 配置日志（简单配置，输出到 stdout）
# 注意：实际日志文件由父进程（models_builtin.py）通过 stdout 重定向控制
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # 只输出到 stdout，父进程会捕获
    ]
)
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title="MLX-VLM Service",
    description="OpenAI-compatible chat completions endpoint powered by MLX-VLM",
    version="1.0.0"
)

# 配置 CORS（允许主服务调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/v1/chat/completions")
async def chat_completions(request: OpenAIChatCompletionRequest):
    """
    OpenAI 兼容的聊天补全接口
    
    支持：
    - 文本对话
    - 多模态输入（图片+文本）
    - 流式和非流式响应
    - 优先级队列（会话 > 批量任务）
    
    支持两种模型标识符：
    1. model_id (如 "qwen3-vl-4b") - 我们自定义的 alias
    2. hf_model_id (如 "mlx-community/Qwen3-VL-4B-Instruct-3bit") - HuggingFace 完整模型 ID
    """
    logger.info(f"Received chat completion request: model={request.model}, stream={request.stream}")
    
    # 获取 VLM 管理器
    manager = get_vlm_manager()
    
    # 解析模型路径
    model_id = request.model
    model_path = None
    
    # 支持两种模型标识符:
    # 1. model_id (如 "qwen3-vl-4b")
    # 2. hf_model_id (如 "mlx-community/Qwen3-VL-4B-Instruct-3bit")
    if model_id in BUILTIN_MODELS:
        # 直接使用 model_id（alias）
        # 注意：这里我们需要获取实际的模型路径
        # 但 mlx_service.py 是独立进程，没有 ModelsBuiltin 实例
        # 所以我们传递 HuggingFace model_id 给 MLX，让它自动查找
        model_path = BUILTIN_MODELS[model_id]["hf_model_id"]
        logger.info(f"Using model alias '{model_id}' -> HF model: {model_path}")
    else:
        # 尝试通过 hf_model_id 查找
        found = False
        for mid, config in BUILTIN_MODELS.items():
            if config["hf_model_id"] == model_id:
                model_path = config["hf_model_id"]
                logger.info(f"Found model by HF ID '{model_id}' -> alias: {mid}")
                found = True
                break
        
        if not found:
            # 未找到，尝试直接使用（可能是完整路径）
            model_path = model_id
            logger.warning(f"Model '{model_id}' not found in BUILTIN_MODELS, using as-is")
    
    # 确定优先级
    # 默认为 LOW 优先级，会话界面可以设置为 HIGH
    # TODO: 可以通过请求头或参数传递优先级
    priority = RequestPriority.LOW
    
    # 将请求加入队列
    logger.info(f"Enqueueing request with priority: {priority.name}, model_path: {model_path}")
    result = await manager.enqueue_request(request, model_path, priority)
    
    logger.info("Request completed successfully")
    return result

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "service": "mlx-vlm",
        "version": "1.0.0"
    }

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "MLX-VLM Service",
        "endpoints": {
            "chat_completions": "/v1/chat/completions",
            "health": "/health"
        }
    }

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="MLX-VLM Service")
    parser.add_argument("--port", type=int, default=60316, help="服务监听端口")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="服务监听地址")
    args = parser.parse_args()
    
    print(f"🚀 Starting MLX-VLM Service on {args.host}:{args.port}")
    print(f"📖 API Documentation: http://{args.host}:{args.port}/docs")
    
    # 启动服务
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=True
    )

if __name__ == "__main__":
    main()
