
import json
import logging
from sqlmodel import Session, select
from typing import List, Dict, Any, Optional
import httpx
from db_mgr import LocalModelConfig, ModelProviderType, SystemConfig

logger = logging.getLogger(__name__)

class LocalModelsManager:
    """管理本地大模型配置的业务逻辑"""

    def __init__(self, session: Session):
        self.session = session

    def get_all_configs(self) -> List[LocalModelConfig]:
        """获取所有本地模型服务商的配置"""
        return self.session.exec(select(LocalModelConfig)).all()

    def get_config_by_provider(self, provider_type: str) -> Optional[LocalModelConfig]:
        """根据服务商类型获取配置"""
        return self.session.exec(
            select(LocalModelConfig).where(LocalModelConfig.provider_type == provider_type)
        ).first()

    def update_config(self, provider_type: str, api_endpoint: str, api_key: str, enabled: bool) -> Optional[LocalModelConfig]:
        """更新服务商配置"""
        config = self.get_config_by_provider(provider_type)
        if config:
            config.api_endpoint = api_endpoint
            config.api_key = api_key
            config.enabled = enabled
            self.session.add(config)
            self.session.commit()
            self.session.refresh(config)
        return config

    async def discover_models(self, provider_type: str) -> Optional[LocalModelConfig]:
        """
        通过API检测并更新指定服务商的可用模型列表
        """
        config = self.get_config_by_provider(provider_type)
        if not config or not config.enabled or not config.api_endpoint:
            return None

        headers = {}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"

        models_list = []
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{config.api_endpoint.rstrip('/')}/models", headers=headers, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                
                # 根据API返回格式解析
                if "data" in data and isinstance(data["data"], list):
                    raw_models = data["data"]
                else:
                    raw_models = []

                for model_data in raw_models:
                    if isinstance(model_data, dict) and "id" in model_data:
                        models_list.append({
                            "id": model_data.get("id"),
                            "name": model_data.get("id"), # 默认使用ID作为name
                            "attributes": {
                                "vision": False,
                                "reasoning": True,
                                "networking": False,
                                "toolUse": False,
                                "embedding": True,
                                "reranking": False,
                            }
                        })
            
            config.available_models = models_list
            self.session.add(config)
            self.session.commit()
            self.session.refresh(config)
            return config
        except httpx.RequestError as e:
            # 网络或请求错误
            print(f"Error discovering models for {provider_type}: {e}")
            return None
        except Exception as e:
            # 其他错误
            print(f"An unexpected error occurred during model discovery for {provider_type}: {e}")
            return None

    def get_selected_model_for_role(self, role: str) -> Dict[str, Any]:
        """获取指定功能角色的已选模型"""
        key = f"selected_model_for_{role}"
        config = self.session.exec(select(SystemConfig).where(SystemConfig.key == key)).first()
        if config and config.value:
            try:
                return json.loads(config.value)
            except json.JSONDecodeError:
                return {}
        return {}

    def set_selected_model_for_role(self, role: str, model_info: Dict[str, Any]) -> bool:
        """设置指定功能角色的模型"""
        key = f"selected_model_for_{role}"
        logger.info(f"Attempting to set model for role: '{role}' with key: '{key}'")
        logger.info(f"Model info to save: {model_info}")

        config = self.session.exec(select(SystemConfig).where(SystemConfig.key == key)).first()
        
        if config:
            logger.info(f"Found config entry for key '{key}'. Updating value.")
            config.value = json.dumps(model_info)
            self.session.add(config)
            self.session.commit()
            logger.info(f"Successfully updated and committed model for role: '{role}'")
            return True
        else:
            logger.error(f"Could not find config entry for key '{key}'. Update failed.")
            return False

