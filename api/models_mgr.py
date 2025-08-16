# from config import EMBEDDING_DIMENSIONS
from config import singleton
from typing import List, Dict, Any
import re
import httpx
import asyncio
import logging
from sqlmodel import Session, select
from db_mgr import SystemConfig
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError
from pydantic_ai import Agent
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
        # 只在非静默模式下发送桥接事件 (主要用于后端主动处理场景)
        # if not silent_validation:
        #     self.bridge_events.model_validation_failed(
        #         provider_type=provider_type,
        #         model_id=model_id,
        #         role_type=role_type,
        #         available_models=[m.get("id", "") for m in available_models[:10]],
        #         error_message=f"模型 '{model_id}' 在提供商 '{provider_type}' 中不可用"
        #     )

    async def get_embedding(self, text_str: str) -> List[float]:
        """
        Generates an embedding for the given text using litellm.
        
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
        http_client = httpx.AsyncClient(proxy=proxy.value if proxy is not None and use_proxy else None)
        openai_client = AsyncOpenAI(
            api_key=api_key if api_key else "sk-xxx",
            base_url=base_url,
            max_retries=3,
            http_client=http_client,
        )
        response = await openai_client.embeddings.create(
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
                usage_limits=UsageLimits(response_tokens_limit=150), # 限制标签生成的最大token数
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
    
    # # Test embedding generation
    # embedding = asyncio.run(mgr.get_embedding("北京是中国的首都，拥有丰富的历史和文化。"))
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

    # test stream text
    async def test_stream():
        async for chunk in mgr.stream_chat([
            {"role": "user", "content": "尽量列举一些首都城市的名字"}
        ]):
            print(chunk, end='', flush=True)
        print()  # 添加换行
    
    asyncio.run(test_stream())
