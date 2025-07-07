from config import EMBEDDING_DIMENSIONS
from typing import List, Dict, Any, Optional
import logging
import json
import re
from sqlmodel import Session, select
from litellm import completion as litellm_completion, embedding as litellm_embedding
from pydantic import BaseModel, Field

from db_mgr import SystemConfig, LocalModelProviderConfig

logger = logging.getLogger(__name__)

class TagResponse(BaseModel):
    tags: List[str] = Field(default_factory=list, description="List of generated tags")

class ModelsMgr:
    def __init__(self, session: Session):
        self.session = session

    def _get_model_config(self, role_type: str) -> tuple[str, str, Optional[str]]:
        """
        Fetches the configuration for a given role and returns the necessary
        parameters for a litellm API call.

        Returns:
            A tuple containing (model_string, api_base, api_key).
            The model_string is in the format litellm expects (e.g., 'ollama/llama3').
        """
        key = f"selected_model_for_{role_type}"
        config_entry = self.session.exec(select(SystemConfig).where(SystemConfig.key == key)).first()
        
        if not config_entry or not config_entry.value or config_entry.value == 'null':
            raise ValueError(f"No configuration found for role: {role_type}")

        try:
            role_config = json.loads(config_entry.value)
            provider_type = role_config.get("provider_type")
            model_id = role_config.get("model_id")
        except (json.JSONDecodeError, AttributeError):
            raise ValueError(f"Invalid configuration format for role: {role_type}")

        if not provider_type or not model_id:
            raise ValueError(f"Incomplete configuration for role: {role_type}")

        provider_config = self.session.exec(
            select(LocalModelProviderConfig).where(LocalModelProviderConfig.provider_type == provider_type)
        ).first()

        if not provider_config or not provider_config.enabled:
            raise ValueError(f"Provider {provider_type} is not configured or not enabled.")

        # Construct the model string for litellm (e.g., "ollama/llama3")
        model_string = f"{provider_type}/{model_id}"

        return model_string, provider_config.api_endpoint, provider_config.api_key

    def get_embedding(self, text: str) -> List[float]:
        """Generates an embedding for the given text using litellm."""
        try:
            model_string, api_base, api_key = self._get_model_config("embedding")
            response = litellm_embedding(
                model=model_string,
                input=[text],
                api_base=api_base,
                api_key=api_key or "dummy-key"
            )
            return response.data[0]["embedding"]
        except Exception as e:
            logger.error(f"Failed to get embedding via litellm: {e}")
            return []

    def get_tags_from_llm(self, file_summary: str, candidate_tags: List[str]) -> List[str]:
        """Generates tags from the LLM using instructor and litellm."""
        try:
            model_string, api_base, api_key = self._get_model_config("base")
            messages = [
                {"role": "system", "content": "You are a world-class librarian. Your task is to analyze the provided text and generate a list of relevant tags. Adhere strictly to the format required."},
                {"role": "user", "content": self._build_user_prompt(file_summary, candidate_tags)}
            ]
            # messages[-1]['content'] += ' /no_think'
            response = litellm_completion(
                model=model_string,
                base_url=api_base,
                api_key=api_key or "dummy-key",
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "type": "object",
                        "name": "TagResponse",
                        "schema": TagResponse.model_json_schema()
                    }
                }
            )
            tags = json.loads(response.choices[0].message.content).get("tags", [])

            # # 把每个tag中间可能的空格替换为下划线，因为要避开英语中用连字符作为合成词的情况
            tags = [tag.replace(" ", "_") for tag in tags]
            # # 把每个tag前后的非字母数字字符去掉
            tags = [re.sub(r"^[^\w]+|[^\w]+$", "", tag) for tag in tags]
            return tags

        except Exception as e:
            logger.error(f"Failed to get tags from LLM: {e}")
            return []

    def _build_user_prompt(self, summary: str, candidates: List[str]) -> str:
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
    
if __name__ == "__main__":
    # Example usage
    db_file = "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db"
    from sqlmodel import create_engine
    session = Session(create_engine(f'sqlite:///{db_file}'))
    mgr = ModelsMgr(session)
    tags = mgr.get_tags_from_llm("北京是中国的首都，拥有丰富的历史和文化。", ["北京", "首都"])
    print("Generated Tags:", tags)
    len_embedding = mgr.get_embedding("北京是中国的首都，拥有丰富的历史和文化。")
    print("Embedding Length:", len(len_embedding))
    