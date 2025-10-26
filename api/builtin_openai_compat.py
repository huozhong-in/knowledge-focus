"""
OpenAI 兼容层 for MLX-VLM 内置模型

提供标准的 /v1/chat/completions 接口，内部调用 mlx_vlm 库
"""
import logging
import asyncio
import gc
import time
import json
import uuid
from config import singleton
from utils import preprocess_image
from enum import IntEnum
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse
import mlx.core as mx
from mlx_vlm.generate import stream_generate, generate
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.utils import load

# 🔒 导入 Metal GPU 互斥锁
# from multivector_mgr import acquire_metal_lock_async, release_metal_lock_async

logger = logging.getLogger(__name__)

# ==================== 优先级定义 ====================

class RequestPriority(IntEnum):
    """请求优先级"""
    HIGH = 1    # 会话界面请求（用户主动发起）
    LOW = 10    # 批量任务请求（后台自动）

# ==================== OpenAI API 模型定义 ====================

class ChatMessage(BaseModel):
    """聊天消息"""
    role: Literal["system", "user", "assistant"] = Field(...)
    content: str | List[Dict[str, Any]] = Field(...)  # 支持文本或多模态内容

class OpenAIChatCompletionRequest(BaseModel):
    """OpenAI /v1/chat/completions 请求格式"""
    model: str = Field(..., description="模型标识符（HuggingFace 路径）")
    messages: List[ChatMessage] = Field(..., description="聊天消息列表")
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=512, ge=1)
    top_p: float = Field(default=1.0, ge=0, le=1)
    stream: bool = Field(default=False, description="是否流式返回")
    response_format: Optional[Dict[str, Any]] = Field(default=None, description="响应格式配置（接受任何格式，主要用于兼容性）")
    # 扩展字段（非 OpenAI 标准）
    images: Optional[List[str]] = Field(default=None, description="图片路径列表（用于向后兼容）")

class ChatCompletionChoice(BaseModel):
    """单个完成选项"""
    index: int
    message: ChatMessage
    finish_reason: Literal["stop", "length"] = "stop"

class ChatCompletionUsage(BaseModel):
    """Token 使用统计"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class OpenAIChatCompletionResponse(BaseModel):
    """OpenAI /v1/chat/completions 响应格式"""
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage

class ChatCompletionChunk(BaseModel):
    """流式响应的单个块"""
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: List[Dict[str, Any]]  # delta 格式

# ==================== 模型管理（带优先级队列） ====================

@singleton
class MLXVLMModelManager:
    """
    MLX-VLM 模型管理器
    
    特性：
    - 按需加载：首次请求时自动加载模型
    - 并发保护：使用 asyncio.Lock 防止并发加载
    - 优先级队列：高优先级请求（会话）优先处理
    - 自动队列处理：后台任务循环处理请求
    """
    
    def __init__(self):
        self._model_cache: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._request_queue = asyncio.PriorityQueue()
        self._processing_task: Optional[asyncio.Task] = None
        self._is_processing = False
        self._request_counter = 0  # 用于打破优先级平局
    
    async def ensure_loaded(self, model_path: str):
        """
        确保模型已加载（按需加载 + 并发保护）
        
        Args:
            model_path: 模型路径
        """
        async with self._lock:
            # 检查是否已加载
            if self._model_cache.get("model_path") == model_path:
                logger.debug(f"Model already loaded: {model_path}")
                return
            
            # 清理旧模型
            if self._model_cache:
                # logger.info("Clearing old model from cache...")
                await self._unload_model_internal()
            
            # 加载新模型
            # logger.info(f"Loading model: {model_path}")
            
            # 在线程池中执行同步的 load 操作
            loop = asyncio.get_event_loop()
            model, processor = await loop.run_in_executor(
                None,
                lambda: load(model_path, trust_remote_code=True)
            )
            config = model.config
            
            self._model_cache = {
                "model_path": model_path,
                "model": model,
                "processor": processor,
                "config": config
            }
            
            # logger.info(f"Model loaded successfully: {model_path}")
            
            # 启动队列处理器（如果还没启动）
            if not self._is_processing:
                self._processing_task = asyncio.create_task(self._process_queue())
    
    async def enqueue_request(
        self,
        request: "OpenAIChatCompletionRequest",
        model_path: str,
        priority: RequestPriority = RequestPriority.LOW
    ):
        """
        将请求加入优先级队列
        
        Args:
            request: OpenAI 格式的请求
            model_path: 模型路径
            priority: 请求优先级
        
        Returns:
            响应结果（阻塞等待）
        """
        # # 验证 response_format 参数（宽容处理，仅记录）
        # if request.response_format:
        #     response_type = request.response_format.get("type", "text")
            # logger.info(f"Response format requested: {response_type}")
            # 注意：本地模型无法强制执行 JSON schema，依赖系统提示词指导
        
        # 确保队列处理器已启动
        if not self._is_processing:
            # logger.info("Starting queue processor (first request)")
            self._processing_task = asyncio.create_task(self._process_queue())
        
        future = asyncio.Future()
        # 使用计数器作为第二个排序键，避免比较 Pydantic 对象
        # 格式: (priority, counter, request, model_path, future)
        self._request_counter += 1
        await self._request_queue.put((priority, self._request_counter, request, model_path, future))
        logger.debug(f"Request enqueued with priority {priority.name}, queue size: {self._request_queue.qsize()}")
        
        # 等待结果
        return await future
    
    async def _process_queue(self):
        """
        队列处理器（后台任务）
        
        循环处理队列中的请求，按优先级排序。
        空闲 60 秒后自动退出。
        """
        self._is_processing = True
        # logger.info("Queue processor started")
        
        try:
            while True:
                try:
                    # 带超时的队列获取（避免永久阻塞）
                    priority, counter, request, model_path, future = await asyncio.wait_for(
                        self._request_queue.get(),
                        timeout=60.0
                    )
                    
                    # logger.info(f"Processing request #{counter} with priority {priority.name} (queue size: {self._request_queue.qsize()})")
                    
                    try:
                        # 确保模型已加载
                        await self.ensure_loaded(model_path)
                        
                        # 执行推理
                        result = await self._generate_completion_internal(request, model_path)
                        future.set_result(result)
                        
                    except Exception as e:
                        logger.error(f"Request processing failed: {e}", exc_info=True)
                        future.set_exception(e)
                    
                except asyncio.TimeoutError:
                    # 队列空闲超时，退出处理器
                    # logger.info("Queue idle for 60s, stopping processor")
                    break
                    
        finally:
            self._is_processing = False
            # logger.info("Queue processor stopped")
    
    async def _generate_completion_internal(
        self,
        request: "OpenAIChatCompletionRequest",
        model_path: str
    ):
        """
        内部推理方法（不经过队列）
        
        这个方法会被队列处理器调用，执行实际的模型推理。
        """
        # 获取已加载的模型
        model = self._model_cache["model"]
        processor = self._model_cache["processor"]
        config = self._model_cache["config"]
        
        # # 🔍 调试：查看收到的原始 messages 格式
        # logger.info(f"📨 收到 {len(request.messages)} 条消息")
        # for i, msg in enumerate(request.messages):
        #     logger.info(f"  消息[{i}] role={msg.role}, content类型={type(msg.content).__name__}")
        #     if isinstance(msg.content, list):
        #         logger.info(f"    content长度={len(msg.content)}")
        #         # 打印每个元素的类型和内容摘要
        #         for j, item in enumerate(msg.content):
        #             if isinstance(item, dict):
        #                 item_type = item.get('type', 'unknown')
        #                 if item_type == 'text':
        #                     text_preview = item.get('text', '')[:50]
        #                     logger.info(f"      [{j}] type=text, preview={text_preview}")
        #                 elif item_type == 'image_url':
        #                     url_obj = item.get('image_url', {})
        #                     if isinstance(url_obj, dict):
        #                         url = url_obj.get('url', '')
        #                         # 只显示前50字符，避免打印整个base64
        #                         url_preview = url[:50] + ('...' if len(url) > 50 else '')
        #                         logger.info(f"      [{j}] type=image_url, url={url_preview}")
        #                     else:
        #                         logger.info(f"      [{j}] type=image_url, url={url_obj}")
        #                 else:
        #                     logger.info(f"      [{j}] type={item_type}, keys={list(item.keys())}")
        #             else:
        #                 logger.info(f"      [{j}] 非dict类型: {type(item).__name__}")
            # elif isinstance(msg.content, str):
                # 对于结构化JSON数据（如标签），显示完整内容；其他情况限制长度
                # if msg.content.strip().startswith('{') or msg.content.strip().startswith('['):
                    # JSON格式，显示完整内容（最多1000字符，标签数据通常很小）
                    # content_display = msg.content if len(msg.content) <= 1000 else msg.content[:1000] + '...'
                    # logger.info(f"    content(JSON完整): {content_display}")
                # else:
                    # 非JSON，只显示前50字符
                    # logger.info(f"    content前50字符: {msg.content[:50]}")
        
        # 提取图片和文本（返回字典列表，用于 apply_chat_template）
        message_dicts, image_urls = _extract_images_from_messages(request.messages)
        
        # logger.info(f"Extracted {len(message_dicts)} messages and {len(image_urls)} images")
        # logger.info("📝 Message dicts for apply_chat_template:")
        # for i, msg_dict in enumerate(message_dicts):
            # 对于JSON格式显示完整内容
            # content = msg_dict['content']
            # if content.strip().startswith('{') or content.strip().startswith('['):
                # content_display = content if len(content) <= 1000 else content[:1000] + '...'
                # logger.info(f"  [{i}] role={msg_dict['role']}, content={content_display}")
            # else:
            #     content_preview = content[:50] if len(content) > 50 else content
                # logger.info(f"  [{i}] role={msg_dict['role']}, content={content_preview}...")
        
        # 应用聊天模板（直接使用字典列表）
        formatted_prompt = apply_chat_template(
            processor,
            config,
            message_dicts,
            num_images=len(image_urls),
            num_audios=0
        )
        
        # logger.info(f"🔤 Formatted prompt preview (first 200 chars): {formatted_prompt[:200]}")
        # logger.info(f"🔤 Formatted prompt contains '<|vision_start|>': {'<|vision_start|>' in formatted_prompt}")
        # logger.info(f"🔤 Formatted prompt contains '<|image_pad|>': {'<|image_pad|>' in formatted_prompt}")
        
        # 执行推理
        if request.stream:
            # 流式响应
            return await self._generate_streaming_response(
                request, model, processor, formatted_prompt, image_urls
            )
        else:
            # 非流式响应
            return await self._generate_non_streaming_response(
                request, model, processor, formatted_prompt, image_urls
            )
    
    async def _generate_streaming_response(
        self,
        request: "OpenAIChatCompletionRequest",
        model, processor, prompt, images
    ):
        """生成流式响应"""
        
        response_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        created_at = int(time.time())
        
        async def stream_generator():
            # 🔒 获取 Metal GPU 锁
            # await acquire_metal_lock_async("MLX-VLM streaming")
            try:
                # logger.info("Starting streaming generation")
                token_iterator = stream_generate(
                    model=model,
                    processor=processor,
                    prompt=prompt,
                    image=images if images else None,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    top_p=request.top_p
                )
                
                chunk_count = 0
                for chunk in token_iterator:
                    chunk_count += 1
                    if chunk is None or not hasattr(chunk, "text"):
                        continue
                    
                    if chunk.text:
                        chunk_data = ChatCompletionChunk(
                            id=response_id,
                            created=created_at,
                            model=request.model,
                            choices=[{
                                "index": 0,
                                "delta": {"content": chunk.text},
                                "finish_reason": None
                            }]
                        )
                        yield f"data: {chunk_data.model_dump_json()}\n\n"
                        await asyncio.sleep(0.01)
                
                # logger.info(f"Streaming completed: {chunk_count} chunks")
                
                # 发送结束标记
                final_chunk = ChatCompletionChunk(
                    id=response_id,
                    created=created_at,
                    model=request.model,
                    choices=[{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop"
                    }]
                )
                yield f"data: {final_chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
                
            except Exception as e:
                logger.error(f"Streaming error: {e}", exc_info=True)
                error_chunk = {"error": {"message": str(e), "type": "internal_error"}}
                yield f"data: {json.dumps(error_chunk)}\n\n"
            # finally:
                # 🔓 释放 Metal GPU 锁
                # await release_metal_lock_async("MLX-VLM streaming")
        
        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream"
        )
    
    async def _generate_non_streaming_response(
        self,
        request: "OpenAIChatCompletionRequest",
        model, processor, prompt, images
    ):
        """生成非流式响应"""
        
        response_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        created_at = int(time.time())
        
        # logger.info("Starting non-streaming generation")
        
        # 🔒 获取 Metal GPU 锁
        # await acquire_metal_lock_async("MLX-VLM non-streaming")
        try:
            # 构造参数字典,只在有图片时传递 image 参数
            generate_kwargs = {
                "model": model,
                "processor": processor,
                "prompt": prompt,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens or 512,
                "top_p": request.top_p,
                "verbose": False
            }
            if images:
                generate_kwargs["image"] = images
            
            # 使用 generate 函数进行非流式推理
            result = generate(**generate_kwargs)
            
            result_text = result.text if hasattr(result, 'text') else str(result)
            # logger.info(f"Generation completed: {len(result_text)} chars")
        finally:
            # 🔓 释放 Metal GPU 锁
            # await release_metal_lock_async("MLX-VLM non-streaming")
            pass
        
        # 构造 OpenAI 格式响应
        response = OpenAIChatCompletionResponse(
            id=response_id,
            created=created_at,
            model=request.model,
            choices=[ChatCompletionChoice(
                index=0,
                message=ChatMessage(role="assistant", content=result_text),
                finish_reason="stop"
            )],
            usage=ChatCompletionUsage(
                prompt_tokens=getattr(result, 'prompt_tokens', 0),
                completion_tokens=getattr(result, 'generation_tokens', len(result_text) // 4),
                total_tokens=getattr(result, 'total_tokens', len(result_text) // 4)
            )
        )
        
        return response
    
    async def _unload_model_internal(self):
        """内部卸载方法"""
        if not self._model_cache:
            return
        
        # logger.info(f"Unloading model: {self._model_cache.get('model_path')}")
        self._model_cache = {}
        gc.collect()
        mx.clear_cache()
        # logger.info("Model unloaded and cache cleared")
    
    async def unload_model(self):
        """公共卸载方法（带锁保护）"""
        async with self._lock:
            await self._unload_model_internal()
    
    async def check_and_unload_if_unused(self, engine):
        """
        智能卸载逻辑：检查是否有任何能力仍在使用 MLX-VLM 模型
        
        如果 4 个能力（VISION, TEXT, STRUCTURED_OUTPUT, TOOL_USE）都已切换到其他模型，
        则自动卸载 MLX-VLM 模型以释放内存。
        
        Args:
            engine: SQLAlchemy engine 用于查询数据库
        """
        from sqlmodel import Session, select
        from db_mgr import CapabilityAssignment, ModelConfiguration
        
        # MLX-VLM 的模型标识符（与数据库中的 model_identifier 一致）
        MLX_VLM_MODEL_IDENTIFIER = "mlx-community/Qwen3-VL-4B-Instruct-3bit"
        
        with Session(engine) as session:
            # 查询所有能力分配
            assignments = session.exec(select(CapabilityAssignment)).all()
            
            # 检查是否有任何能力仍在使用 MLX-VLM
            for assignment in assignments:
                model_config = session.exec(
                    select(ModelConfiguration).where(
                        ModelConfiguration.id == assignment.model_configuration_id
                    )
                ).first()
                
                if model_config and model_config.model_identifier == MLX_VLM_MODEL_IDENTIFIER:
                    # logger.info(
                    #     f"Capability {assignment.capability_value} still using MLX-VLM, "
                    #     f"skipping unload"
                    # )
                    return False
            
            # 所有能力都已切换到其他模型，卸载 MLX-VLM
            # logger.info("All capabilities switched away from MLX-VLM, unloading model...")
            await self.unload_model()
            # logger.info("MLX-VLM model unloaded successfully")
            return True
    
    def is_model_loaded(self, model_path: str) -> bool:
        """检查指定模型是否已加载"""
        return self._model_cache.get("model_path") == model_path
    
    def get_queue_size(self) -> int:
        """获取当前队列大小"""
        return self._request_queue.qsize()


# ==================== 请求转换逻辑 ====================

def _extract_images_from_messages(messages: List[ChatMessage]) -> tuple[List[Dict[str, Any]], List[str]]:
    """
    从 OpenAI 消息格式中提取图片 URL，但保持消息结构用于 apply_chat_template
    
    支持两种格式:
    1. content 为 list: [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "..."}}]
    2. content 为 str: 纯文本
    
    重要：会合并多个连续的 system 消息为一条，以确保 apply_chat_template 正确插入图片占位符
    
    Returns:
        (消息字典列表（用于 apply_chat_template）, 图片URL列表（用于传递给 generate/stream_generate）)
    """
    message_dicts = []
    image_urls = []
    system_messages = []  # 临时存储连续的 system 消息
    
    def flush_system_messages():
        """合并并添加累积的 system 消息"""
        if system_messages:
            combined_system = "\n\n".join(system_messages)
            message_dicts.append({
                "role": "system",
                "content": combined_system
            })
            system_messages.clear()
    
    for msg in messages:
        if isinstance(msg.content, str):
            # 纯文本消息
            if msg.role == "system":
                system_messages.append(msg.content)
            else:
                # 先刷新累积的 system 消息
                flush_system_messages()
                message_dicts.append({
                    "role": msg.role,
                    "content": msg.content
                })
        elif isinstance(msg.content, list):
            # 多模态消息 - 提取文本和图片
            text_parts = []
            for part in msg.content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(part["text"])
                    elif part.get("type") == "image_url":
                        # 提取图片 URL 并预处理
                        url = part.get("image_url", {}).get("url") or part.get("image_url")
                        if url:
                            # 预处理图片（压缩大图片）
                            processed_url = preprocess_image(url, max_size=1920, quality=85)
                            image_urls.append(processed_url)
            
            # 合并文本部分并保存为字典
            combined_text = " ".join(text_parts)
            if combined_text:
                if msg.role == "system":
                    system_messages.append(combined_text)
                else:
                    # 先刷新累积的 system 消息
                    flush_system_messages()
                    message_dicts.append({
                        "role": msg.role,
                        "content": combined_text
                    })
    
    # 刷新最后的 system 消息
    flush_system_messages()
    
    return message_dicts, image_urls


# 全局单例
_model_manager = MLXVLMModelManager()
def get_vlm_manager() -> MLXVLMModelManager:
    """获取全局 VLM 模型管理器单例"""
    return _model_manager

# ==================== 测试代码 ====================
if __name__ == "__main__":
    import asyncio
    
    async def test_lazy_loading():
        """测试1: 懒加载"""
        print("\n" + "="*60)
        print("测试 1: 懒加载")
        print("="*60)
        
        manager = get_vlm_manager()
        model_path = "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/builtin_models/models--mlx-community--Qwen3-VL-4B-Instruct-3bit/snapshots/629882a0df4a41662d0b6d6aa7aedf56032501fd"
        
        # 首次加载会触发模型加载
        await manager.ensure_loaded(model_path)
        print(f"✅ 模型已加载: {manager.is_model_loaded(model_path)}")
        print(f"   队列大小: {manager.get_queue_size()}")
    
    async def test_simple_chat():
        """测试2: 简单聊天"""
        print("\n" + "="*60)
        print("测试 2: 简单聊天（非流式）")
        print("="*60)
        
        manager = get_vlm_manager()
        model_path = "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/builtin_models/models--mlx-community--Qwen3-VL-4B-Instruct-3bit/snapshots/629882a0df4a41662d0b6d6aa7aedf56032501fd"
        
        # 构造请求
        request = OpenAIChatCompletionRequest(
            model="qwen3-vl-4b",
            messages=[
                ChatMessage(role="user", content="用一句话介绍Python编程语言")
            ],
            max_tokens=100,
            temperature=0.7,
            stream=False
        )
        
        print("🚀 发送请求...")
        response = await manager.enqueue_request(
            request=request,
            model_path=model_path,
            priority=RequestPriority.HIGH
        )
        
        print("✅ 收到响应:")
        print(f"   ID: {response.id}")
        print(f"   内容: {response.choices[0].message.content}")
        print(f"   Tokens: {response.usage.total_tokens}")
    
    async def test_streaming_chat():
        """测试3: 流式聊天"""
        print("\n" + "="*60)
        print("测试 3: 流式聊天")
        print("="*60)
        
        manager = get_vlm_manager()
        model_path = "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/builtin_models/models--mlx-community--Qwen3-VL-4B-Instruct-3bit/snapshots/629882a0df4a41662d0b6d6aa7aedf56032501fd"
        
        # 构造流式请求
        request = OpenAIChatCompletionRequest(
            model="qwen3-vl-4b",
            messages=[
                ChatMessage(role="user", content="列举3个Python的优点")
            ],
            max_tokens=150,
            temperature=0.7,
            stream=True
        )
        
        print("🚀 发送流式请求...")
        response = await manager.enqueue_request(
            request=request,
            model_path=model_path,
            priority=RequestPriority.HIGH
        )
        
        # StreamingResponse 需要通过异步迭代器读取
        print("✅ 收到流式响应:")
        print("   ", end="", flush=True)
        
        # 注意: StreamingResponse 的 body_iterator 是异步生成器
        async for chunk in response.body_iterator:
            chunk_str = chunk.decode('utf-8') if isinstance(chunk, bytes) else chunk
            if chunk_str.startswith('data: '):
                data_str = chunk_str[6:].strip()
                if data_str and data_str != '[DONE]':
                    try:
                        import json
                        data = json.loads(data_str)
                        if 'choices' in data and len(data['choices']) > 0:
                            delta = data['choices'][0].get('delta', {})
                            content = delta.get('content', '')
                            if content:
                                print(content, end="", flush=True)
                    except json.JSONDecodeError:
                        pass
        print("\n")
    
    async def test_priority_queue():
        """测试4: 优先级队列"""
        print("\n" + "="*60)
        print("测试 4: 优先级队列（并发请求）")
        print("="*60)
        
        manager = get_vlm_manager()
        model_path = "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/builtin_models/models--mlx-community--Qwen3-VL-4B-Instruct-3bit/snapshots/629882a0df4a41662d0b6d6aa7aedf56032501fd"
        
        # 模拟低优先级请求（批量任务）
        low_request = OpenAIChatCompletionRequest(
            model="qwen3-vl-4b",
            messages=[ChatMessage(role="user", content="说'低优先级'")],
            max_tokens=20,
            stream=False
        )
        
        # 模拟高优先级请求（用户聊天）
        high_request = OpenAIChatCompletionRequest(
            model="qwen3-vl-4b",
            messages=[ChatMessage(role="user", content="说'高优先级'")],
            max_tokens=20,
            stream=False
        )
        
        print("🚀 同时发送低优先级和高优先级请求...")
        
        # 并发发送
        low_task = asyncio.create_task(
            manager.enqueue_request(low_request, model_path, RequestPriority.LOW)
        )
        await asyncio.sleep(0.1)  # 稍微延迟，让低优先级先入队
        
        high_task = asyncio.create_task(
            manager.enqueue_request(high_request, model_path, RequestPriority.HIGH)
        )
        
        # 等待结果
        results = await asyncio.gather(low_task, high_task)
        
        print(f"✅ 低优先级响应: {results[0].choices[0].message.content}")
        print(f"✅ 高优先级响应: {results[1].choices[0].message.content}")
        print("   (注意: 高优先级应该先被处理)")
    
    async def main():
        """运行所有测试"""
        print("\n" + "="*60)
        print("MLX-VLM 模型管理器测试套件")
        print("="*60)
        
        try:
            # 测试1: 懒加载
            await test_lazy_loading()
            
            # 测试2: 简单聊天
            await test_simple_chat()
            
            # 测试3: 流式聊天
            await test_streaming_chat()
            
            # 测试4: 优先级队列
            await test_priority_queue()
            
            print("\n" + "="*60)
            print("✅ 所有测试完成！")
            print("="*60)
            
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
    
    # 运行测试
    asyncio.run(main())