# from config import EMBEDDING_DIMENSIONS
from config import singleton
from typing import List, Dict, Any
import re
import json
import uuid
import httpx
import logging
from sqlmodel import Session, select
from db_mgr import SystemConfig
from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel, Field, ValidationError
from pydantic_ai import Agent
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
from bridge_events import BridgeEventSender

logger = logging.getLogger(__name__)

class SessionTitleResponse(BaseModel):
    title: str = Field(description="Generated session title (max 20 characters)")

class TagResponse(BaseModel):
    tags: List[str] = Field(default_factory=list, description="List of generated tags")

@singleton
class ModelsMgr:
    def __init__(self, session: Session):
        self.session = session
        self.model_config_mgr = ModelConfigMgr(session)
        self.bridge_events = BridgeEventSender(source="models-manager")

    def get_embedding(self, text_str: str) -> List[float]:
        """
        Generates an embedding for the given text using sync OpenAI client.
        
        This is typically called by backend processes (document parsing, vectorization),
        so model validation failures will trigger IPC events to notify the frontend.
        """
        try:
            model_interface = self.model_config_mgr.get_embedding_model_config()
            model_identifier = model_interface.model_identifier
            base_url = model_interface.base_url
            api_key = model_interface.api_key
            use_proxy = model_interface.use_proxy
        except Exception as e:
            logger.error(f"Failed to get embedding model config: {e}")
            return []
        
        proxy = self.session.exec(select(SystemConfig).where(SystemConfig.key == "proxy")).first()
        http_client = httpx.Client(proxy=proxy.value if proxy is not None and use_proxy else None)
        openai_client = OpenAI(
            api_key=api_key if api_key else "sk-xxx",
            base_url=base_url,
            max_retries=3,
            http_client=http_client,
        )
        response = openai_client.embeddings.create(
            model=model_identifier,
            input=text_str,
        )
        return response.data[0].embedding

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
        user_prompt = [msg['content'] for msg in messages if msg['role'] == 'user']
        if user_prompt == []:
            raise ValueError("User prompt is empty")
        async with agent.run_stream(
                user_prompt=user_prompt[0],
                # usage_limits=UsageLimits(response_tokens_limit=500),
            ) as response:
            # print(await response.get_output()) # 此行会破坏流式输出的效果
            async for message in response.stream_text(delta=True):
                yield message
    
    async def stream_agent_chat(self, messages: List[Dict], session_id: int):
        """
        Streams an agentic chat response, using dynamic tools based on session context.
        
        This implementation now uses a dummy tool to demonstrate streaming of structured
        events like tool calls and tool results.
        """
        logging.info(f"Agent chat invoked for session_id: {session_id}")

        try:
            model_interface = self.model_config_mgr.get_text_model_config()
            model_identifier = model_interface.model_identifier
            base_url = model_interface.base_url
            api_key = model_interface.api_key
            use_proxy = model_interface.use_proxy
        except Exception as e:
            logger.error(f"Failed to get text model config: {e}")
            yield {"type": "error", "error": str(e)}
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
        
        # TODO: Replace this with a call to the real ToolProvider
        # def get_weather(city: str = Field(..., description="The city to get the weather for")) -> str:
        #     """
        #     A dummy function to get the weather for a city.
        #     """
        #     if "beijing" in city.lower():
        #         return "The weather in Beijing is sunny."
        #     if "tokyo" in city.lower():
        #         return "The weather in Tokyo is rainy."
        #     return f"Sorry, I don't know the weather for {city}."
        
        
        system_prompt = [msg['content'] for msg in messages if msg['role'] == 'system']
        
        agent = Agent(
            model=model,
            # tools=[get_weather],
            system_prompt=system_prompt[0] if system_prompt else "You are a helpful assistant.",
        )

        user_prompt = [msg['content'] for msg in messages if msg['role'] == 'user']
        if not user_prompt:
            raise ValueError("User prompt is empty")

        # 状态跟踪变量
        current_part_type = None  # 当前部分类型 ('text', 'reasoning', 'tool')
        current_part_id = None    # 当前部分的 ID
        active_tool_calls = {}    # 跟踪活跃的工具调用 {tool_call_id: {'id': str, 'started': bool}}
        message_id_counter = 0    # 全局唯一的 messageId 计数器

        def end_current_part():
            """结束当前部分并发送 end 事件"""
            nonlocal current_part_type, current_part_id
            if current_part_type and current_part_id:
                if current_part_type == 'text':
                    data = {"type": "text-end", "id": current_part_id}
                    return f'data: {json.dumps(data)}\n'
                elif current_part_type == 'reasoning':
                    data = {"type": "reasoning-end", "id": current_part_id}
                    return f'data: {json.dumps(data)}\n'
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
                return f'data: {json.dumps(data)}\n'
            elif part_type == 'reasoning':
                data = {"type": "reasoning-start", "id": part_id}
                return f'data: {json.dumps(data)}\n'
            return None

        # 使用 agent.iter() 方法来逐个迭代 agent 的图节点
        async with agent.iter(user_prompt=user_prompt[-1], deps=None) as run:
            async for node in run:
                if Agent.is_user_prompt_node(node):
                    # 结束之前的部分
                    end_event = end_current_part()
                    if end_event:
                        yield end_event
                    
                    # 用户输入节点
                    data = {"type": "user-prompt", "content": node.user_prompt}
                    yield f'data: {json.dumps(data)}\n'
                elif Agent.is_model_request_node(node):
                    # 模型请求节点 - 可以流式获取模型的响应
                    async with node.stream(run.ctx) as request_stream:
                        final_result_found = False
                        async for event in request_stream:
                            if isinstance(event, PartStartEvent):
                                data = {"type": "start", "messageId": message_id_counter}
                                message_id_counter += 1
                                yield f'data: {json.dumps(data)}\n'
                            elif isinstance(event, PartDeltaEvent):
                                if isinstance(event.delta, TextPartDelta):
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
                                    yield f'data: {json.dumps(data)}\n'
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
                                    yield f'data: {json.dumps(data)}\n'
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
                                            yield f'data: {json.dumps(data)}\n'
                                        
                                        # 工具调用参数增量事件
                                        data = {
                                            "type": "tool-input-delta",
                                            "toolCallId": tool_call_id,
                                            "inputTextDelta": event.delta.args_delta
                                        }
                                        yield f'data: {json.dumps(data)}\n'
                            elif isinstance(event, FinalResultEvent):
                                # 结束当前部分
                                end_event = end_current_part()
                                if end_event:
                                    yield end_event
                                
                                # FinalResultEvent 标志工具调用完成，准备输出最终文本
                                # 不发送特殊事件，让后续文本按标准协议处理
                                final_result_found = True
                                break

                        # 如果找到了最终结果，开始流式输出文本
                        if final_result_found:
                            # 重置当前部分状态，因为这是一个新的文本流
                            current_part_type = None
                            current_part_id = None
                            
                            async for output in request_stream.stream_text():
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
                                yield f'data: {json.dumps(data)}\n'
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
                                    yield f'data: {json.dumps(data)}\n'
                                    
                                    # 发送 tool-input-delta（如果有参数）
                                    if event.part.args:
                                        args_str = event.part.args_as_json_str()
                                        data = {
                                            "type": "tool-input-delta",
                                            "toolCallId": tool_call_id,
                                            "inputTextDelta": args_str
                                        }
                                        yield f'data: {json.dumps(data)}\n'
                                    
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
                                yield f'data: {json.dumps(data)}\n'
                            elif isinstance(event, FunctionToolResultEvent):
                                # 工具结果事件
                                data = {
                                    "type": "tool-output-available",
                                    "toolCallId": event.tool_call_id,
                                    "output": event.result.content
                                }
                                yield f'data: {json.dumps(data)}\n'
                elif Agent.is_end_node(node):
                    # 结束最后的部分（如果有的话）
                    end_event = end_current_part()
                    if end_event:
                        yield end_event
                    
                    # 结束节点 - agent 运行完成
                    data = {
                        "type": "finish"
                    }
                    yield f'data: {json.dumps(data)}\n'
                    yield 'data: [DONE]\n'
                    break
                else:
                    # 其他未处理的节点类型
                    logging.warning(f"Unhandled node type: {type(node)}")

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
            user_prompt = [msg['content'] for msg in messages if msg['role'] == 'user']
            if user_prompt == []:
                raise ValueError("User prompt is empty")
            response = agent.run_sync(
                user_prompt=user_prompt[0]
                # usage_limits=UsageLimits(response_tokens_limit=50),
            )
            return response.output
        except Exception as e:
            logger.error(f"Failed to get chat completion: {e}")
            raise ValueError("Failed to get chat completion")

# for testing
if __name__ == "__main__":
    from config import TEST_DB_PATH
    from sqlmodel import create_engine
    session = Session(create_engine(f'sqlite:///{TEST_DB_PATH}'))
    mgr = ModelsMgr(session)

    # # Test get TEXT model interface
    # model_interface = mgr.model_config_mgr.get_text_model_config()
    # print(model_interface.model_dump())
    
    import asyncio

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
    async def test_stream():
        messages = [
            {'role': 'user', 'content': 'What is the weather in Beijing?'}
        ]
        
        print('Testing Vercel AI SDK compatible stream protocol:')
        print('=' * 50)
        
        async for chunk in mgr.stream_agent_chat(messages, session_id=1):
            print(chunk, end='')
    
    asyncio.run(test_stream())
