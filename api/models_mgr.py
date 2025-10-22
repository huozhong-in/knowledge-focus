from config import singleton, EMBEDDING_MODEL, VLM_MODEL
import os
import re
import json
import uuid
import time
from pathlib import Path
import logging
from typing import List, Dict, Any
from sqlalchemy import Engine
from pydantic import BaseModel, Field, ValidationError
from pydantic_ai import Agent, Tool, BinaryContent, RunContext, PromptedOutput, ModelSettings
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
from pydantic_ai.exceptions import UsageLimitExceeded
# from pydantic_ai.usage import UsageLimits
from model_config_mgr import ModelConfigMgr, ModelUseInterface
from tool_provider import ToolProvider
from memory_mgr import MemoryMgr
from bridge_events import BridgeEventSender
from huggingface_hub import snapshot_download
from tqdm import tqdm
from mlx_embeddings.utils import load as load_embedding_model
import mlx.core as mx

logger = logging.getLogger()

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
    def __init__(self, engine: Engine, base_dir: str):
        self.engine = engine
        self.base_dir = base_dir
        self.model_config_mgr = ModelConfigMgr(engine)
        self.tool_provider = ToolProvider(engine)
        self.memory_mgr = MemoryMgr(engine)
        self.bridge_events = BridgeEventSender(source="models-manager")

    def get_embedding(self, text_str: str) -> List[float]:
        """
        Generates an embedding for the given text using sync OpenAI client.
        
        This is typically called by backend processes (document parsing, vectorization),
        so model validation failures will trigger IPC events to notify the frontend.
        """
        model_path = self.model_config_mgr.get_embeddings_model_path()
        if model_path == "":
            model_path = self.download_huggingface_model(EMBEDDING_MODEL, self.base_dir)
            self.model_config_mgr.set_embeddings_model_path(model_path)        
        try:
            model, tokenizer = load_embedding_model(model_path)
            
            # 使用批处理编码并指定参数
            if hasattr(tokenizer, 'batch_encode_plus'):
                inputs = tokenizer.batch_encode_plus(
                    [text_str], 
                    return_tensors="mlx", 
                    padding=True, 
                    truncation=True, 
                    max_length=512
                )
                input_ids = inputs["input_ids"]
                attention_mask = inputs.get("attention_mask", None)
            else:
                input_ids = tokenizer.encode(text_str, return_tensors="mlx")
                attention_mask = None
                
            # 调用模型时提供attention_mask参数（如果可用）
            if attention_mask is not None:
                outputs = model(input_ids, attention_mask=attention_mask)
            else:
                outputs = model(input_ids)
                
            # raw_embeds = outputs.last_hidden_state[:, 0, :] # CLS token
            text_embeds = outputs.text_embeds # mean pooled and normalized embeddings
            return text_embeds[0].tolist()
        except Exception as e:
            logger.error(f"Error on load embedding model or generating embeddings: {e}")
            return []

    def get_tags_from_llm(self, file_path: str, file_summary: str, candidate_tags: List[str]) -> List[str]:
        """
        Generates tags from the LLM using instructor and litellm.
        
        This is typically called by backend processes (file processing, tagging),
        so model validation failures will trigger IPC events to notify the frontend.
        """

        class TagResponse(BaseModel):
            tags: List[str] = Field(default_factory=list, description="List of generated tags")
        
        try:
            model_interface: ModelUseInterface = self.model_config_mgr.get_structured_output_model_config()
        except Exception as e:
            logger.error(f"Failed to get structured output model config: {e}")
            return []
        model = self.model_config_mgr.model_adapter(model_interface)
        # System prompt 明确要求返回纯 JSON，不要 markdown 代码块
        system_prompt = """
You are an expert AI data curator for a desktop knowledge management app named "KnowledgeFocus". Your mission is to analyze file information and generate a refined, consistent, and structured set of tags that are optimized for future retrieval and organization.

# CRITICAL OUTPUT REQUIREMENT
YOU MUST ONLY OUTPUT RAW JSON WITHOUT ANY MARKDOWN CODE BLOCKS.
DO NOT wrap your response in ```json or ``` tags.
DO NOT include ANY explanatory text before or after the JSON.
ONLY output the JSON object itself.

# ABSOLUTELY CRITICAL TAG LIMITS
- You MUST generate EXACTLY 3 to 7 tags. NO MORE, NO LESS.
- NEVER repeat the same tag multiple times.
- Each tag must be UNIQUE and DISTINCT.

# CONTEXT PROVIDED

You will be given three pieces of information to perform your task:
1.  **File Path**: The full path to the file. This often contains invaluable context like project names, dates, or categories that may not be present in the content itself.
2.  **Content Summary**: The first few thousand characters of the file's text content.
3.  **Candidate Tags**: An AI-generated list of suggested tags based on vector similarity to other files. These are intelligent suggestions that require your expert review.

# CORE INSTRUCTIONS: Your Cognitive Workflow

You must follow this four-step cognitive process to arrive at the final, high-quality tags.

---

### Step 1: Holistic Analysis
First, synthesize your understanding by thoroughly examining BOTH the `File Path` and the `Content Summary`. Form a comprehensive mental model of what the file is about, its purpose, and its context.

---

### Step 2: Candidate Curation & Refinement (Crucial Step)
This is where your expertise shines. Scrutinize the `Candidate Tags` list not as a command, but as a draft needing an editor.

* **EVALUATE & SELECT**: For each candidate tag, determine if it accurately and importantly represents a core concept of the file.
* **MERGE & UNIFY**: If multiple candidates are semantically similar (e.g., synonyms, abbreviations, plural/singular forms like "Web Dev", "Web Development"), merge them into a single, most standard, and representative tag (e.g., `Web_Development`).
* **REFINE**: If a candidate is relevant but imprecise, refine it to be more specific or accurate based on the file's context. For example, a candidate "API" might be refined to "API_Design" if the content is about specifications.
* **DISCARD**: You MUST discard any candidate tags that are irrelevant, too generic, or redundant after merging.

---

### Step 3: Conceptual Creation
After curating the candidates, identify any core conceptual gaps. If a major theme or category of the file is still not represented, create 1 to 3 new, high-level tags to fill these gaps. These new tags should represent a significant aspect that the curated candidates missed.

---

### Step 4: Finalization & Formatting
Assemble the final list of tags from Step 2 and Step 3. Before outputting, ensure the list adheres to these strict final rules:

* **Quantity**: The final list must contain between 3 and 7 tags. NEVER MORE THAN 7 TAGS.
* **Uniqueness**: Each tag MUST be unique. NEVER repeat the same tag multiple times. Check for duplicates before finalizing.
* **Language & Terminology**:
    * The tag language MUST match the dominant language of the `Content Summary`.
    * If Chinese characters are present, all tags MUST be in Chinese.
    * Globally recognized technical acronyms (e.g., API, CPU, RAG, AI, LLM) MUST be preserved in their original English uppercase form, even within Chinese tags (e.g., `AI模型`, `RAG应用`).
* **Formatting**:
    * All multi-word English tags MUST use a single underscore `_` as a separator (e.g., `Project_Management`).
    * Hyphens `-` that are part of a word must be preserved (e.g., `Man-in-the-Loop`).
    * Absolutely NO generic tags like "File", "Document", "Text", "资料", "文档".
    * Ensure there are no leading/trailing spaces or punctuation around the tags.

# OUTPUT FORMAT

YOU MUST respond ONLY with raw JSON. NO MARKDOWN CODE BLOCKS.
Do not wrap your output in ```json or ```.
Do not include ANY explanatory text before or after the JSON.

**Example Input (User Prompt):**
* File Path: `/Users/Admin/Work/Project_KF/specs/2025-09-02_后端API设计草案.md`
* Content Summary: `# KF 后端 API 规范 (草案)... 主要实体是文件(Files), 标签(Tags)... 我们将使用 FastAPI...`
* Candidate Tags: `["API", "Knowledge-Focus", "Database", "草稿"]`

**Your Correct and ONLY Output (RAW JSON, NO MARKDOWN):**
{
  "tags": [
    "API设计",
    "Knowledge-Focus",
    "后端",
    "草稿"
  ]
}
""".strip()
        user_prompt = self._build_tagging_prompt(file_path, file_summary, candidate_tags)
        
        # 用于记录每次验证尝试的原始响应
        validation_attempts = []
        
        agent = Agent(
            model=model,
            system_prompt=system_prompt,
            # mlx_vlm加载模型使用 PromptedOutput 强制 prompt-based 模式，避免 tool calling
            output_type=PromptedOutput(TagResponse) if model_interface.model_identifier == VLM_MODEL else TagResponse,
            retries=3,  # 允许最多3次重试，给小模型更多纠错机会
        )
        
        # 添加输出验证器来记录原始响应
        @agent.output_validator
        async def log_validation_attempt(ctx: RunContext, result: TagResponse) -> TagResponse:
            """记录每次验证尝试，帮助调试"""
            validation_attempts.append({
                'attempt': len(validation_attempts) + 1,
                'tags': result.tags,
                'tags_count': len(result.tags)
            })
            logger.info(f"Validation attempt #{len(validation_attempts)}: Got {len(result.tags)} tags: {result.tags}")
            return result
        
        try:
            response = agent.run_sync(
                user_prompt=user_prompt,
                model_settings=ModelSettings(max_tokens=200),  # 限制标签生成的最大token数,防止重复生成
                # usage_limits=UsageLimits(output_tokens_limit=250), # 限制标签生成的最大token数，主要考虑thinking占用token
            )
            logger.info(f"Tag generation successful: {response.output.tags}")
        except UsageLimitExceeded as e:
            logger.error(f"Usage limit exceeded during tag generation: {e}")
            return []
        except ValidationError as e:
            logger.error(f"Validation error during tag generation: {e}")
            logger.error("This usually happens when the model output contains markdown code blocks or invalid JSON format")
            # 记录详细的验证错误信息
            import traceback
            logger.error(f"Validation details:\n{traceback.format_exc()}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error during tag generation: {e}")
            import traceback
            logger.error(f"Error details:\n{traceback.format_exc()}")
            # 记录所有验证尝试
            if validation_attempts:
                logger.error(f"Validation attempts made: {len(validation_attempts)}")
                for attempt in validation_attempts:
                    logger.error(f"  Attempt {attempt['attempt']}: {attempt['tags_count']} tags - {attempt['tags']}")
            else:
                logger.error("No validation attempts were recorded (model may not have returned valid JSON)")
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
        
        class SessionTitleResponse(BaseModel):
            title: str = Field(description="Generated session title (max 20 characters)")
        
        try:
            model_interface: ModelUseInterface = self.model_config_mgr.get_text_model_config()
    
        except Exception as e:
            logger.error(f"Failed to get model config: {e}")
            return "new chat"
        model = self.model_config_mgr.model_adapter(model_interface)
        messages = [
            {"role": "system", "content": "You are an expert at creating concise, meaningful titles. Generate a short title (max 20 characters) that captures the essence of the user's request or question."},
            {"role": "user", "content": self._build_title_prompt(first_message_content)}
        ]
        agent = Agent(
            model=model,
            system_prompt=messages[0]['content'],
            # mlx_vlm加载模型使用 PromptedOutput 强制 prompt-based 模式，避免 tool calling
            output_type=PromptedOutput(SessionTitleResponse) if model_interface.model_identifier == VLM_MODEL else SessionTitleResponse,
        )
        try:
            response = agent.run_sync(
                user_prompt=messages[1]['content'],
                # usage_limits=UsageLimits(output_tokens_limit=50),  # 限制生成的最大token数，确保简洁
            )
            title = response.output.title.strip()
            
            # 确保标题长度不超过20个字符
            if len(title) > 20:
                title = title[:17] + "..."
                
            return title if title else "new chat"

        except Exception as e:
            logger.error(f"Failed to generate session title: {e}")
            # 降级处理：使用简单截取方式
            fallback_title = first_message_content.strip()[:17]
            if len(first_message_content) > 17:
                fallback_title += "..."
            return fallback_title or "new chat"

    def _build_title_prompt(self, first_message: str) -> str:
        """Build prompt for session title generation"""
        return f'''
Please create a concise and meaningful title for a chat session based on the user's first message.

**Requirements:**
1. **Length:** Maximum 20 characters (including Chinese characters, English letters, numbers, and symbols)
2. **Language:** Use the same language as the user's message (Chinese for Chinese input, English for English input)
3. **Content:** Capture the main topic or intent of the user's question/request
4. **Style:** Clear, descriptive, and professional
5. **Special Cases:** For simple greetings like "你好", "hello", use generic titles like "新对话", "New chat"

**User's First Message:**
---
{first_message}
---

Generate a title that best represents what this conversation will be about. Avoid overly specific titles for vague or greeting-only messages.
        '''

    def _build_tagging_prompt(self, file_path: str, summary: str, candidates: List[str]) -> str:
        """
        Builds a clean and structured user prompt containing the raw data for the tagging task.
        The Agent's system_prompt contains all the instructions.
        """
        # Format candidates for clear presentation
        candidate_str = ", ".join(f'"{t}"' for t in candidates) if candidates else "None provided."
        
        # Use f-string with clear markers for the model to parse
        return f"""
    --- Contextual Information ---
    File Path: {file_path}

    --- Candidate Tags (Reuse these if possible) ---
    [{candidate_str}]

    --- File Content Summary to Analyze ---
    {summary}

    ---

    Based on all the provided information and your system instructions, generate the tags for this file.
    """

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
        except Exception as e:
            logger.error(f"Failed to get model config: {e}")
            return ""
        model = self.model_config_mgr.model_adapter(model_interface)
        try:
            system_prompt = [msg['content'] for msg in messages if msg['role'] == 'system']
            # logger.info(f"System prompt for chat completion: {system_prompt}")
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
                user_prompt=user_prompt_texts[0],
                # usage_limits=UsageLimits(output_tokens_limit=50),
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

            # 先预检查消息中是否包含图片，以确定使用哪种模型配置
            has_images = False
            for msg in messages:
                if msg['role'] == 'user' and "parts" in msg:
                    for part in msg["parts"]:
                        if part.get("type") == "file" and part.get("mediaType", "").startswith("image/"):
                            has_images = True
                            break
                if has_images:
                    break

            # 根据是否包含图片选择合适的模型配置
            if has_images:
                # logger.info("检测到图片消息，使用视觉模型配置")
                model_interface: ModelUseInterface = self.model_config_mgr.get_vision_model_config()
            else:
                # logger.info("纯文本消息，使用文本模型配置")
                model_interface: ModelUseInterface = self.model_config_mgr.get_text_model_config()
            
            if model_interface is None:
                error_msg = "can't use vision model" if has_images else "can't use text model"
                error_msg = f"{error_msg}, please check model configuration"
                logger.error(error_msg)
                yield f'data: {json.dumps({"type": "error", "errorText": error_msg})}\n\n'
                return
            
            max_context_length = model_interface.max_context_length if model_interface.max_context_length != 0 else 4096
            max_output_tokens = model_interface.max_output_tokens if model_interface.max_output_tokens != 0 else 1024
            
            model = self.model_config_mgr.model_adapter(model_interface)
            
            # 准备工具
            tools = [Tool(tool, takes_ctx=True) for tool in self.tool_provider.get_tools_for_session(session_id)]
            count_tokens_tools = self.memory_mgr.calculate_tools_tokens(tools)
            logger.info(f"当前工具数: {len(tools)}, tools token数: {count_tokens_tools}")
            
            # 构建系统prompt
            system_prompt = ["You are a helpful assistant."]
            # 加载场景相关的系统prompt
            scenario_system_prompt = self.tool_provider.get_session_scenario_system_prompt(session_id)
            system_prompt.append(scenario_system_prompt) if scenario_system_prompt is not None else None
            # 在系统提示词中描述工具用法
            if len(tools) > 0:
                system_prompt.append("Search Tavily for the given query and return the results.")
            count_tokens_system_prompt = self.memory_mgr.calculate_string_tokens("\n".join(system_prompt))
            logger.info(f"当前系统prompt token数: {count_tokens_system_prompt}")
            
            # 处理用户输入 - 兼容AI SDK v5的parts格式
            user_prompt: List[str] = []
            image_files: List[str] = []  # 存储图片文件路径
            for msg in messages:
                if msg['role'] == 'user':
                    # 优先从parts中提取文本内容和图片文件
                    content_text = ""
                    if "parts" in msg:
                        for part in msg["parts"]:
                            if part.get("type") == "text":
                                content_text += part.get("text", "")
                            elif part.get("type") == "file":
                                media_type = part.get("mediaType", "")
                                file_url = part.get("url", "")
                                filename = part.get("filename", "")
                                # 处理图片文件
                                if media_type.startswith("image/") and file_url:
                                    # 处理file://协议的本地文件路径
                                    if file_url.startswith("file://"):
                                        file_path = file_url[7:]  # 移除file://前缀
                                    else:
                                        file_path = file_url
                                    image_files.append(file_path)
                                    # logger.info(f'图片文件: {media_type} {filename} {file_path}')
                                else:
                                    logger.info(f'未知文件类型: {media_type} {filename} {file_url}')
                            else:
                                logger.info(f'Unknown part type: {part.get("type", "unknown")}')
                    # 备用：检查传统的content字段
                    if not content_text:
                        content_text = msg.get("content", "")
                    
                    if content_text.strip():
                        user_prompt.append(content_text.strip())
            
            if user_prompt == []:
                yield f'data: {"type": "error", "errorText": "User prompt is empty"}\n\n'
                return

            # 构建包含文本和图片的消息内容
            if image_files:
                # 如果有图片，需要构建多模态消息
                logger.info(f"处理 {len(image_files)} 个图片文件: {image_files}")
                
                # 构建pydantic-ai格式的用户输入 - 使用List[Any]支持BinaryContent
                user_prompt_multimodal: List[Any] = []
                
                # 添加文本内容
                if user_prompt != []:
                    user_prompt_multimodal.append("\n".join(user_prompt))
                
                # 添加图片内容
                for image_path in image_files:
                    try:
                        if os.path.exists(image_path):
                            # 获取文件扩展名来确定MIME类型
                            file_ext = Path(image_path).suffix.lower()
                            if file_ext in ['.jpg', '.jpeg']:
                                mime_type = 'image/jpeg'
                            elif file_ext == '.png':
                                mime_type = 'image/png'
                            elif file_ext == '.gif':
                                mime_type = 'image/gif'
                            elif file_ext == '.webp':
                                mime_type = 'image/webp'
                            else:
                                mime_type = 'image/png'  # 默认
                            
                            # 读取图片数据并创建BinaryContent
                            image_data = Path(image_path).read_bytes()
                            # TODO : 考虑图片大小限制
                            binary_content = BinaryContent(
                                data=image_data, 
                                media_type=mime_type
                            )
                            user_prompt_multimodal.append(binary_content)
                            # logger.info(f"成功添加图片: {image_path} ({len(image_data)} bytes, {mime_type})")
                        else:
                            logger.warning(f"图片文件不存在: {image_path}")
                    except Exception as e:
                        logger.error(f"读取图片文件失败: {image_path}, 错误: {e}")
                
                user_prompt_final = user_prompt_multimodal
            else:
                # 只有文本的情况，也用list保持一致
                user_prompt_final = user_prompt

            # # 输出日志，处理多模态情况
            # if isinstance(user_prompt_final, list):
            #     text_parts = [part for part in user_prompt_final if isinstance(part, str)]
            #     binary_parts = [part for part in user_prompt_final if hasattr(part, 'data')]
            #     logger.info(f"最终用户提示词: 文本部分({len(text_parts)})和图片部分({len(binary_parts)})")
            #     if text_parts:
            #         logger.info(f"文本内容: {' '.join(text_parts)[:200]}...")
            # else:
            #     logger.info(f"最终用户提示词: {user_prompt_final[:200]}...")  # 只显示前200字符

            count_tokens_user_prompt = self.memory_mgr.calculate_string_tokens("\n".join([prompt for prompt in user_prompt_final if isinstance(prompt, str)]))
            logger.info(f"当前用户prompt token数: {count_tokens_user_prompt}")
            
            # 留给会话历史记录的token数
            available_tokens = max_context_length - max_output_tokens - count_tokens_tools - count_tokens_system_prompt - count_tokens_user_prompt
            logger.info(f"当前可用历史消息token数: {available_tokens}")
            chat_history: List[str] = self.memory_mgr.trim_messages_to_fit(session_id, available_tokens)
            
            # RAG：将pin文件关联的知识片段召回并插到用户提示词上方
            user_query = "\n".join([prompt for prompt in user_prompt_final if isinstance(prompt, str)])  # 合并用户输入作为查询
            rag_context, rag_sources = self._get_rag_context(session_id, user_query, available_tokens)
            if rag_context:
                user_prompt_final = ["## 相关知识背景："] + [rag_context] + ['\n\n---\n\n'] + user_prompt_final
                logger.info(f"RAG检索到 {len(rag_sources)} 个相关片段")
                
                # 通过桥接器发送RAG数据到知识观察窗
                self._send_rag_to_observation_window(rag_sources, user_query)
            
            # 将会话历史记录插到用户提示词上方
            if chat_history != []:
                user_prompt_final = ["## 会话历史: "] + chat_history + ['\n\n---\n\n'] + user_prompt_final
            logger.info(f"当前用户提示词: {[prompt for prompt in user_prompt_final if isinstance(prompt, str)]}")
            
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

            # 使用 agent.iter() 方法来逐个输出流中每个节点
            async with agent.iter(user_prompt=user_prompt_final, deps=self.engine) as run:
                async for node in run:
                    # logger.info(f"Processing node type: {type(node)}")
                    if Agent.is_user_prompt_node(node):
                        # 用户输入节点 - 在v5协议中我们不需要发送user-prompt事件
                        # AI SDK v5协议中用户消息由前端直接处理，我们只处理AI响应
                        # logger.info(f"Processing user prompt node: {node.user_prompt}")
                        # 跳过，不发送事件
                        pass
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

    def download_huggingface_model(self, model_id: str, cache_dir: str = None) -> str:
        """
        下载指定的huggingface模型到本地
        
        Args:
            model_id: HuggingFace模型ID，如 'BAAI/bge-small-zh-v1.5'
            cache_dir: 缓存目录，默认使用HuggingFace默认目录
            
        Returns:
            str: 下载后的本地模型路径
            
        Raises:
            Exception: 下载过程中的其他错误
        """
        
        max_attempts_per_endpoint = 3
        endpoints = ['https://huggingface.co', 'https://hf-mirror.com']
        last_exception = None

        for endpoint in endpoints:
            for attempt in range(max_attempts_per_endpoint):
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
                        endpoint=endpoint, # 添加endpoint参数
                    )
                    # 发送完成事件
                    self.bridge_events.model_download_completed(
                        model_name=model_id,
                        local_path=local_path,
                        message=f"模型 {model_id} 下载完成"
                    )
                    return local_path
                except Exception as e:
                    last_exception = e
                    error_msg = f"下载模型失败 (尝试 {attempt + 1}/{max_attempts_per_endpoint}，镜像站: {endpoint}): {str(e)}"
                    logger.warning(f"下载模型 {model_id} 失败: {e}", exc_info=True)
                    # 发送失败事件，但不是最终失败，只是单次尝试失败
                    self.bridge_events.model_download_progress(
                        model_name=model_id,
                        current=0,
                        total=0,
                        message=f"下载失败 (尝试 {attempt + 1}/{max_attempts_per_endpoint}，镜像站: {endpoint})",
                        stage="failed_attempt"
                    )
                    time.sleep(2) # 等待2秒后重试

            logger.error(f"镜像站 {endpoint} 下载模型 {model_id} 失败，已达到最大重试次数 {max_attempts_per_endpoint}。")

        # 如果所有镜像站和所有尝试都失败了
        error_msg = f"所有镜像站下载模型 {model_id} 均失败: {str(last_exception)}"
        logger.error(error_msg, exc_info=True)
        # 发送最终失败事件
        self.bridge_events.model_download_failed(
            model_name=model_id,
            error_message=error_msg,
            details={"exception_type": type(last_exception).__name__ if last_exception else "UnknownError"}
        )            
        return ""

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
            chat_mgr = ChatSessionMgr(self.engine)
            document_ids = chat_mgr.get_pinned_document_ids(session_id)
            
            if not document_ids:
                logger.debug(f"会话 {session_id} 没有Pin文档，跳过RAG")
                return "", []
            
            # 使用SearchManager进行检索
            from lancedb_mgr import LanceDBMgr
            lancedb_mgr = LanceDBMgr(base_dir=self.base_dir)
            from search_mgr import SearchManager
            search_mgr = SearchManager(
                engine=self.engine, 
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

    def cosine_similarity_list_input(self, a: List[float], b: List[float]) -> float:
        """
        计算两个List[float]（向量）之间的余弦相似度。

        Args:
            a: 第一个输入列表（表示向量）。
            b: 第二个输入列表（表示向量）。

        Returns:
            一个浮点数，表示输入向量之间的余弦相似度。
            如果任一向量为零向量，则返回 0.0。
        """
        # 将 List[float] 转换为 mlx.core.array
        vec_a = mx.array(a)
        vec_b = mx.array(b)

        # 计算点积
        # mlx.core.sum(vec_a * vec_b) 会将所有元素相乘后求和，等同于向量点积
        dot_product = mx.sum(vec_a * vec_b)

        # 计算L2范数（magnitude）
        norm_a = mx.linalg.norm(vec_a)
        norm_b = mx.linalg.norm(vec_b)

        # 避免除以零：如果任一范数为零，则相似度为零
        denominator = norm_a * norm_b
        
        # 使用mx.where处理除以零的情况。
        # 如果denominator不为0，则执行 dot_product / denominator，否则返回0.0。
        # 由于我们期望返回一个浮点数，这里直接取其item()。
        # 注意：如果处理批量数据，通常不会用.item()。但对于两个单一向量，这是合适的。
        similarity = mx.where(denominator != 0, dot_product / denominator, mx.array(0.0)).item()
        
        return float(similarity)

    async def coreading_v5_compatible(self, messages: List[Dict], session_id: int):
        """
        [临时方案] 提供给“共读”模型的stream接口，兼容AI SDK v5协议。
        """
        try:
            model_interface: ModelUseInterface = self.model_config_mgr.get_vision_model_config()
            if model_interface is None:
                error_msg = "can't use vision model"
                logger.error(error_msg)
                yield f'data: {json.dumps({"type": "error", "errorText": error_msg})}\n\n'
                return
            
            max_context_length = model_interface.max_context_length if model_interface.max_context_length != 0 else 4096
            max_output_tokens = model_interface.max_output_tokens if model_interface.max_output_tokens != 0 else 1024
            
            model = self.model_config_mgr.model_adapter(model_interface)
            
            # 构建系统prompt
            system_prompt = self.tool_provider.get_session_scenario_system_prompt(session_id)
            count_tokens_system_prompt = self.memory_mgr.calculate_string_tokens("\n".join(system_prompt))
            logger.info(f"当前系统prompt token数: {count_tokens_system_prompt}")
            
            # 处理用户输入 - 兼容AI SDK v5的parts格式
            user_prompt: List[str] = []
            image_files: List[str] = []  # 存储图片文件路径
            for msg in messages:
                if msg['role'] == 'user':
                    # 优先从parts中提取文本内容和图片文件
                    content_text = ""
                    if "parts" in msg:
                        for part in msg["parts"]:
                            if part.get("type") == "text":
                                content_text += part.get("text", "")
                            elif part.get("type") == "file":
                                media_type = part.get("mediaType", "")
                                file_url = part.get("url", "")
                                filename = part.get("filename", "")
                                # 处理图片文件
                                if media_type.startswith("image/") and file_url:
                                    # 处理file://协议的本地文件路径
                                    if file_url.startswith("file://"):
                                        file_path = file_url[7:]  # 移除file://前缀
                                    else:
                                        file_path = file_url
                                    image_files.append(file_path)
                                    logger.info(f'图片文件: {media_type} {filename} {file_path}')
                                else:
                                    logger.info(f'未知文件类型: {media_type} {filename} {file_url}')
                            else:
                                logger.info(f'Unknown part type: {part.get("type", "unknown")}')
                    # 备用：检查传统的content字段
                    if not content_text:
                        content_text = msg.get("content", "")
                    
                    if content_text.strip():
                        user_prompt.append(content_text.strip())
            
            if user_prompt == []:
                yield f'data: {"type": "error", "errorText": "User prompt is empty"}\n\n'
                return

            # 共读模式有一至两张图片，构建多模态消息            
            # 构建pydantic-ai格式的用户输入 - 使用List[Any]支持BinaryContent
            user_prompt_multimodal: List[Any] = []
            
            # 添加文本内容
            if user_prompt:
                user_prompt_multimodal.append("\n".join(user_prompt))
            
            # 添加图片内容
            for image_path in image_files:
                try:
                    if os.path.exists(image_path):
                        # 获取文件扩展名来确定MIME类型
                        file_ext = Path(image_path).suffix.lower()
                        if file_ext in ['.jpg', '.jpeg']:
                            mime_type = 'image/jpeg'
                        elif file_ext == '.png':
                            mime_type = 'image/png'
                        elif file_ext == '.gif':
                            mime_type = 'image/gif'
                        elif file_ext == '.webp':
                            mime_type = 'image/webp'
                        else:
                            mime_type = 'image/png'  # 默认
                        
                        # 读取图片数据并创建BinaryContent
                        image_data = Path(image_path).read_bytes()
                        # TODO : 考虑图片大小限制
                        binary_content = BinaryContent(
                            identifier=os.path.basename(image_path),
                            data=image_data, 
                            media_type=mime_type
                        )
                        user_prompt_multimodal.append(binary_content)
                        # logger.info(f"成功添加图片: {image_path} ({len(image_data)} bytes, {mime_type})")
                    else:
                        logger.warning(f"图片文件不存在: {image_path}")
                except Exception as e:
                    logger.error(f"读取图片文件失败: {image_path}, 错误: {e}")
            
            user_prompt_final = user_prompt_multimodal
            
            count_tokens_user_prompt = self.memory_mgr.calculate_string_tokens("\n".join([prompt for prompt in user_prompt_final if isinstance(prompt, str)]))
            logger.info(f"当前用户prompt token数: {count_tokens_user_prompt}")
            
            # 留给会话历史记录的token数
            available_tokens = max_context_length - max_output_tokens - count_tokens_system_prompt - count_tokens_user_prompt
            logger.info(f"当前可用历史消息token数: {available_tokens}")
            chat_history: List[str] = self.memory_mgr.trim_messages_to_fit(session_id, available_tokens)
            
            # RAG：将pin文件关联的知识片段召回并插到用户提示词上方
            user_query = "\n".join([prompt for prompt in user_prompt_final if isinstance(prompt, str)])  # 合并用户输入作为查询
            rag_context, rag_sources = self._get_rag_context(session_id, user_query, available_tokens)
            if rag_context:
                user_prompt_final = ["## 相关知识背景："] + [rag_context] + ['\n\n---\n\n'] + user_prompt_final
                logger.info(f"RAG检索到 {len(rag_sources)} 个相关片段")
                
                # 通过桥接器发送RAG数据到知识观察窗
                self._send_rag_to_observation_window(rag_sources, user_query)
            
            # 将会话历史记录插到用户提示词上方
            if chat_history != []:
                user_prompt_final = ["## 会话历史: "] + chat_history + ['\n\n---\n\n'] + user_prompt_final
            logger.info(f"当前用户提示词: {[prompt for prompt in user_prompt_final if isinstance(prompt, str)]}")
            
            # 创建agent
            agent = Agent(
                model=model,
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

            # 使用 agent.iter() 方法来逐个输出流中每个节点
            async with agent.iter(user_prompt=user_prompt_final, deps=session_id) as run:
                async for node in run:
                    # logger.info(f"Processing node type: {type(node)}")
                    if Agent.is_user_prompt_node(node):
                        # 用户输入节点 - 在v5协议中我们不需要发送user-prompt事件
                        # AI SDK v5协议中用户消息由前端直接处理，我们只处理AI响应
                        # logger.info(f"Processing user prompt node: {node.user_prompt}")
                        # 跳过，不发送事件
                        pass
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
            logger.error(f"Error in coreading_v5_compatible: {e}")
            yield f'data: {json.dumps({"type": "error", "errorText": str(e)})}\n\n'

# for testing
if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        # format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(stream=sys.stdout)]
    )

    from config import TEST_DB_PATH
    from sqlmodel import create_engine
    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
    mgr = ModelsMgr(engine, base_dir=Path(TEST_DB_PATH).parent)

    # # Test get TEXT model interface
    # model_interface = mgr.model_config_mgr.get_text_model_config()
    # print(model_interface.model_dump())
    

    # Test embedding generation
    # embedding = mgr.get_embedding("北京是中国的首都，拥有丰富的历史和文化。")
    # print("Embedding Length:", len(embedding))
    
    # # Test tag generation
    # tags = mgr.get_tags_from_llm("北京是中国的首都，拥有丰富的历史和文化。", ["北京", "首都"])
    # print("Generated Tags:", tags)
        
    # # test generate title
    # title = mgr.generate_session_title('你好，我想了解一下人工智能的发展历史')
    # print('Generated title:', title)
    
    # Test chat completion
    try:
        chat_response = mgr.get_chat_completion([
            {"role": "user", "content": "尽量列举一些首都城市的名字"}
        ])
        print("Chat Response:", chat_response)
    except Exception as e:
        print("Chat Error:", e)

    # # test stream
    # import asyncio
    # async def test_stream():
    #     messages = [
    #         {'role': 'user', 'content': '今天的谷歌股价是多少？'}
    #     ]
        
    #     print('Testing Vercel AI SDK compatible stream protocol:')
    #     print('=' * 50)

    #     async for chunk in mgr.stream_agent_chat_v5_compatible(messages, session_id=1):
    #         # print(chunk, end='')
    #         try:
    #             print(json.dumps(json.loads(chunk.lstrip('data: ')), ensure_ascii=False), end='')
    #         except Exception as e:
    #             print(f"Error processing chunk: {e}")
    #             pass
    # asyncio.run(test_stream())

    # # 下载MLX优化的Qwen3 Embedding模型
    # import os
    # cache_dir = os.path.dirname(TEST_DB_PATH)
    # path = mgr.download_embedding_model(EMBEDDING_MODEL, cache_dir)
    # print(path)
    
    # # === RAG测试代码 ===
    # print("\n" + "="*50)
    # print("测试RAG检索结果和相似度计算")
    # print("="*50)
    
    # # 测试会话ID=18的RAG检索
    # session_id = 18
    # user_query = "Manus项目有哪些经验教训？"
    # available_tokens = 2000
    
    # print(f"测试查询: {user_query}")
    # print(f"会话ID: {session_id}")
    
    # try:
    #     rag_context, rag_sources = mgr._get_rag_context(session_id, user_query, available_tokens)
        
    #     print("\n检索结果:")
    #     print(f"- 上下文长度: {len(rag_context)} 字符")
    #     print(f"- 来源数量: {len(rag_sources)}")
        
    #     if rag_sources:
    #         print("\n详细来源信息:")
    #         for i, source in enumerate(rag_sources):
    #             print(f"\n[来源 {i+1}]")
    #             print(f"  文件: {source.get('file_path', 'Unknown')}")
    #             print(f"  相似度分数: {source.get('similarity_score', 0.0)}")
    #             print(f"  内容长度: {len(source.get('content', ''))}")
    #             print(f"  内容预览: {source.get('content', '')[:200]}...")
                
    #             # 如果有原始distance数据，也显示出来
    #             if 'raw_distance' in source:
    #                 print(f"  原始距离: {source.get('raw_distance')}")
        
    #     # 同时测试SearchManager的原始返回
    #     print("\n" + "-"*30)
    #     print("原始SearchManager返回数据:")
        
    #     from chatsession_mgr import ChatSessionMgr
    #     chat_mgr = ChatSessionMgr(engine)
    #     document_ids = chat_mgr.get_pinned_document_ids(session_id)
    #     print(f"Pin的文档ID: {document_ids}")
        
    #     if document_ids:
    #         from lancedb_mgr import LanceDBMgr
    #         from search_mgr import SearchManager
            
    #         lancedb_mgr = LanceDBMgr(base_dir=base_dir)

    #         search_mgr = SearchManager(
    #             engine=engine, 
    #             lancedb_mgr=lancedb_mgr, 
    #             models_mgr=mgr
    #         )
            
    #         search_response = search_mgr.search_documents(
    #             query=user_query,
    #             top_k=5,
    #             document_ids=document_ids
    #         )
            
    #         if search_response and search_response.get('success'):
    #             raw_results = search_response.get('raw_results', [])
    #             print(f"原始结果数量: {len(raw_results)}")
                
    #             if raw_results:
    #                 print(f"\n首个原始结果字段: {list(raw_results[0].keys())}")
                    
    #                 for i, result in enumerate(raw_results[:3]):  # 只显示前3个
    #                     print(f"\n[原始结果 {i+1}]")
    #                     print(f"  所有字段: {result}")
                        
    #                     distance = result.get('distance', 'N/A')
    #                     print(f"  原始distance: {distance}")
                        
    #                     # 使用相同的转换公式
    #                     if isinstance(distance, (int, float)):
    #                         similarity_score = max(0.0, min(1.0, 1.0 - (distance / 2.0)))
    #                         print(f"  转换后相似度: {similarity_score} ({similarity_score*100:.1f}%)")
    #         else:
    #             print(f"搜索失败: {search_response.get('error', '未知错误') if search_response else '无响应'}")
                
    # except Exception as e:
    #     print(f"RAG测试失败: {e}")
    #     import traceback
    #     traceback.print_exc()
