# OpenAI 是使用tiktoken库做本地计数
# https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb

# Claude 是调用count_tokens API
# https://docs.anthropic.com/en/docs/build-with-claude/token-counting

# Google Gemini是调用count_tokens API
# https://ai.google.dev/gemini-api/docs/tokens?lang=python

from sqlmodel import Session, select
from sqlalchemy import Engine
from typing import List
from utils import num_tokens_from_string, num_tokens_from_messages
from db_mgr import ChatMessage
# from chatsession_mgr import ChatSessionMgr
# from model_config_mgr import ModelConfigMgr, ModelUseInterface
# from pydantic import BaseModel
from pydantic_ai import Tool, format_as_xml
import logging

logger = logging.getLogger()

class MemoryMgr:
    """记忆管理器"""
    def __init__(self, engine: Engine):
        self.engine = engine

    # 根据剩余token数，裁剪消息列表
    def trim_messages_to_fit(self, session_id: int, max_tokens: int) -> List[str]:
        """
        裁剪指定会话的消息列表，以适应剩余的token数

        Args:
            session_id: 会话ID
            max_tokens: 最大token数
        """
        limit: int = 20
        with Session(self.engine) as session:
            messages = session.exec(
                select(ChatMessage).where(ChatMessage.session_id == session_id).limit(limit)
            ).all()
            # 如果当前token数超过限制，则从最早开始裁剪消息
            while messages:
                # 计算当前消息列表的token数
                # 转换ChatMessage为符合OpenAI格式的字典，只包含role和content字段
                formatted_messages = []
                for msg in messages:
                    formatted_msg = {
                        "role": msg.role,
                        "content": msg.content if msg.content is not None else ""
                    }
                    formatted_messages.append(formatted_msg)
                
                current_tokens = num_tokens_from_messages(formatted_messages)
                print(f"当前消息数: {len(messages)}, 当前token数: {current_tokens}, 限制token数: {max_tokens}")
                if current_tokens > max_tokens:
                    # 从最早开始裁剪消息
                    messages.pop(0)
                else:
                    break
            # 历史消息内容清洗：用户消息前拼接'user:'，助手消息前拼接'assistant:'
            result = []
            for chat_msg in messages:
                if chat_msg.role == 'user':
                    result.append(f"user: {chat_msg.content}")
                elif chat_msg.role == 'assistant':
                    result.append(f"assistant: {chat_msg.content}")
            return result

    # 计算tools的token数
    def calculate_tools_tokens(self, tools: List[Tool]) -> int:
        result = 0
        for tool in tools:
            log = format_as_xml({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.function_schema.json_schema
            })
            # logger.info(log)
            result += num_tokens_from_string(log)
        return result

    # 计算字符串的token数
    def calculate_string_tokens(self, text: str) -> int:
        return num_tokens_from_string(text)

if __name__ == "__main__":
    from config import TEST_DB_PATH
    from sqlmodel import create_engine
    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
    mgr = MemoryMgr(engine)

    print(mgr.trim_messages_to_fit(1, 4096))