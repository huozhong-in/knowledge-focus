
import json
import httpx
from sqlmodel import Session, select
from typing import List, Dict, Any, Tuple, Optional

from db_mgr import LocalModelProviderConfig, SystemConfig

class ModelConfigMgr:
    def __init__(self, session: Session):
        self.session = session

    def get_all_provider_configs(self) -> List[LocalModelProviderConfig]:
        """Retrieves all model provider configurations from the database."""
        return self.session.exec(select(LocalModelProviderConfig)).all()

    def update_provider_config(self, provider_type: str, api_endpoint: str, api_key: str, enabled: bool) -> Optional[LocalModelProviderConfig]:
        """Updates a specific provider's configuration."""
        config = self.session.exec(select(LocalModelProviderConfig).where(LocalModelProviderConfig.provider_type == provider_type)).first()
        if config:
            config.api_endpoint = api_endpoint
            config.api_key = api_key
            config.enabled = enabled
            self.session.add(config)
            self.session.commit()
            self.session.refresh(config)
        return config

    async def discover_and_update_models_for_provider(self, provider_type: str) -> Optional[LocalModelProviderConfig]:
        """Discovers available models from a provider and updates the database."""
        config = self.session.exec(select(LocalModelProviderConfig).where(LocalModelProviderConfig.provider_type == provider_type)).first()
        if not config or not config.enabled or not config.api_endpoint:
            return None

        headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{config.api_endpoint.rstrip('/')}/models", headers=headers, timeout=10)
                response.raise_for_status()
                models_data = response.json()
            
            # The data is often in a 'data' key
            models_list = models_data.get("data", models_data)
            
            available_models = [{"id": m["id"], "name": m.get("name", m["id"])} for m in models_list]
            
            config.available_models = available_models
            self.session.add(config)
            self.session.commit()
            self.session.refresh(config)
            return config
        except (httpx.RequestError, json.JSONDecodeError) as e:
            # Log the error properly in a real app
            print(f"Error discovering models for {provider_type}: {e}")
            return None

    def get_role_configs(self) -> Dict[str, Any]:
        """Gets the model assignments for all roles."""
        roles = ["base", "vision", "embedding", "reranking"]
        role_configs = {}
        for role in roles:
            key = f"selected_model_for_{role}"
            config_entry = self.session.exec(select(SystemConfig).where(SystemConfig.key == key)).first()
            if config_entry and config_entry.value and config_entry.value != 'null':
                try:
                    role_configs[role] = json.loads(config_entry.value)
                except json.JSONDecodeError:
                    role_configs[role] = {}
            else:
                role_configs[role] = {} # Default to empty object if no value or value is 'null'
        return role_configs

    def update_role_config(self, role_type: str, provider_type: str, model_id: str, model_name: str) -> Optional[SystemConfig]:
        """Updates the model assignment for a specific role."""
        key = f"selected_model_for_{role_type}"
        config_entry = self.session.exec(select(SystemConfig).where(SystemConfig.key == key)).first()
        
        value_to_store = json.dumps({
            "provider_type": provider_type,
            "model_id": model_id,
            "model_name": model_name
        })

        if config_entry:
            config_entry.value = value_to_store
        else:
            config_entry = SystemConfig(key=key, value=value_to_store)
        
        self.session.add(config_entry)
        self.session.commit()
        self.session.refresh(config_entry)
        return config_entry
    
    # 取得视觉模型的api_endpoint和model_id
    def get_vision_model_config(self) -> Tuple[str, str]:
        """Gets the configuration for the vision model."""
        # 获取视觉模型的角色配置
        key = "selected_model_for_vision"
        config_entry = self.session.exec(select(SystemConfig).where(SystemConfig.key == key)).first()
        
        if not config_entry or not config_entry.value or config_entry.value == 'null':
            raise ValueError("No configuration found for vision model")

        try:
            role_config = json.loads(config_entry.value)
            provider_type = role_config.get("provider_type")
            model_id = role_config.get("model_id")
        except (json.JSONDecodeError, AttributeError):
            raise ValueError("Invalid configuration format for vision model")

        if not provider_type or not model_id:
            raise ValueError("Incomplete configuration for vision model")

        # 获取提供商配置
        provider_config = self.session.exec(
            select(LocalModelProviderConfig).where(LocalModelProviderConfig.provider_type == provider_type)
        ).first()

        if not provider_config or not provider_config.enabled:
            raise ValueError(f"Provider {provider_type} is not configured or not enabled.")

        return provider_config.api_endpoint, model_id
        
    
if __name__ == "__main__":
    from sqlmodel import create_engine
    from config import TEST_DB_PATH

    # Initialize the session
    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
    with Session(engine) as session:
        mgr = ModelConfigMgr(session)
        print(mgr.get_vision_model_config())