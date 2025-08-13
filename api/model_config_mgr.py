
import json
import httpx
from sqlmodel import Session, select
from typing import List, Tuple, Dict
from db_mgr import (
    # ModelSourceType, 
    ModelProvider, 
    ModelCapability, 
    ModelConfiguration, 
    CapabilityAssignment,
    SystemConfig,
)
import asyncio

class ModelConfigMgr:
    def __init__(self, session: Session):
        self.session = session

    def get_all_provider_configs(self) -> List[ModelProvider]:
        """Retrieves all model provider configurations from the database."""
        return self.session.exec(select(ModelProvider)).all()

    def update_provider_config(self, id: int, display_name: str, base_url: str, api_key: str, extra_data_json: Dict, is_active: bool) -> ModelProvider | None:
        """Updates a specific provider's configuration."""
        provider: ModelProvider = self.session.exec(select(ModelProvider).where(ModelProvider.id == id)).first()
        if provider is not None:
            provider.display_name = display_name if provider.is_user_added else None
            provider.base_url = base_url if provider.base_url != base_url else None
            provider.api_key = api_key if provider.api_key != api_key else None
            provider.extra_data = extra_data_json if provider.extra_data != extra_data_json else None
            provider.is_active = is_active if provider.is_active != is_active else None
            self.session.add(provider)
            self.session.commit()
            self.session.refresh(provider)
        return provider

    async def discover_models_from_provider(self, id: int) -> List[ModelConfiguration]:
        """Discovers available models from a provider."""

        def _already_exists(provider_id: int, model_identifier: str) -> bool:
            if model_identifier == "":
                print("Model identifier is empty.")
                return False
            return self.session.exec(select(ModelConfiguration).where(
                ModelConfiguration.provider_id == provider_id,
                ModelConfiguration.model_identifier == model_identifier
            )).first() is not None

        provider: ModelProvider = self.session.exec(select(ModelProvider).where(ModelProvider.id == id)).first()
        if provider is None:
            return []
        
        result: List[ModelConfiguration] = []
        headers = {}
        if provider.provider_type == "openai" or provider.provider_type == "grok":
            headers["Authorization"] = f"Bearer {provider.api_key}" if provider.api_key else ""
        elif provider.provider_type == "anthropic":
            headers["x-api-key"] = provider.api_key if provider.api_key else ""
            headers["anthropic-version"] = "2023-06-01"
        elif provider.provider_type == "google":
            headers["Content-Type"] = "application/json"
            headers["X-goog-api-key"] = provider.api_key if provider.api_key else ""
        elif provider.provider_type == "groq":
            headers["Content-Type"] = "application/json"
            headers["Authorization"] = f"Bearer {provider.api_key}" if provider.api_key else ""

        discover_url = f"{provider.base_url.rstrip('/')}/models"
        try:
            proxy = self.session.exec(select(SystemConfig).where(SystemConfig.key == "proxy")).first()
            async with httpx.AsyncClient(proxy=proxy.value if proxy is not None and provider.use_proxy else None) as client:
                response = await client.get(discover_url, headers=headers, timeout=10)
                response.raise_for_status()
                models_data = response.json()
        except (httpx.RequestError, json.JSONDecodeError) as e:
            print(f"Error discovering models for {id}: {e}")
            return []
        
        if provider.provider_type == "openai":
            if provider.display_name == "OpenAI":
                # https://platform.openai.com/docs/api-reference/models/list
                models_list = models_data.get("data", [])
                for model in models_list:
                    result.append(ModelConfiguration(
                        provider_id=id,
                        model_identifier=model.get("id", ""),
                        display_name=model.get("id", ""),
                    )) if not _already_exists(id, model.get("id", "")) else None
            elif provider.display_name == "OpenRouter":
                # https://openrouter.ai/docs/api-reference/list-available-models
                models_list = models_data.get("data", [])
                for model in models_list:
                    result.append(ModelConfiguration(
                        provider_id=id,
                        model_identifier=model.get("id", ""),
                        display_name=model.get("name", ""),
                        max_context_length=model.get("top_provider", {}).get("context_length", 0),
                        max_output_tokens=model.get("top_provider", {}).get("max_completion_tokens", 0),
                    )) if not _already_exists(id, model.get("id", "")) else None
            elif provider.display_name == "Ollama":
                # https://github.com/ollama/ollama/blob/main/docs/api.md#list-local-models
                models_list = models_data.get("models", [])
                for model in models_list:
                    result.append(ModelConfiguration(
                        provider_id=id,
                        model_identifier=model.get("model", ""),
                        display_name=model.get("name", ""),
                        # TODO POST /api/show to get context_length
                    )) if not _already_exists(id, model.get("model", "")) else None
            elif provider.display_name == "LM Studio":
                # https://lmstudio.ai/docs/app/api/endpoints/rest
                models_list = models_data.get("data", [])
                for model in models_list:
                    result.append(ModelConfiguration(
                        provider_id=id,
                        model_identifier=model.get("id", ""),
                        display_name=model.get("id", ""),
                        max_context_length=model.get("max_context_length", 0),
                        extra_data_json={"type": model.get("type", "")}
                    )) if not _already_exists(id, model.get("id", "")) else None
            else:
                return []
        
        elif provider.provider_type == "anthropic":
            # https://docs.anthropic.com/en/api/models-list
            models_list = models_data.get("data", [])
            for model in models_list:
                result.append(ModelConfiguration(
                    provider_id=id,
                    model_identifier=model.get("id", ""),
                    display_name=model.get("display_name", ""),
                )) if not _already_exists(id, model.get("id", "")) else None
        elif provider.provider_type == "google":
            # https://ai.google.dev/api/models
            models_list = models_data.get("models", [])
            for model in models_list:
                result.append(ModelConfiguration(
                    provider_id=id,
                    model_identifier=model.get("name", ""),
                    display_name=model.get("display_name", ""),
                    max_context_length=model.get("inputTokenLimit", 0) + model.get("outputTokenLimit", 0),
                    max_output_tokens=model.get("outputTokenLimit", 0),
                )) if not _already_exists(id, model.get("name", "")) else None
        elif provider.provider_type == "grok":
            # https://docs.x.ai/docs/api-reference#list-models
            models_list = models_data.get("data", [])
            for model in models_list:
                result.append(ModelConfiguration(
                    provider_id=id,
                    model_identifier=model.get("id", ""),
                    display_name=model.get("id", ""),
                )) if not _already_exists(id, model.get("id", "")) else None
        elif provider.provider_type == "groq":
            # https://console.groq.com/docs/models
            models_list = models_data.get("data", [])
            for model in models_list:
                result.append(ModelConfiguration(
                    provider_id=id,
                    model_identifier=model.get("id", ""),
                    display_name=model.get("id", ""),
                    max_context_length=model.get("context_window", 0),
                    max_output_tokens=model.get("max_completion_tokens", 0),
                )) if not _already_exists(id, model.get("id", "")) else None
        else:
            return []
        
        if result != []:
            self.session.add_all(result)
            self.session.commit()
        return result

    def get_model_capabilities(self, model_id: int) -> List[ModelCapability]:
        """获取指定模型的能力列表"""
        with self.session as session:
            model_config: ModelConfiguration = session.exec(
                select(ModelConfiguration).where(ModelConfiguration.id == model_id)
            ).first()
            if model_config is None:
                return []
            return [ModelCapability(value=cap) for cap in model_config.capabilities_json]

    def update_model_capabilities(self, model_id: int, capabilities: List[ModelCapability]) -> bool:
        """更新指定模型的能力列表"""
        with self.session as session:
            model_config: ModelConfiguration = session.exec(
                select(ModelConfiguration).where(ModelConfiguration.id == model_id)
            ).first()
            if model_config is None:
                return False
            
            capabilities_json = [capability.value for capability in capabilities]
            model_config.capabilities_json = capabilities_json
            session.commit()
            return True

    def assign_global_capability_to_model(self, model_config_id: int, capability: ModelCapability) -> bool:
        """指定某个模型为全局的ModelCapability某项能力"""
        with self.session as session:
            # 如果不存在就新增，否则更新
            assignment = session.exec(
                select(CapabilityAssignment).where(
                    CapabilityAssignment.capability_value == capability.value,
                )
            ).first()
            if assignment is None:
                assignment = CapabilityAssignment(
                    capability_value=capability.value,
                    model_configuration_id=model_config_id
                )
                session.add(assignment)
            else:
                assignment.model_configuration_id=model_config_id
            session.commit()
            return True

    def get_model_for_global_capability(self, capability: ModelCapability) -> ModelConfiguration | None:
        """获取全局指定ModelCapability能力的模型配置"""
        with self.session as session:
            assignment = session.exec(
                select(CapabilityAssignment).where(CapabilityAssignment.capability_value == capability.value)
            ).first()
            if assignment:
                return session.exec(
                    select(ModelConfiguration).where(ModelConfiguration.id == assignment.model_configuration_id)
                ).first()
        return None
    
    def get_spec_model_config(self, capability: ModelCapability) -> Tuple[str, str, str]:
        """取得全局指定能力的模型的model_identifier base_url api_key use_proxy"""
        model_config: ModelConfiguration = self.get_model_for_global_capability(capability)
        if model_config is None:
            raise ValueError(f"No configuration found for {capability} model")

        model_identifier = model_config.model_identifier
        model_provider: ModelProvider = self.session.exec(select(ModelProvider).where(ModelProvider.id == model_config.provider_id)).first()

        if model_provider is None:
            raise ValueError(f"No provider found for {capability} model")
        base_url = model_provider.base_url
        if base_url is None or base_url == "":
            raise ValueError(f"No base URL found for {capability} model")
        api_key = model_provider.api_key
        use_proxy = model_provider.use_proxy

        return model_identifier, base_url, api_key, use_proxy

    def get_vision_model_config(self) -> Tuple[str, str, str, bool]:
        """取得全局视觉模型的model_identifier base_url api_key use_proxy"""
        return self.get_spec_model_config(ModelCapability.VISION)

    def get_embedding_model_config(self) -> Tuple[str, str, str, bool]:
        """取得全局嵌入模型的model_identifier base_url api_key use_proxy"""
        return self.get_spec_model_config(ModelCapability.EMBEDDING)

    def get_text_model_config(self) -> Tuple[str, str, str, bool]:
        """取得全局文本模型的model_identifier base_url api_key use_proxy"""
        return self.get_spec_model_config(ModelCapability.TEXT)


if __name__ == "__main__":
    from sqlmodel import create_engine
    from config import TEST_DB_PATH

    # Initialize the session
    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
    with Session(engine) as session:
        mgr = ModelConfigMgr(session)

        list_model_provider: List[ModelProvider] = mgr.get_all_provider_configs()
        print({model_provider.id: model_provider.display_name for model_provider in list_model_provider})

        # # test pull models info from specific provider
        # asyncio.run(mgr.discover_models_from_provider(8))

        # test set global text model
        mgr.assign_global_capability_to_model(1, ModelCapability.TEXT)

        # test set global vision model
        mgr.assign_global_capability_to_model(2, ModelCapability.VISION)
        
        # test set global embedding model
        mgr.assign_global_capability_to_model(7, ModelCapability.EMBEDDING)

        # # test update_model_capabilities and get_model_capabilities
        # mgr.update_model_capabilities(1, [ModelCapability.TEXT, ModelCapability.TOOL_USE])
        # capabilities = mgr.get_model_capabilities(1)
        # print(capabilities)
        