from config import singleton
import json
import httpx
from sqlmodel import Session, select
from sqlalchemy import Engine
from typing import List, Dict
from db_mgr import (
    # ModelSourceType, 
    ModelProvider, 
    ModelCapability, 
    ModelConfiguration, 
    CapabilityAssignment,
    SystemConfig,
)
from openai import AsyncOpenAI
from google.genai import Client
from google.genai.types import HttpOptions
from pydantic import BaseModel
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.groq import GroqProvider
from pydantic_ai.models.groq import GroqModel
import logging

logger = logging.getLogger()

class ModelUseInterface(BaseModel):
    model_identifier: str
    base_url: str
    api_key: str
    use_proxy: bool
    max_context_length: int
    max_output_tokens: int
    provider_type: str = "openai"

@singleton
class ModelConfigMgr:
    def __init__(self, engine: Engine):
        self.engine = engine

    def get_all_provider_configs(self) -> List[ModelProvider]:
        """Retrieves all model provider configurations from the database."""
        with Session(self.engine) as session:
            return session.exec(select(ModelProvider)).all()

    def get_models_by_provider(self, provider_id: int) -> List[ModelConfiguration]:
        """Retrieves all model configurations for a specific provider."""
        with Session(self.engine) as session:
            return session.exec(select(ModelConfiguration).where(ModelConfiguration.provider_id == provider_id)).all()

    def get_proxy_value(self) -> SystemConfig | None:
        with Session(self.engine) as session:
            return session.exec(select(SystemConfig).where(SystemConfig.key == "proxy")).first()

    def get_embeddings_model_path(self) -> str:
        with Session(self.engine) as session:
            embeddings_config = session.exec(select(SystemConfig).where(SystemConfig.key == "embeddings_model_path")).first()
            if embeddings_config is not None and embeddings_config.value is not None and embeddings_config.value != "":
                return embeddings_config.value
            return ""

    def set_embeddings_model_path(self, model_path: str) -> bool:
        with Session(self.engine) as session:
            embeddings_config = session.exec(select(SystemConfig).where(SystemConfig.key == "embeddings_model_path")).first()
            if embeddings_config is None:
                embeddings_config = SystemConfig(
                    key="embeddings_model_path", 
                    value=model_path,
                    description="Path to the built-in embeddings model file",
                )
                try:
                    session.add(embeddings_config)
                    session.commit()
                    return True
                except Exception as e:
                    logger.error(f"Failed to set embeddings model path: {e}")
                    return False
            else:
                embeddings_config.value = model_path
                try:
                    session.add(embeddings_config)
                    session.commit()
                    return True
                except Exception as e:
                    logger.error(f"Failed to update embeddings model path: {e}")
                    return False
        return False
    
    def create_provider(self, provider_type: str, display_name: str, base_url: str = "", api_key: str = "", extra_data_json: Dict = None, is_active: bool = True, use_proxy: bool = False) -> ModelProvider:
        """Creates a new model provider configuration."""
        if extra_data_json is None:
            extra_data_json = {}
        
        provider = ModelProvider(
            provider_type=provider_type,
            display_name=display_name,
            base_url=base_url,
            api_key=api_key,
            extra_data_json=extra_data_json,
            is_active=is_active,
            use_proxy=use_proxy,
            is_user_added=True  # 标记为用户添加的提供商
        )
        with Session(self.engine) as session:
            session.add(provider)
            session.commit()
            session.refresh(provider)
            return provider

    def delete_provider(self, provider_id: int) -> bool:
        """Deletes a provider and all its associated models."""
        try:
            # 先删除关联的模型配置
            with Session(self.engine) as session:
                models = session.exec(select(ModelConfiguration).where(ModelConfiguration.provider_id == provider_id)).all()
                for model in models:
                    session.delete(model)
                session.commit()
            
            # 删除提供商
            with Session(self.engine) as session:
                provider = session.exec(select(ModelProvider).where(ModelProvider.id == provider_id)).first()
                if provider and provider.is_user_added:  # 只允许删除用户添加的提供商
                    session.delete(provider)
                    session.commit()
                    return True
                return False
        except Exception as e:
            session.rollback()
            print(f"Error deleting provider {provider_id}: {e}")
            return False

    def update_provider_config(self, id: int, display_name: str, base_url: str, api_key: str, extra_data_json: Dict, is_active: bool, use_proxy: bool = False) -> ModelProvider | None:
        """Updates a specific provider's configuration."""
        with Session(self.engine) as session:
            provider: ModelProvider = session.exec(select(ModelProvider).where(ModelProvider.id == id)).first()
            if provider is not None:
                # 只有用户添加的提供商才能修改display_name
                if provider.is_user_added:
                    provider.display_name = display_name
                # 所有提供商都可以修改这些字段
                provider.base_url = base_url
                provider.api_key = api_key
                provider.extra_data_json = extra_data_json
                provider.is_active = is_active
                provider.use_proxy = use_proxy
                session.add(provider)
                session.commit()
                session.refresh(provider)
            return provider

    async def discover_models_from_provider(self, id: int) -> List[ModelConfiguration]:
        """Discovers available models from a provider."""

        def _already_exists(provider_id: int, model_identifier: str) -> bool:
            # 判断模型是否已经存在
            if model_identifier == "":
                print("Model identifier is empty.")
                return False
            # 也过滤掉embedding模型
            if "embedding" in model_identifier.lower():
                return True
            with Session(self.engine) as session:
                return session.exec(select(ModelConfiguration).where(
                    ModelConfiguration.provider_id == provider_id,
                    ModelConfiguration.model_identifier == model_identifier
                )).first() is not None

        with Session(self.engine) as session:
            provider: ModelProvider = session.exec(select(ModelProvider).where(ModelProvider.id == id)).first()
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
            # 如果provider的extra_data_json中包含discovery_api字段，则使用该字段作为发现模型的API地址
            try:
                extra_data = json.loads(provider.extra_data_json) if isinstance(provider.extra_data_json, str) else provider.extra_data_json
                if extra_data and "discovery_api" in extra_data:
                    discover_url = extra_data["discovery_api"]
            except Exception as e:
                print(f"Error reading discovery_api from extra_data_json: {e}")

            try:
                proxy = self.get_proxy_value()
                async with httpx.AsyncClient(proxy=proxy.value if proxy is not None and provider.use_proxy else None) as client:
                    response = await client.get(discover_url, headers=headers, timeout=10)
                    response.raise_for_status()
                    models_data = response.json()
            except (httpx.RequestError, json.JSONDecodeError) as e:
                print(f"Error discovering models for {id}: {e}")
                return []
            
            all_model_identifiers: List[str] = []  # 存放从API拉取回来的所有model_identifier
            if provider.provider_type == "openai":
                if provider.display_name == "OpenAI":
                    # https://platform.openai.com/docs/api-reference/models/list
                    models_list = models_data.get("data", [])
                    for model in models_list:
                        model_identifier=model.get("id", "")
                        all_model_identifiers.append(model_identifier)
                        result.append(ModelConfiguration(
                            provider_id=id,
                            model_identifier=model_identifier,
                            display_name=model_identifier,
                        )) if not _already_exists(id, model_identifier) else None
                elif provider.display_name == "OpenRouter":
                    # https://openrouter.ai/docs/api-reference/list-available-models
                    models_list = models_data.get("data", [])
                    for model in models_list:
                        model_identifier=model.get("id", "")
                        all_model_identifiers.append(model_identifier)
                        result.append(ModelConfiguration(
                            provider_id=id,
                            model_identifier=model_identifier,
                            display_name=model.get("name", ""),
                            max_context_length=model.get("top_provider", {}).get("context_length", 0),
                            max_output_tokens=model.get("top_provider", {}).get("max_completion_tokens", 0),
                        )) if not _already_exists(id, model_identifier) else None
                elif provider.display_name == "Ollama":
                    # https://github.com/ollama/ollama/blob/main/docs/api.md#list-local-models
                    models_list = models_data.get("models", [])
                    for model in models_list:
                        # https://github.com/ollama/ollama/blob/main/docs/api.md#show-model-information
                        # POST /api/show to get context_length:`curl http://localhost:11434/api/show -d '{"model": "llava"}'`
                        model_identifier=model.get("model", "")
                        all_model_identifiers.append(model_identifier)
                        max_content_length = 0
                        extra_data_json = {}
                        capabilities = []
                        try:
                            async with httpx.AsyncClient() as client:
                                response = await client.post("http://127.0.0.1:11434/api/show", json={"model": model_identifier})
                                response.raise_for_status()
                                model_data = response.json()
                                architecture = model_data.get("model_info", {}).get("general.architecture", "")
                                max_content_length = model_data.get("model_info", {}).get(f"{architecture}.context_length", 0)
                                extra_data_json = {"capabilities": model_data.get("capabilities", [])}
                                # 将"capabilities": ["completion","vision"] 转换为 ModelCapability.value 的列表
                                for cap in model_data.get("capabilities", []):
                                    if cap == "completion":
                                        capabilities.append(ModelCapability.TEXT.value)
                                    elif cap == "vision":
                                        capabilities.append(ModelCapability.VISION.value)
                        except Exception as e:
                            print(f"Error fetching model info for Ollama: {e}")
                        result.append(ModelConfiguration(
                            provider_id=id,
                            model_identifier=model_identifier,
                            display_name=model.get("name", ""),
                            max_context_length=max_content_length,
                            extra_data_json=extra_data_json,
                            capabilities_json=capabilities,
                        )) if not _already_exists(id, model_identifier) else None
                elif provider.display_name == "LM Studio":
                    # https://lmstudio.ai/docs/app/api/endpoints/rest
                    models_list = models_data.get("data", [])
                    for model in models_list:
                        model_identifier=model.get("id", "")
                        all_model_identifiers.append(model_identifier)
                        # 将type的值对应转换为ModelCapability.value的list
                        capabilities = []
                        type_name = model.get("type", "") # 已经发现的值有llm/vlm/embeddings
                        if type_name != '':
                            if type_name == "llm":
                                capabilities.append(ModelCapability.TEXT.value)
                            elif type_name == "vlm":
                                capabilities.append(ModelCapability.TEXT.value)
                                capabilities.append(ModelCapability.VISION.value)
                            # elif type_name == "embeddings":
                            #     capabilities.append(ModelCapability.EMBEDDING.value)
                            else:
                                pass
                        # LM Studio有一个额外的capabilities字段
                        if "tool_use" in model.get("capabilities", []):
                            capabilities.append(ModelCapability.TOOL_USE.value)
                        result.append(ModelConfiguration(
                            provider_id=id,
                            model_identifier=model_identifier,
                            display_name=model_identifier,
                            max_context_length=model.get("max_context_length", 0),
                            extra_data_json={"type": model.get("type", "")},
                            capabilities_json=capabilities,
                        )) if not _already_exists(id, model_identifier) else None
                else:
                    return []
            
            elif provider.provider_type == "anthropic":
                # https://docs.anthropic.com/en/api/models-list
                models_list = models_data.get("data", [])
                for model in models_list:
                    model_identifier=model.get("id", "")
                    all_model_identifiers.append(model_identifier)
                    result.append(ModelConfiguration(
                        provider_id=id,
                        model_identifier=model_identifier,
                        display_name=model.get("display_name", ""),
                    )) if not _already_exists(id, model_identifier) else None
            elif provider.provider_type == "google":
                # https://ai.google.dev/api/models
                models_list = models_data.get("models", [])
                for model in models_list:
                    model_identifier=model.get("name", "")
                    all_model_identifiers.append(model_identifier)
                    result.append(ModelConfiguration(
                        provider_id=id,
                        model_identifier=model_identifier,
                        display_name=model.get("display_name", ""),
                        max_context_length=model.get("inputTokenLimit", 0) + model.get("outputTokenLimit", 0),
                        max_output_tokens=model.get("outputTokenLimit", 0),
                    )) if not _already_exists(id, model_identifier) else None
            elif provider.provider_type == "grok":
                # https://docs.x.ai/docs/api-reference#list-models
                models_list = models_data.get("data", [])
                for model in models_list:
                    model_identifier=model.get("id", "")
                    all_model_identifiers.append(model_identifier)
                    result.append(ModelConfiguration(
                        provider_id=id,
                        model_identifier=model_identifier,
                        display_name=model_identifier,
                    )) if not _already_exists(id, model_identifier) else None
            elif provider.provider_type == "groq":
                # https://console.groq.com/docs/models
                models_list = models_data.get("data", [])
                for model in models_list:
                    model_identifier=model.get("id", "")
                    all_model_identifiers.append(model_identifier)
                    result.append(ModelConfiguration(
                        provider_id=id,
                        model_identifier=model_identifier,
                        display_name=model_identifier,
                        max_context_length=model.get("context_window", 0),
                        max_output_tokens=model.get("max_completion_tokens", 0),
                    )) if not _already_exists(id, model_identifier) else None
            else:
                return []

        if result != []:
            with Session(self.engine) as session:
                session.add_all(result)
                session.commit()
                # 刷新对象以获取数据库分配的 ID
                for model in result:
                    session.refresh(model)

        # API返回的结果中不再存在的模型从数据库删除
        with Session(self.engine) as session:
            models_to_delete = []
            for model in session.exec(select(ModelConfiguration).where(
                ModelConfiguration.provider_id == id,
            )).all():
                if model.model_identifier not in all_model_identifiers:
                    models_to_delete.append(model)

            # 批量删除并一次性提交
            if models_to_delete:
                # 先删除这些模型的能力分配记录（外键依赖）
                model_ids_to_delete = [model.id for model in models_to_delete]
                session.exec(
                    select(CapabilityAssignment).where(
                        CapabilityAssignment.model_configuration_id.in_(model_ids_to_delete)
                    )
                ).all()  # 需要先查询出来
                
                # 删除能力分配
                for assignment in session.exec(
                    select(CapabilityAssignment).where(
                        CapabilityAssignment.model_configuration_id.in_(model_ids_to_delete)
                    )
                ).all():
                    session.delete(assignment)
                
                # 再删除模型配置
                for model in models_to_delete:
                    session.delete(model)
                session.commit()
        
        return result

    def get_model_capabilities(self, model_id: int) -> List[ModelCapability]:
        """获取指定模型的能力列表"""
        with Session(self.engine) as session:
            model_config: ModelConfiguration = session.exec(
                select(ModelConfiguration).where(ModelConfiguration.id == model_id)
            ).first()
            if model_config is None:
                return []
            return [ModelCapability(value=cap) for cap in model_config.capabilities_json]

    def update_model_capabilities(self, model_id: int, capabilities: List[ModelCapability]) -> bool:
        """更新指定模型的能力列表"""
        with Session(self.engine) as session:
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
        with Session(self.engine) as session:
            if model_config_id == 0:
                # 如果model_config_id为0，表示取消该能力的全局模型配置
                assignment = session.exec(
                    select(CapabilityAssignment).where(
                        CapabilityAssignment.capability_value == capability.value,
                    )
                ).first()
                if assignment is not None:
                    session.delete(assignment)
                    session.commit()
                return True
            
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
        with Session(self.engine) as session:
            assignment = session.exec(
                select(CapabilityAssignment).where(CapabilityAssignment.capability_value == capability.value)
            ).first()
            if assignment:
                return session.exec(
                    select(ModelConfiguration).where(ModelConfiguration.id == assignment.model_configuration_id)
                ).first()
        return None
    
    def get_spec_model_config(self, capability: ModelCapability) -> ModelUseInterface | None:
        """取得全局指定能力的模型的model使用参数"""
        model_config: ModelConfiguration = self.get_model_for_global_capability(capability)
        if model_config is None:
            logger.info(f"No configuration found for {capability} model")
            return None

        model_identifier = model_config.model_identifier
        with Session(self.engine) as session:
            model_provider: ModelProvider = session.exec(select(ModelProvider).where(ModelProvider.id == model_config.provider_id)).first()

            if model_provider is None:
                logger.info(f"No provider found for {capability} model")
                return None
            base_url = model_provider.base_url
            if base_url is None or base_url == "":
                logger.info(f"No base URL found for {capability} model")
                return None
            api_key = model_provider.api_key
            use_proxy = model_provider.use_proxy
            provider_type = model_provider.provider_type

            return ModelUseInterface(
                model_identifier=model_identifier,
                base_url=base_url if base_url is not None else "",
                api_key=api_key if api_key is not None else "",
                use_proxy=use_proxy,
                max_context_length=model_config.max_context_length,
                max_output_tokens=model_config.max_output_tokens,
                provider_type=provider_type,
            )

    def get_vision_model_config(self) -> ModelUseInterface:
        """取得全局视觉模型的model使用参数"""
        return self.get_spec_model_config(ModelCapability.VISION)

    def get_text_model_config(self) -> ModelUseInterface:
        """取得全局文本模型的model使用参数"""
        return self.get_spec_model_config(ModelCapability.TEXT)

    def get_structured_output_model_config(self) -> ModelUseInterface:
        """取得全局结构化输出模型的model使用参数"""
        return self.get_spec_model_config(ModelCapability.STRUCTURED_OUTPUT)

    def toggle_model_enabled(self, model_id: int, is_enabled: bool) -> bool:
        """切换模型的启用/禁用状态"""
        with Session(self.engine) as session:
            try:
                model_config: ModelConfiguration = session.exec(
                    select(ModelConfiguration).where(ModelConfiguration.id == model_id)
                ).first()
                
                if model_config is None:
                    return False
                
                model_config.is_enabled = is_enabled
                session.add(model_config)
                session.commit()
                session.refresh(model_config)
                return True
            except Exception as e:
                session.rollback()
                print(f"Error toggling model enabled state for model {model_id}: {e}")
                return False

    def model_adapter(self, model_interface: ModelUseInterface) -> Model | None:
        model_identifier = model_interface.model_identifier
        base_url = model_interface.base_url
        api_key = model_interface.api_key
        use_proxy = model_interface.use_proxy
        proxy = self.get_proxy_value()
        http_client = httpx.AsyncClient(proxy=proxy.value if proxy is not None and use_proxy else None)
        provider_type = model_interface.provider_type
        
        if provider_type == "openai" or provider_type == "grok":
            openai_client = AsyncOpenAI(
                api_key=api_key if api_key else "sk-xxx",
                base_url=base_url,
                max_retries=3,
                http_client=http_client,
            )
            model = OpenAIChatModel(
                model_name=model_identifier,
                provider=OpenAIProvider(
                    openai_client=openai_client,
                ),
            )
        elif provider_type == "anthropic":
            model = AnthropicModel(
                model_name=model_identifier,
                provider=AnthropicProvider(
                    api_key=api_key,
                    http_client=http_client
                ),
            )
        elif provider_type == "google":
            client_args = {'proxy': proxy.value} if use_proxy and proxy is not None else None
            async_client_args = {'proxy': proxy.value} if use_proxy and proxy is not None else None
            http_options = HttpOptions(client_args=client_args, async_client_args=async_client_args) if client_args and async_client_args else None
            client = Client(
                api_key=api_key,
                http_options=http_options,
            )
            provider = GoogleProvider(client=client)
            model = GoogleModel(
                model_name=model_identifier, 
                provider=provider,
            )
        elif provider_type == "groq":
            model = GroqModel(
                model_name=model_identifier,
                provider=GroqProvider(
                    api_key=api_key,
                    http_client=http_client
                ),
            )
        else:
            return None
        
        return model

if __name__ == "__main__":
    from sqlmodel import create_engine
    from config import TEST_DB_PATH

    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
    mgr = ModelConfigMgr(engine=engine)

    list_model_provider: List[ModelProvider] = mgr.get_all_provider_configs()
    print({model_provider.id: model_provider.display_name for model_provider in list_model_provider})

    # test pull models info from specific provider
    import asyncio
    asyncio.run(mgr.discover_models_from_provider(8))

    # # test set global text model
    # mgr.assign_global_capability_to_model(1, ModelCapability.TEXT)

    # # test set global vision model
    # mgr.assign_global_capability_to_model(2, ModelCapability.VISION)
    
    # # test update_model_capabilities and get_model_capabilities
    # mgr.update_model_capabilities(1, [ModelCapability.TEXT, ModelCapability.TOOL_USE])
    # capabilities = mgr.get_model_capabilities(1)
    # print(capabilities)
        