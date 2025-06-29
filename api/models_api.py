
from fastapi import APIRouter, Depends, Body
from sqlmodel import Session
from typing import List, Dict, Any

from models_mgr import LocalModelsManager

def get_router(external_get_session):
    router = APIRouter()

    def get_models_manager(session: Session = Depends(external_get_session)) -> LocalModelsManager:
        return LocalModelsManager(session)

    @router.get("/local-models/configs", tags=["local-models"])
    def get_all_model_configs(models_mgr: LocalModelsManager = Depends(get_models_manager)):
        """获取所有本地模型服务商的配置"""
        try:
            configs = models_mgr.get_all_configs()
            # 将模型对象转换为可序列化的字典
            configs_data = [config.model_dump() for config in configs]
            return {"success": True, "data": configs_data}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.put("/local-models/configs/{provider_type}", tags=["local-models"])
    def update_model_config(provider_type: str, data: Dict[str, Any] = Body(...), models_mgr: LocalModelsManager = Depends(get_models_manager)):
        """更新指定服务商的配置"""
        try:
            api_endpoint = data.get("api_endpoint", "")
            api_key = data.get("api_key", "")
            enabled = data.get("enabled", True)
            
            config = models_mgr.update_config(provider_type, api_endpoint, api_key, enabled)
            if config:
                return {"success": True, "data": config.model_dump()}
            return {"success": False, "message": "Provider not found"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.post("/local-models/configs/{provider_type}/discover", tags=["local-models"])
    async def discover_provider_models(provider_type: str, models_mgr: LocalModelsManager = Depends(get_models_manager)):
        """检测并更新服务商的可用模型"""
        try:
            config = await models_mgr.discover_models(provider_type)
            if config:
                return {"success": True, "data": config.model_dump()}
            return {"success": False, "message": "Failed to discover models. Check API endpoint and key."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.get("/local-models/roles", tags=["local-models"])
    def get_model_roles(models_mgr: LocalModelsManager = Depends(get_models_manager)):
        """获取所有功能角色的模型选择"""
        try:
            roles = ["vision", "reasoning", "toolUse", "embedding", "reranking"]
            role_configs = {}
            for role in roles:
                role_configs[role] = models_mgr.get_selected_model_for_role(role)
            return {"success": True, "data": role_configs}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.put("/local-models/roles/{role}", tags=["local-models"])
    def set_model_for_role(role: str, model_info: Dict[str, Any] = Body(...), models_mgr: LocalModelsManager = Depends(get_models_manager)):
        """为指定功能角色选择模型"""
        try:
            success = models_mgr.set_selected_model_for_role(role, model_info)
            if success:
                return {"success": True, "message": f"Successfully assigned model for {role} role."}
            return {"success": False, "message": "Failed to set model for role."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    return router
