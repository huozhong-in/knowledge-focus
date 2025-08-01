# from config import EMBEDDING_DIMENSIONS
from typing import List, Dict, Any
import logging
import json
import re
from sqlmodel import Session, select
from litellm import completion as litellm_completion, embedding as litellm_embedding
from pydantic import BaseModel, Field
import httpx

from db_mgr import SystemConfig, LocalModelProviderConfig
from bridge_events import BridgeEventSender

logger = logging.getLogger(__name__)

class TagResponse(BaseModel):
    tags: List[str] = Field(default_factory=list, description="List of generated tags")

class ModelsMgr:
    def __init__(self, session: Session):
        self.session = session
        # 初始化桥接事件发送器
        self.bridge_events = BridgeEventSender(source="models-manager")

    def _get_model_config(self, role_type: str, silent_validation: bool = False) -> tuple[str, str, str | None]:
        """
        Fetches the configuration for a given role and returns the necessary
        parameters for a litellm API call.

        Args:
            role_type: The role type (e.g., "base", "embedding")
            silent_validation: If True, model validation failures won't trigger IPC events
                              (useful for chat requests where frontend handles errors directly)

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

        # Verify that the model_id exists in the provider's model list
        try:
            available_models = self._get_available_models(provider_config.api_endpoint, provider_config.api_key)
            if not self._is_model_available(model_id, available_models):
                logger.warning(f"Model '{model_id}' not found in provider '{provider_type}' model list. "
                             f"Available models: {[m['id'] for m in available_models[:5]]}...")
                
                # 只在非静默模式下发送桥接事件 (主要用于后端主动处理场景)
                if not silent_validation:
                    self.bridge_events.model_validation_failed(
                        provider_type=provider_type,
                        model_id=model_id,
                        role_type=role_type,
                        available_models=[m.get("id", "") for m in available_models[:10]],
                        error_message=f"模型 '{model_id}' 在提供商 '{provider_type}' 中不可用"
                    )
                
                raise ValueError(f"Model '{model_id}' is not available in provider '{provider_type}'. "
                               f"Please check your {provider_type} configuration or update the model selection.")
        except Exception as e:
            if "not available in provider" in str(e):
                raise  # Re-raise model availability errors
            logger.warning(f"Could not verify model availability for {model_id} in {provider_type}: {e}")
            # Continue execution even if verification fails (network issues, etc.)

        return model_string, provider_config.api_endpoint, provider_config.api_key

    def _get_available_models(self, api_endpoint: str, api_key: str | None) -> List[Dict[str, Any]]:
        """
        Fetch available models from the provider's /v1/models endpoint.
        
        Returns:
            List of model dictionaries with 'id', 'object', 'owned_by' fields.
            Example format:
            [
                {
                    "id": "google/gemma-3-4b",
                    "object": "model",
                    "owned_by": "organization_owner"
                },
                ...
            ]
        """
        try:
            # Ensure the endpoint ends with /v1/models
            models_url = api_endpoint.rstrip('/') + '/v1/models'
            
            headers = {"Content-Type": "application/json"}
            if api_key and api_key != "dummy-key":
                headers["Authorization"] = f"Bearer {api_key}"
            
            with httpx.Client(timeout=10.0) as client:
                response = client.get(models_url, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                return data.get("data", [])
                
        except httpx.RequestError as e:
            logger.error(f"Network error when fetching models from {models_url}: {e}")
            raise ValueError(f"Could not connect to model provider at {api_endpoint}")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code} when fetching models from {models_url}")
            raise ValueError(f"Model provider returned error: {e.response.status_code}")
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Invalid response format from models endpoint: {e}")
            raise ValueError("Invalid response format from model provider")

    def _is_model_available(self, model_id: str, available_models: List[Dict[str, Any]]) -> bool:
        """
        Check if the specified model_id exists in the list of available models.
        
        Args:
            model_id: The model ID to check (e.g., "qwen/qwen3-30b-a3b-2507")
            available_models: List of model dictionaries from the provider
            
        Returns:
            True if the model is available, False otherwise
        """
        available_ids = [model.get("id", "") for model in available_models]
        return model_id in available_ids

    def get_embedding(self, text: str) -> List[float]:
        """
        Generates an embedding for the given text using litellm.
        
        This is typically called by backend processes (document parsing, vectorization),
        so model validation failures will trigger IPC events to notify the frontend.
        """
        try:
            model_string, api_base, api_key = self._get_model_config("embedding", silent_validation=False)
            response = litellm_embedding(
                model=model_string,
                input=[text],
                # dimensions=EMBEDDING_DIMENSIONS,
                api_base=api_base,
                api_key=api_key or "dummy-key"
            )
            return response.data[0]["embedding"]
        except Exception as e:
            logger.error(f"Failed to get embedding via litellm: {e}")
            return []

    def get_tags_from_llm(self, file_summary: str, candidate_tags: List[str]) -> List[str]:
        """
        Generates tags from the LLM using instructor and litellm.
        
        This is typically called by backend processes (file processing, tagging),
        so model validation failures will trigger IPC events to notify the frontend.
        """
        try:
            model_string, api_base, api_key = self._get_model_config("base", silent_validation=False)
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

    async def stream_chat(self, provider_type: str, model_name: str, messages: List[Dict[str, Any]]):
        """
        Streams a chat response from the specified model provider.
        
        Note: This method is typically called by frontend requests, so model validation
        errors will be returned as HTTP responses rather than IPC events.
        """
        provider_config = self.session.exec(
            select(LocalModelProviderConfig).where(LocalModelProviderConfig.provider_type == provider_type)
        ).first()

        if not provider_config or not provider_config.enabled:
            raise ValueError(f"Provider {provider_type} is not configured or not enabled.")

        model_string = f"{provider_type}/{model_name}"

        try:
            response = await litellm_completion(
                model=model_string,
                messages=messages,
                api_base=provider_config.api_endpoint,
                api_key=provider_config.api_key or "dummy-key",
                stream=True
            )

            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as e:
            logger.error(f"Error during chat streaming: {e}")
            yield f"Error: {str(e)}"

    def get_chat_completion(self, messages: List[Dict[str, Any]], role_type: str = "base") -> str:
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
            # For chat completions initiated by frontend, you might want to use:
            # model_string, api_base, api_key = self._get_model_config(role_type, silent_validation=True)
            model_string, api_base, api_key = self._get_model_config(role_type, silent_validation=False)
            
            response = litellm_completion(
                model=model_string,
                messages=messages,
                api_base=api_base,
                api_key=api_key or "dummy-key"
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Failed to get chat completion: {e}")
            raise  # Let the caller handle the error

    def validate_model_availability(self, provider_type: str, model_id: str) -> Dict[str, Any]:
        """
        Public method to validate if a model is available in the specified provider.
        
        Args:
            provider_type: The provider type (e.g., "ollama", "lm-studio")
            model_id: The model ID to validate
            
        Returns:
            Dictionary with validation results:
            {
                "is_available": bool,
                "error_message": str | None,
                "available_models": List[str] | None  # List of available model IDs
            }
        """
        try:
            provider_config = self.session.exec(
                select(LocalModelProviderConfig).where(LocalModelProviderConfig.provider_type == provider_type)
            ).first()

            if not provider_config or not provider_config.enabled:
                return {
                    "is_available": False,
                    "error_message": f"Provider {provider_type} is not configured or not enabled.",
                    "available_models": None
                }

            available_models = self._get_available_models(provider_config.api_endpoint, provider_config.api_key)
            is_available = self._is_model_available(model_id, available_models)
            
            if not is_available:
                # 发送桥接事件到前端
                self.bridge_events.model_validation_failed(
                    provider_type=provider_type,
                    model_id=model_id,
                    role_type="manual_validation",
                    available_models=[m.get("id", "") for m in available_models[:10]],
                    error_message=f"模型 '{model_id}' 在提供商 '{provider_type}' 中不可用"
                )
            
            return {
                "is_available": is_available,
                "error_message": None if is_available else f"Model '{model_id}' not found in provider '{provider_type}'",
                "available_models": [model.get("id", "") for model in available_models]
            }
            
        except Exception as e:
            logger.error(f"Error validating model availability: {e}")
            return {
                "is_available": False,
                "error_message": str(e),
                "available_models": None
            }
    
if __name__ == "__main__":
    # Example usage
    from config import TEST_DB_PATH
    from sqlmodel import create_engine
    session = Session(create_engine(f'sqlite:///{TEST_DB_PATH}'))
    mgr = ModelsMgr(session)
    
    # Test tag generation (backend processing - will send IPC events on failure)
    tags = mgr.get_tags_from_llm("北京是中国的首都，拥有丰富的历史和文化。", ["北京", "首都"])
    print("Generated Tags:", tags)
    
    # Test embedding generation (backend processing - will send IPC events on failure)
    len_embedding = mgr.get_embedding("北京是中国的首都，拥有丰富的历史和文化。")
    print("Embedding Length:", len(len_embedding))
    
    # Test manual model validation (will send IPC events on failure)
    validation_result = mgr.validate_model_availability("ollama", "qwen/qwen3-30b-a3b-2507")
    print("Model Validation Result:", validation_result)
    
    # Test chat completion (you can choose whether to send IPC events)
    try:
        chat_response = mgr.get_chat_completion([
            {"role": "user", "content": "Hello, how are you?"}
        ])
        print("Chat Response:", chat_response)
    except Exception as e:
        print("Chat Error:", e)
    