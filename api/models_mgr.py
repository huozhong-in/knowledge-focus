from config import singleton, EMBEDDING_MODEL
from typing import List, Dict, Any
import re
import json
import uuid
import time
import httpx
import logging
from sqlmodel import Session, select
from db_mgr import SystemConfig
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError
from pydantic_ai import Agent, Tool
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartStartEvent,
    PartDeltaEvent,
    TextPartDelta,
    ThinkingPartDelta,
    ToolCallPartDelta,
    FinalResultEvent,
)
from pydantic_ai.models.openai import OpenAIModel
# from pydantic_ai.profiles import InlineDefsJsonSchemaTransformer
# from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits
from model_config_mgr import ModelConfigMgr
from tool_provider import ToolProvider
from memory_mgr import MemoryMgr
from bridge_events import BridgeEventSender
from huggingface_hub import snapshot_download
from tqdm import tqdm
from mlx_embeddings.utils import load as load_embedding_model
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SessionTitleResponse(BaseModel):
    title: str = Field(description="Generated session title (max 20 characters)")

class TagResponse(BaseModel):
    tags: List[str] = Field(default_factory=list, description="List of generated tags")

# 定义一个可以在运行时创建的 BridgeProgressReporter 类
def create_bridge_progress_reporter(bridge_events, model_name):
    """
    动态创建带有bridge events的tqdm子类
    
    这个工厂函数解决了在类方法内部创建子类时的作用域问题。
    """    
    class BridgeProgressReporter(tqdm):
        """
        继承自真正的tqdm类，确保完全兼容
        """
        
        def __init__(self, *args, **kwargs):
            # 注入我们的自定义参数
            self.bridge_events = bridge_events
            self.model_name = model_name
            
            # 调用父类初始化
            super().__init__(*args, **kwargs)
            
            # 发送开始事件
            if self.bridge_events and not self.disable:
                self.bridge_events.model_download_progress(
                    model_name=self.model_name,
                    current=0,
                    total=self.total or 0,
                    message=f"开始下载 {self.model_name}",
                    stage="downloading"
                )
        
        def update(self, n=1):
            """重写update方法，添加bridge events"""
            # 调用父类的update方法
            result = super().update(n)
            
            # 发送进度事件
            if self.bridge_events and not self.disable:
                # 格式化消息
                if self.unit_scale and self.unit == 'B':
                    # 自动缩放字节单位
                    current_mb = self.n / (1024 * 1024)
                    total_mb = self.total / (1024 * 1024) if self.total and self.total > 0 else 0
                    message = f"{self.desc}: {current_mb:.1f}MB/{total_mb:.1f}MB"
                else:
                    message = f"{self.desc}: {self.n}/{self.total or '?'}"
                
                self.bridge_events.model_download_progress(
                    model_name=self.model_name,
                    current=self.n,
                    total=self.total or 0,
                    message=message,
                    stage="downloading"
                )
            
            return result
        
        def close(self):
            """重写close方法，发送完成事件"""
            # 发送完成事件
            if self.bridge_events and not self.disable:
                self.bridge_events.model_download_progress(
                    model_name=self.model_name,
                    current=self.n,
                    total=self.total or self.n,
                    message=f"{self.model_name} 下载完成",
                    stage="completed"
                )
            
            # 调用父类的close方法
            return super().close()
    
    return BridgeProgressReporter

@singleton
class ModelsMgr:
    def __init__(self, session: Session):
        self.session = session
        self.model_config_mgr = ModelConfigMgr(session)
        self.tool_provider = ToolProvider(session)
        self.memory_mgr = MemoryMgr(session)
        self.bridge_events = BridgeEventSender(source="models-manager")

    def get_embedding(self, text_str: str) -> List[float]:
        """
        Generates an embedding for the given text using sync OpenAI client.
        
        This is typically called by backend processes (document parsing, vectorization),
        so model validation failures will trigger IPC events to notify the frontend.
        """
        sqlite_url = str(self.session.get_bind().url)  # 从SQLite数据库路径推导出base_dir
        db_path = sqlite_url.replace('sqlite:///', '')
        cache_directory = os.path.dirname(db_path)
        model_path = self.download_embedding_model(EMBEDDING_MODEL, cache_directory)
        model, tokenizer = load_embedding_model(model_path)
        input_ids = tokenizer.encode(text_str, return_tensors="mlx")
        outputs = model(input_ids)
        # raw_embeds = outputs.last_hidden_state[:, 0, :] # CLS token
        text_embeds = outputs.text_embeds # mean pooled and normalized embeddings
        return text_embeds[0].tolist()

    def get_tags_from_llm(self, file_summary: str, candidate_tags: List[str]) -> List[str]:
        """
        Generates tags from the LLM using instructor and litellm.
        
        This is typically called by backend processes (file processing, tagging),
        so model validation failures will trigger IPC events to notify the frontend.
        """
        try:
            model_interface = self.model_config_mgr.get_text_model_config()
            model_identifier = model_interface.model_identifier
            base_url = model_interface.base_url
            api_key = model_interface.api_key
            use_proxy = model_interface.use_proxy
        except Exception as e:
            logger.error(f"Failed to get text model config: {e}")
            return []
        messages = [
            {"role": "system", "content": "You are a world-class librarian. Your task is to analyze the provided text and generate a list of relevant tags. Adhere strictly to the format required."},
            {"role": "user", "content": self._build_tagging_prompt(file_summary, candidate_tags)}
        ]
        proxy = self.session.exec(select(SystemConfig).where(SystemConfig.key == "proxy")).first()
        http_client = httpx.AsyncClient(proxy=proxy.value if proxy is not None and use_proxy else None)
        openai_client = AsyncOpenAI(
            api_key=api_key if api_key else "sk-xxx",
            base_url=base_url,
            max_retries=3,
            http_client=http_client,
        )
        model = OpenAIModel(
            model_name=model_identifier,
            provider=OpenAIProvider(
                openai_client=openai_client,
            ),
        )
        agent = Agent(
            model=model,
            system_prompt=messages[0]['content'],
            output_type=TagResponse,
        )
        try:
            response = agent.run_sync(
                user_prompt=messages[1]['content'],
                usage_limits=UsageLimits(response_tokens_limit=250), # 限制标签生成的最大token数
            )
            # print(response.output)
        except UsageLimitExceeded as e:
            print(e)
            return []
        except ValidationError as e:
            print(e)
            return []

        # # 把每个tag中间可能的空格替换为下划线，因为要避开英语中用连字符作为合成词的情况
        tags = [tag.replace(" ", "_") for tag in response.output.tags]
        # # 把每个tag前后的非字母数字字符去掉
        tags = [re.sub(r"^[^\w]+|[^\w]+$", "", tag) for tag in tags]
        return tags

    def generate_session_title(self, first_message_content: str) -> str:
        """
        Generate an intelligent session title based on the first user message.
        
        This method is typically called by backend processes (session creation),
        and uses a non-streaming approach for title generation.
        
        Args:
            first_message_content: The first user message content
            
        Returns:
            Generated session title (max 20 characters)
        """
        try:
            model_interface = self.model_config_mgr.get_text_model_config()
            model_identifier = model_interface.model_identifier
            base_url = model_interface.base_url
            api_key = model_interface.api_key
            use_proxy = model_interface.use_proxy
        except Exception as e:
            logger.error(f"Failed to get model config: {e}")
            return "新会话"
        try:
            messages = [
                {"role": "system", "content": "You are an expert at creating concise, meaningful titles. Generate a short title (max 20 characters) that captures the essence of the user's request or question."},
                {"role": "user", "content": self._build_title_prompt(first_message_content)}
            ]
            proxy = self.session.exec(select(SystemConfig).where(SystemConfig.key == "proxy")).first()
            http_client = httpx.AsyncClient(proxy=proxy.value if proxy is not None and use_proxy else None)
            openai_client = AsyncOpenAI(
                api_key=api_key if api_key else "sk-xxx",
                base_url=base_url,
                max_retries=3,
                http_client=http_client,
            )
            model = OpenAIModel(
                model_name=model_identifier,
                provider=OpenAIProvider(
                    openai_client=openai_client,
                ),
            )
            agent = Agent(
                model=model,
                system_prompt=messages[0]['content'],
                output_type=SessionTitleResponse,
            )
            response = agent.run_sync(
                user_prompt=messages[1]['content'],
                usage_limits=UsageLimits(response_tokens_limit=50),  # 限制生成的最大token数，确保简洁
            )
            title = response.output.title.strip()
            
            # 确保标题长度不超过20个字符
            if len(title) > 20:
                title = title[:17] + "..."
                
            return title if title else "新会话"

        except Exception as e:
            logger.error(f"Failed to generate session title: {e}")
            # 降级处理：使用简单截取方式
            fallback_title = first_message_content.strip()[:17]
            if len(first_message_content) > 17:
                fallback_title += "..."
            return fallback_title or "新会话"

    def _build_title_prompt(self, first_message: str) -> str:
        """Build prompt for session title generation"""
        return f'''
Please create a concise and meaningful title for a chat session based on the user's first message.

**Requirements:**
1. **Length:** Maximum 20 characters (including Chinese characters, English letters, numbers, and symbols)
2. **Language:** Use the same language as the user's message (Chinese for Chinese input, English for English input)
3. **Content:** Capture the main topic or intent of the user's question/request
4. **Style:** Clear, descriptive, and professional
5. **Special Cases:** For simple greetings like "你好", "hello", use generic titles like "新对话", "Chat Session"

**User's First Message:**
---
{first_message}
---

Generate a title that best represents what this conversation will be about. Avoid overly specific titles for vague or greeting-only messages.
        '''

    def _build_tagging_prompt(self, summary: str, candidates: List[str]) -> str:
        candidate_str = ", ".join(f'"{t}"' for t in candidates) if candidates else "None"
        return f'''
Please analyze the following file summary and context to generate between 0 and 3 relevant tags.

**Rules:**
1.  **Language:** If any Chinese characters in summary, generate Chinese Tags as top priority. Use English only for globally recognized acronyms (e.g., `AI`, `API`, `RAG`).
2.  **Format:** English tags must not contain spaces. Use a hyphen `_` to connect words (e.g., `project_management`), but keep hyphens `-` in compound words (e.g., `man-in-loop`).
3.  **Quality:** Tags must be meaningful and concise. Avoid generic or redundant tags.
4.  **Reuse First:** If any of the "Existing Candidate Tags" are highly relevant, reuse them.

**Existing Candidate Tags:**
[{candidate_str}]

**File Content Summary:**
---
{summary}
---

Based on all information, provide the best tags for this file.
        '''

    async def stream_chat(self, messages: List[Dict[str, Any]]):
        """
        Streams a chat response from the specified model provider.
        
        Note: This method is typically called by frontend requests, so model validation
        errors will be returned as HTTP responses rather than IPC events.
        """
        try:
            model_interface = self.model_config_mgr.get_text_model_config()
            model_identifier = model_interface.model_identifier
            base_url = model_interface.base_url
            api_key = model_interface.api_key
            use_proxy = model_interface.use_proxy
        except Exception as e:
            logger.error(f"Failed to get text model config: {e}")
            return

        proxy = self.session.exec(select(SystemConfig).where(SystemConfig.key == "proxy")).first()
        http_client = httpx.AsyncClient(proxy=proxy.value if proxy is not None and use_proxy else None)
        openai_client = AsyncOpenAI(
            api_key=api_key if api_key else "sk-xxx",
            base_url=base_url,
            max_retries=3,
            http_client=http_client,
        )
        model = OpenAIModel(
            model_name=model_identifier,
            provider=OpenAIProvider(
                openai_client=openai_client,
            ),
        )
        system_prompt = [msg['content'] for msg in messages if msg['role'] == 'system']
        agent = Agent(
            model=model,
            system_prompt=system_prompt[0] if system_prompt else "",
        )
        
        # 处理用户输入 - 兼容AI SDK v5的parts格式
        user_prompt_texts = []
        for msg in messages:
            if msg['role'] == 'user':
                # 优先从parts中提取文本内容
                content_text = ""
                if "parts" in msg:
                    for part in msg["parts"]:
                        if part.get("type") == "text":
                            content_text += part.get("text", "")
                
                # 备用：检查传统的content字段
                if not content_text:
                    content_text = msg.get("content", "")
                
                if content_text.strip():
                    user_prompt_texts.append(content_text.strip())
        
        if user_prompt_texts == []:
            raise ValueError("User prompt is empty")
        async with agent.run_stream(
                user_prompt=user_prompt_texts[0],
                # usage_limits=UsageLimits(response_tokens_limit=500),
            ) as response:
            # print(await response.get_output()) # 此行会破坏流式输出的效果
            async for message in response.stream_text(delta=True):
                yield message

    def get_chat_completion(self, messages: List[Dict[str, Any]]) -> str:
        """
        Get a single chat completion response (non-streaming).
        
        This method can be used for both backend processing and frontend requests.
        For frontend-initiated requests, consider using silent_validation=True
        to let the frontend handle errors directly via HTTP responses.
        
        Args:
            messages: Chat messages
            role_type: Model role type
            
        Returns:
            The completion response as a string
        """
        try:
            model_interface = self.model_config_mgr.get_text_model_config()
            model_identifier = model_interface.model_identifier
            base_url = model_interface.base_url
            api_key = model_interface.api_key
            use_proxy = model_interface.use_proxy
        except Exception as e:
            logger.error(f"Failed to get model config: {e}")
            return "新会话"
        try:
            proxy = self.session.exec(select(SystemConfig).where(SystemConfig.key == "proxy")).first()
            http_client = httpx.AsyncClient(proxy=proxy.value if proxy is not None and use_proxy else None)
            openai_client = AsyncOpenAI(
                api_key=api_key if api_key else "sk-xxx",
                base_url=base_url,
                max_retries=3,
                http_client=http_client,
            )
            model = OpenAIModel(
                model_name=model_identifier,
                provider=OpenAIProvider(
                    openai_client=openai_client,
                ),
            )
            system_prompt = [msg['content'] for msg in messages if msg['role'] == 'system']
            agent = Agent(
                model=model,
                system_prompt=system_prompt[0] if system_prompt else "",
            )
            
            # 处理用户输入 - 兼容AI SDK v5的parts格式
            user_prompt_texts = []
            for msg in messages:
                if msg['role'] == 'user':
                    # 优先从parts中提取文本内容
                    content_text = ""
                    if "parts" in msg:
                        for part in msg["parts"]:
                            if part.get("type") == "text":
                                content_text += part.get("text", "")
                    
                    # 备用：检查传统的content字段
                    if not content_text:
                        content_text = msg.get("content", "")
                    
                    if content_text.strip():
                        user_prompt_texts.append(content_text.strip())
            
            if user_prompt_texts == []:
                raise ValueError("User prompt is empty")
            response = agent.run_sync(
                user_prompt=user_prompt_texts[0]
                # usage_limits=UsageLimits(response_tokens_limit=50),
            )
            return response.output
        except Exception as e:
            logger.error(f"Failed to get chat completion: {e}")
            raise ValueError("Failed to get chat completion")

    async def stream_agent_chat_v5_compatible(self, messages: List[Dict], session_id: int):
        """
        创建一个完全符合Vercel AI SDK v5 UI Message Stream格式的流响应生成器
        
        这个版本集成了真实的AI agent逻辑，但保持v5兼容的SSE格式。
        """
        try:
            logger.info(f"Agent chat v5_compatible invoked for session_id: {session_id}")

            # 获取模型配置
            model_interface = self.model_config_mgr.get_text_model_config()
            if model_interface is None:
                logger.error("Model interface is not configured.")
                yield f'data: {json.dumps({"type": "error", "errorText": "Model interface is not configured."})}\n\n'
                return
            
            model_identifier = model_interface.model_identifier
            base_url = model_interface.base_url
            api_key = model_interface.api_key
            use_proxy = model_interface.use_proxy
            max_context_length = model_interface.max_context_length if model_interface.max_context_length != 0 else 4096
            max_output_tokens = model_interface.max_output_tokens if model_interface.max_output_tokens != 0 else 1024

            # 设置HTTP客户端和OpenAI客户端
            proxy = self.session.exec(select(SystemConfig).where(SystemConfig.key == "proxy")).first()
            http_client = httpx.AsyncClient(proxy=proxy.value if proxy is not None and use_proxy else None)
            openai_client = AsyncOpenAI(
                api_key=api_key if api_key else "sk-xxx",
                base_url=base_url,
                max_retries=3,
                http_client=http_client,
            )
            model = OpenAIModel(
                model_name=model_identifier,
                provider=OpenAIProvider(
                    openai_client=openai_client,
                ),
            )
            
            # 准备工具
            tools = [Tool(tool, takes_ctx=True) for tool in self.tool_provider.get_tools_for_session(session_id)]
            count_tokens_tools = self.memory_mgr.calculate_tools_tokens(tools)
            logger.info(f"当前工具数: {len(tools)}, 当前token数: {count_tokens_tools}")
            
            # 构建系统prompt
            system_prompt = ["You are a helpful assistant."]
            scenario_system_prompt = self.tool_provider.get_session_scenario_system_prompt(session_id)
            if scenario_system_prompt:
                system_prompt.append(scenario_system_prompt)
            count_tokens_system_prompt = self.memory_mgr.calculate_string_tokens("\n".join(system_prompt))
            logger.info(f"当前系统prompt token数: {count_tokens_system_prompt}")
            
            # 处理用户输入 - 兼容AI SDK v5的parts格式
            user_prompt: List[str] = []
            for msg in messages:
                if msg['role'] == 'user':
                    # 优先从parts中提取文本内容
                    content_text = ""
                    if "parts" in msg:
                        for part in msg["parts"]:
                            if part.get("type") == "text":
                                content_text += part.get("text", "")
                    
                    # 备用：检查传统的content字段
                    if not content_text:
                        content_text = msg.get("content", "")
                    
                    if content_text.strip():
                        user_prompt.append(content_text.strip())
            
            if user_prompt == []:
                yield f'data: {"type": "error", "errorText": "User prompt is empty"}\n\n'
                return
            
            count_tokens_user_prompt = self.memory_mgr.calculate_string_tokens("\n".join(user_prompt))
            logger.info(f"当前用户prompt token数: {count_tokens_user_prompt}")
            
            # 留给会话历史记录的token数
            available_tokens = max_context_length - max_output_tokens - count_tokens_tools - count_tokens_system_prompt - count_tokens_user_prompt
            logger.info(f"当前可用历史消息token数: {available_tokens}")
            chat_history: List[str] = self.memory_mgr.trim_messages_to_fit(session_id, available_tokens)
            
            # RAG：将pin文件关联的知识片段召回并插到用户提示词上方
            user_query = "\n".join(user_prompt)  # 合并用户输入作为查询
            rag_context, rag_sources = self._get_rag_context(session_id, user_query, available_tokens)
            if rag_context:
                user_prompt = ["## 相关知识背景："] + [rag_context] + ['\n\n---\n\n'] + user_prompt
                logger.info(f"RAG检索到 {len(rag_sources)} 个相关片段")
                
                # 通过桥接器发送RAG数据到知识观察窗
                self._send_rag_to_observation_window(rag_sources, user_query)
            
            # 将会话历史记录插到用户提示词上方
            if chat_history != []:
                user_prompt = ["## 会话历史: "] + chat_history + ['\n\n---\n\n'] + user_prompt
            logger.info(f"当前用户提示词: {user_prompt}")
            
            # 创建agent
            agent = Agent(
                model=model,
                tools=tools,
                system_prompt=system_prompt,
            )

            # 状态跟踪变量 
            current_part_type = None  # 当前部分类型 ('text', 'reasoning', 'tool')
            current_part_id = None    # 当前部分的 ID
            active_tool_calls = {}    # 跟踪活跃的工具调用

            def end_current_part():
                """结束当前部分并发送 end 事件"""
                nonlocal current_part_type, current_part_id
                if current_part_type and current_part_id:
                    if current_part_type == 'text':
                        data = {"type": "text-end", "id": current_part_id}
                        return f'data: {json.dumps(data)}\n\n'
                    elif current_part_type == 'reasoning':
                        data = {"type": "reasoning-end", "id": current_part_id}
                        return f'data: {json.dumps(data)}\n\n'
                current_part_type = None
                current_part_id = None
                return None

            def start_new_part(part_type: str, part_id: str):
                """开始新部分并发送 start 事件"""
                nonlocal current_part_type, current_part_id
                current_part_type = part_type
                current_part_id = part_id
                if part_type == 'text':
                    data = {"type": "text-start", "id": part_id}
                    return f'data: {json.dumps(data)}\n\n'
                elif part_type == 'reasoning':
                    data = {"type": "reasoning-start", "id": part_id}
                    return f'data: {json.dumps(data)}\n\n'
                return None

            # 使用 agent.iter() 方法来逐个迭代 agent 的图节点
            async with agent.iter(user_prompt=user_prompt, deps=session_id) as run:
                async for node in run:
                    # logger.info(f"Processing node type: {type(node)}")
                    if Agent.is_user_prompt_node(node):
                        # 用户输入节点 - 在v5协议中我们不需要发送user-prompt事件
                        # AI SDK v5协议中用户消息由前端直接处理，我们只处理AI响应
                        logger.info(f"Processing user prompt node: {node.user_prompt}")
                        # 跳过，不发送事件
                    elif Agent.is_model_request_node(node):
                        # 模型请求节点 - 可以流式获取模型的响应
                        async with node.stream(run.ctx) as request_stream:
                            final_result_found = False
                            # logger.info("Starting model request stream processing")
                            async for event in request_stream:
                                # logger.info(f"Received event type: {type(event)}")
                                if isinstance(event, PartStartEvent):
                                    logger.info("Processing PartStartEvent")
                                    # 在AI SDK v5中，我们不需要发送通用的start事件
                                    # 文本部分会在TextPartDelta事件中自动开始
                                    # logger.info("Skipping PartStartEvent - will start parts when content arrives")
                                    continue
                                elif isinstance(event, PartDeltaEvent):
                                    # logger.info(f"Processing PartDeltaEvent with delta type: {type(event.delta)}")
                                    if isinstance(event.delta, TextPartDelta):
                                        # logger.info(f"Processing TextPartDelta: {event.delta.content_delta}")
                                        # 检查是否需要切换到文本类型
                                        if current_part_type != 'text':
                                            # 结束之前的部分
                                            end_event = end_current_part()
                                            if end_event:
                                                yield end_event
                                            # 开始新的文本部分
                                            part_id = f"msg_{uuid.uuid4().hex}"
                                            start_event = start_new_part('text', part_id)
                                            if start_event:
                                                yield start_event
                                        
                                        # 文本增量事件
                                        data = {
                                            "type": "text-delta",
                                            "id": current_part_id,
                                            "delta": event.delta.content_delta
                                        }
                                        # logger.info(f"Yielding text-delta: {data}")
                                        yield f'data: {json.dumps(data)}\n\n'
                                    elif isinstance(event.delta, ThinkingPartDelta):
                                        # 检查是否需要切换到思考类型
                                        if current_part_type != 'reasoning':
                                            # 结束之前的部分
                                            end_event = end_current_part()
                                            if end_event:
                                                yield end_event
                                            # 开始新的思考部分
                                            part_id = f"reasoning_{uuid.uuid4().hex}"
                                            start_event = start_new_part('reasoning', part_id)
                                            if start_event:
                                                yield start_event
                                        
                                        # 思考过程增量事件
                                        data = {
                                            "type": "reasoning-delta",
                                            "id": current_part_id,
                                            "delta": event.delta.content_delta
                                        }
                                        yield f'data: {json.dumps(data)}\n\n'
                                    elif isinstance(event.delta, ToolCallPartDelta):
                                        # 结束当前文本/思考部分（如果有的话）
                                        if current_part_type in ['text', 'reasoning']:
                                            end_event = end_current_part()
                                            if end_event:
                                                yield end_event
                                        
                                        tool_call_id = event.delta.tool_call_id
                                        if tool_call_id:
                                            # 如果是新的工具调用，发送 tool-input-start
                                            if tool_call_id not in active_tool_calls:
                                                active_tool_calls[tool_call_id] = {
                                                    'id': tool_call_id,
                                                    'started': True
                                                }
                                                # 发送 tool-input-start 事件
                                                data = {
                                                    "type": "tool-input-start",
                                                    "toolCallId": tool_call_id,
                                                    "toolName": event.delta.tool_name_delta or ""
                                                }
                                                yield f'data: {json.dumps(data)}\n\n'
                                            
                                            # 工具调用参数增量事件
                                            data = {
                                                "type": "tool-input-delta",
                                                "toolCallId": tool_call_id,
                                                "inputTextDelta": event.delta.args_delta
                                            }
                                            yield f'data: {json.dumps(data)}\n\n'
                                elif isinstance(event, FinalResultEvent):
                                    # logger.info("Processing FinalResultEvent")
                                    # 结束当前部分
                                    end_event = end_current_part()
                                    if end_event:
                                        yield end_event
                                    
                                    # FinalResultEvent 标志工具调用完成，准备输出最终文本
                                    final_result_found = True
                                    break

                            # 如果找到了最终结果，开始流式输出文本
                            if final_result_found:
                                # logger.info("Starting final result text streaming")
                                # 重置当前部分状态，因为这是一个新的文本流
                                current_part_type = None
                                current_part_id = None
                                
                                try:
                                    # logger.info("About to call request_stream.stream_text(delta=True)")
                                    async for output in request_stream.stream_text(delta=True):
                                        # logger.info(f"Streaming text output: {output}")
                                        # 检查是否需要开始新的文本部分
                                        if current_part_type != 'text':
                                            # 开始新的文本部分
                                            part_id = f"msg_{uuid.uuid4().hex}"
                                            start_event = start_new_part('text', part_id)
                                            if start_event:
                                                yield start_event
                                        
                                        data = {
                                            "type": "text-delta",
                                            "id": current_part_id,
                                            "delta": output
                                        }
                                        # logger.info(f"Yielding final text-delta: {data}")
                                        yield f'data: {json.dumps(data)}\n\n'
                                    # logger.info("Finished streaming text from request_stream")
                                except Exception as e:
                                    logger.error(f"Error in final result text streaming: {e}")
                            else:
                                logger.info("final_result_found is False, skipping text streaming")
                    elif Agent.is_call_tools_node(node):
                        # 工具调用节点 - 处理工具的调用和响应
                        async with node.stream(run.ctx) as handle_stream:
                            async for event in handle_stream:
                                if isinstance(event, FunctionToolCallEvent):
                                    tool_call_id = event.part.tool_call_id
                                    
                                    # 确保发送了 start 和 delta 事件
                                    if tool_call_id not in active_tool_calls:
                                        # 发送 tool-input-start
                                        data = {
                                            "type": "tool-input-start",
                                            "toolCallId": tool_call_id,
                                            "toolName": event.part.tool_name
                                        }
                                        yield f'data: {json.dumps(data)}\n\n'
                                        
                                        # 发送 tool-input-delta（如果有参数）
                                        if event.part.args:
                                            args_str = event.part.args_as_json_str()
                                            data = {
                                                "type": "tool-input-delta",
                                                "toolCallId": tool_call_id,
                                                "inputTextDelta": args_str
                                            }
                                            yield f'data: {json.dumps(data)}\n\n'
                                        
                                        active_tool_calls[tool_call_id] = {
                                            'id': tool_call_id,
                                            'started': True
                                        }
                                    
                                    # 工具调用完整参数可用事件
                                    data = {
                                        "type": "tool-input-available",
                                        "toolCallId": tool_call_id,
                                        "toolName": event.part.tool_name,
                                        "input": event.part.args
                                    }
                                    yield f'data: {json.dumps(data)}\n\n'
                                elif isinstance(event, FunctionToolResultEvent):
                                    # 工具结果事件
                                    data = {
                                        "type": "tool-output-available",
                                        "toolCallId": event.tool_call_id,
                                        "output": event.result.content
                                    }
                                    yield f'data: {json.dumps(data)}\n\n'
                    elif Agent.is_end_node(node):
                        # 结束最后的部分（如果有的话）
                        end_event = end_current_part()
                        if end_event:
                            yield end_event
                        
                        # 结束节点 - agent 运行完成
                        data = {
                            "type": "finish"
                        }
                        yield f'data: {json.dumps(data)}\n\n'
                        yield 'data: [DONE]\n\n'
                        break
                    else:
                        # 其他未处理的节点类型
                        logging.warning(f"Unhandled node type: {type(node)}")
            
        except Exception as e:
            logger.error(f"Error in stream_agent_chat_v5_compatible: {e}")
            yield f'data: {json.dumps({"type": "error", "errorText": str(e)})}\n\n'

    def download_embedding_model(self, model_id: str, cache_dir: str = None) -> str:
        """
        下载指定的embedding模型到本地
        
        Args:
            model_id: HuggingFace模型ID，如 'BAAI/bge-small-zh-v1.5'
            cache_dir: 缓存目录，默认使用HuggingFace默认目录
            
        Returns:
            str: 下载后的本地模型路径
            
        Raises:
            Exception: 下载过程中的其他错误
        """
        
        try:
            # 使用工厂函数创建自定义的tqdm子类
            ProgressReporter = create_bridge_progress_reporter(
                bridge_events=self.bridge_events,
                model_name=model_id
            )            
            # 使用snapshot_download下载模型
            local_path = snapshot_download(
                repo_id=model_id,
                cache_dir=cache_dir,
                tqdm_class=ProgressReporter,
                allow_patterns=["*.safetensors", "*.json", "*.txt"],  # 只下载需要的文件
            )
            # 发送完成事件
            self.bridge_events.model_download_completed(
                model_name=model_id,
                local_path=local_path,
                message=f"模型 {model_id} 下载完成"
            )
            return local_path
            
        except Exception as e:
            error_msg = f"下载模型失败: {str(e)}"
            logger.error(f"下载模型 {model_id} 失败: {e}", exc_info=True)
            # 发送失败事件
            self.bridge_events.model_download_failed(
                model_name=model_id,
                error_message=error_msg,
                details={"exception_type": type(e).__name__}
            )            
            raise

    def _get_rag_context(self, session_id: int, user_query: str, available_tokens: int) -> tuple[str, list]:
        """
        获取RAG上下文和来源信息
        
        Args:
            session_id: 会话ID  
            user_query: 用户查询内容
            available_tokens: 可用token数量
            
        Returns:
            tuple: (rag_context_text, rag_sources_list)
        """
        try:
            # 获取会话Pin文件对应的文档ID
            from chatsession_mgr import ChatSessionMgr
            chat_mgr = ChatSessionMgr(self.session)
            document_ids = chat_mgr.get_pinned_document_ids(session_id)
            
            if not document_ids:
                logger.debug(f"会话 {session_id} 没有Pin文档，跳过RAG")
                return "", []
            
            # 使用SearchManager进行检索
            from lancedb_mgr import LanceDBMgr
            sqlite_url = str(self.session.get_bind().url)  # 从SQLite数据库路径推导出base_dir
            if sqlite_url.startswith('sqlite:///'):
                db_path = sqlite_url.replace('sqlite:///', '')
                db_directory = os.path.dirname(db_path)
                lancedb_mgr = LanceDBMgr(base_dir=db_directory)
            from search_mgr import SearchManager
            search_mgr = SearchManager(
                session=self.session, 
                lancedb_mgr=lancedb_mgr, 
                models_mgr=self
            )
            # 执行搜索，限制在Pin的文档内
            search_response = search_mgr.search_documents(
                query=user_query,
                top_k=5,  # 取前5个最相关的片段
                document_ids=document_ids  # 限制搜索范围
            )
            
            # 检查搜索是否成功
            if not search_response or not search_response.get('success', False):
                error_msg = search_response.get('error', '未知错误') if search_response else '搜索响应为空'
                logger.debug(f"RAG检索失败: {error_msg}")
                return "", []
            
            # 获取实际的搜索结果
            search_results = search_response.get('raw_results', [])
            if not search_results:
                logger.debug(f"RAG检索无结果，查询: {user_query[:50]}...")
                return "", []
            
            logger.debug(f"RAG检索到 {len(search_results)} 个结果")
            if search_results:
                logger.debug(f"首个结果字段: {list(search_results[0].keys())}")
            
            # 构建RAG上下文文本
            context_parts = []
            sources = []
            
            for result in search_results:
                # 限制每个片段的长度，避免token超限
                content = result.get('retrieval_content', '')[:1000]  # 限制1000字符
                
                # 将distance转换为相似度百分比 (1 - normalized_distance)
                distance = result.get('_distance', 1.0)  # 修正字段名
                # 假设distance在0-2之间，转换为相似度百分比
                similarity_score = max(0.0, min(1.0, 1.0 - (distance / 2.0)))
                
                source_info = {
                    'chunk_id': result.get('child_chunk_id', ''),
                    'file_path': result.get('file_path', ''),
                    'similarity_score': similarity_score,  # 使用转换后的相似度
                    'content': content,
                    'metadata': result.get('metadata', {})
                }
                
                context_parts.append(f"**来源**: {result.get('file_path', '未知文件')}\n{content}")
                sources.append(source_info)
            
            rag_context = "\n\n".join(context_parts)
            
            logger.info(f"RAG成功检索 {len(sources)} 个片段，总长度: {len(rag_context)} 字符")
            return rag_context, sources
            
        except Exception as e:
            logger.error(f"RAG检索失败: {e}", exc_info=True)
            return "", []

    def _send_rag_to_observation_window(self, rag_sources: list, user_query: str):
        """
        通过桥接器发送RAG数据到知识观察窗
        
        Args:
            rag_sources: RAG检索的来源列表
            user_query: 用户查询内容
        """
        try:
            if not rag_sources:
                return
                
            # 构建发送给观察窗的数据
            observation_data = {
                "timestamp": int(time.time() * 1000),
                "query": user_query[:200],  # 限制查询长度
                "sources_count": len(rag_sources),
                "sources": [
                    {
                        "file_path": source.get('file_path', ''),
                        "similarity_score": round(source.get('similarity_score', 0.0), 3),
                        "content_preview": source.get('content', '')[:300],  # 内容预览
                        "chunk_id": source.get('chunk_id'),
                        "metadata": source.get('metadata', {})
                    }
                    for source in rag_sources
                ],
                "event_type": "rag_retrieval"
            }
            
            # 通过桥接器发送事件
            self.bridge_events.send_event("rag-retrieval-result", observation_data)
            
            logger.debug(f"RAG观察数据已发送: {len(rag_sources)} 个来源")
            
        except Exception as e:
            logger.error(f"发送RAG观察数据失败: {e}", exc_info=True)


# for testing
if __name__ == "__main__":
    from config import TEST_DB_PATH
    from sqlmodel import create_engine
    session = Session(create_engine(f'sqlite:///{TEST_DB_PATH}'))
    mgr = ModelsMgr(session)

    # # Test get TEXT model interface
    # model_interface = mgr.model_config_mgr.get_text_model_config()
    # print(model_interface.model_dump())
    
    # import asyncio

    # # Test embedding generation
    # embedding = mgr.get_embedding("北京是中国的首都，拥有丰富的历史和文化。")
    # print("Embedding Length:", len(embedding))
    
    # # Test tag generation
    # tags = mgr.get_tags_from_llm("北京是中国的首都，拥有丰富的历史和文化。", ["北京", "首都"])
    # print("Generated Tags:", tags)
        
    # # test generate title
    # title = mgr.generate_session_title('你好，我想了解一下人工智能的发展历史')
    # print('Generated title:', title)
    
    # # Test chat completion
    # try:
    #     chat_response = mgr.get_chat_completion([
    #         {"role": "user", "content": "尽量列举一些首都城市的名字"}
    #     ])
    #     print("Chat Response:", chat_response)
    # except Exception as e:
    #     print("Chat Error:", e)

    # # test stream
    # async def test_stream():
    #     messages = [
    #         {'role': 'user', 'content': 'What is the weather in Beijing?'}
    #     ]
        
    #     print('Testing Vercel AI SDK compatible stream protocol:')
    #     print('=' * 50)
        
    #     async for chunk in mgr.stream_agent_chat(messages, session_id=1):
    #         print(chunk, end='')
    
    # asyncio.run(test_stream())

    # # 下载MLX优化的Qwen3 Embedding模型
    # import os
    # cache_dir = os.path.dirname(TEST_DB_PATH)
    # path = mgr.download_embedding_model(EMBEDDING_MODEL, cache_dir)
    # print(path)
    
    # === RAG测试代码 ===
    print("\n" + "="*50)
    print("测试RAG检索结果和相似度计算")
    print("="*50)
    
    # 测试会话ID=18的RAG检索
    session_id = 18
    user_query = "Manus项目有哪些经验教训？"
    available_tokens = 2000
    
    print(f"测试查询: {user_query}")
    print(f"会话ID: {session_id}")
    
    try:
        rag_context, rag_sources = mgr._get_rag_context(session_id, user_query, available_tokens)
        
        print("\n检索结果:")
        print(f"- 上下文长度: {len(rag_context)} 字符")
        print(f"- 来源数量: {len(rag_sources)}")
        
        if rag_sources:
            print("\n详细来源信息:")
            for i, source in enumerate(rag_sources):
                print(f"\n[来源 {i+1}]")
                print(f"  文件: {source.get('file_path', 'Unknown')}")
                print(f"  相似度分数: {source.get('similarity_score', 0.0)}")
                print(f"  内容长度: {len(source.get('content', ''))}")
                print(f"  内容预览: {source.get('content', '')[:200]}...")
                
                # 如果有原始distance数据，也显示出来
                if 'raw_distance' in source:
                    print(f"  原始距离: {source.get('raw_distance')}")
        
        # 同时测试SearchManager的原始返回
        print("\n" + "-"*30)
        print("原始SearchManager返回数据:")
        
        from chatsession_mgr import ChatSessionMgr
        chat_mgr = ChatSessionMgr(session)
        document_ids = chat_mgr.get_pinned_document_ids(session_id)
        print(f"Pin的文档ID: {document_ids}")
        
        if document_ids:
            from lancedb_mgr import LanceDBMgr
            from search_mgr import SearchManager
            
            sqlite_url = str(session.get_bind().url)
            db_path = sqlite_url.replace('sqlite:///', '')
            db_directory = os.path.dirname(db_path)
            lancedb_mgr = LanceDBMgr(base_dir=db_directory)
            
            search_mgr = SearchManager(
                session=session, 
                lancedb_mgr=lancedb_mgr, 
                models_mgr=mgr
            )
            
            search_response = search_mgr.search_documents(
                query=user_query,
                top_k=5,
                document_ids=document_ids
            )
            
            if search_response and search_response.get('success'):
                raw_results = search_response.get('raw_results', [])
                print(f"原始结果数量: {len(raw_results)}")
                
                if raw_results:
                    print(f"\n首个原始结果字段: {list(raw_results[0].keys())}")
                    
                    for i, result in enumerate(raw_results[:3]):  # 只显示前3个
                        print(f"\n[原始结果 {i+1}]")
                        print(f"  所有字段: {result}")
                        
                        distance = result.get('distance', 'N/A')
                        print(f"  原始distance: {distance}")
                        
                        # 使用相同的转换公式
                        if isinstance(distance, (int, float)):
                            similarity_score = max(0.0, min(1.0, 1.0 - (distance / 2.0)))
                            print(f"  转换后相似度: {similarity_score} ({similarity_score*100:.1f}%)")
            else:
                print(f"搜索失败: {search_response.get('error', '未知错误') if search_response else '无响应'}")
                
    except Exception as e:
        print(f"RAG测试失败: {e}")
        import traceback
        traceback.print_exc()
