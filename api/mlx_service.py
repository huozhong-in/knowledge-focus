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
    
    重要：为了支持离线使用，会尝试解析为本地路径
    """
    logger.info(f"Received chat completion request: model={request.model}, stream={request.stream}")
    
    # 获取 VLM 管理器
    manager = get_vlm_manager()
    
    # 解析模型路径（优先使用本地路径以支持离线）
    model_id = request.model
    model_path = None
    
    # 尝试从 ModelsBuiltin 获取本地路径
    try:
        from models_builtin import ModelsBuiltin, BUILTIN_MODELS
        from sqlmodel import create_engine
        import os
        
        # 获取 base_dir
        base_dir = app.state.base_dir
        
        # 创建临时 engine（只用于查询）
        db_path = os.path.join(base_dir, 'knowledge-focus.db')
        engine = create_engine(f'sqlite:///{db_path}')
        
        # 获取 ModelsBuiltin 实例
        models_builtin = ModelsBuiltin(engine=engine, base_dir=base_dir)
        
        # 支持两种模型标识符:
        # 1. model_id (如 "qwen3-vl-4b")
        if model_id in BUILTIN_MODELS:
            # 尝试获取本地路径
            local_path = models_builtin.get_model_path(model_id)
            if local_path:
                model_path = local_path
                logger.info(f"✅ Using local model path for '{model_id}': {model_path}")
            else:
                # 本地未下载，使用 HuggingFace ID（会尝试联网下载）
                model_path = BUILTIN_MODELS[model_id]["hf_model_id"]
                logger.warning(f"⚠️  Model '{model_id}' not downloaded locally, using HF ID: {model_path}")
        
        # 2. hf_model_id (如 "mlx-community/Qwen3-VL-4B-Instruct-3bit")
        else:
            # 尝试通过 hf_model_id 查找对应的 model_id
            found = False
            for mid, config in BUILTIN_MODELS.items():
                if config["hf_model_id"] == model_id:
                    # 找到对应的 model_id，尝试获取本地路径
                    local_path = models_builtin.get_model_path(mid)
                    if local_path:
                        model_path = local_path
                        logger.info(f"✅ Found local model by HF ID '{model_id}' -> alias: {mid}, path: {model_path}")
                    else:
                        model_path = model_id  # 使用 HF ID
                        logger.warning(f"⚠️  Model '{mid}' not downloaded locally, using HF ID: {model_path}")
                    found = True
                    break
            
            if not found:
                # 未找到，直接使用（可能是完整路径或 HF ID）
                model_path = model_id
                logger.warning(f"Model '{model_id}' not found in BUILTIN_MODELS, using as-is")
    
    except Exception as e:
        # 如果解析失败，回退到使用原始 model_id
        logger.error(f"Failed to resolve model path: {e}, using model_id as-is")
        model_path = model_id
    
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
    parser.add_argument("--base-dir", type=str, help="用户应用临时目录")
    args = parser.parse_args()
    app.state.base_dir = args.base_dir
    
    print(f"🚀 Starting MLX-VLM Service on {args.host}:{args.port}")
    print(f"📖 API Documentation: http://{args.host}:{args.port}/docs")
    print(f"🗄️  Base Directory: {args.base_dir}")
    
    # 启动服务
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=True
    )

if __name__ == "__main__":
    from utils import kill_process_on_port
    kill_process_on_port(60316)
    main()
