from fastapi import APIRouter, Depends, Body
from sqlmodel import Session
from typing import List, Dict, Any

from model_config_mgr import ModelConfigMgr

def get_router(external_get_session):
    router = APIRouter()

    def get_model_config_manager(session: Session = Depends(external_get_session)) -> ModelConfigMgr:
        return ModelConfigMgr(session)

    @router.get("/local-models/configs", tags=["local-models"])
    def get_all_model_configs(config_mgr: ModelConfigMgr = Depends(get_model_config_manager)):
        """获取所有本地模型服务商的配置"""
        try:
            configs = config_mgr.get_all_provider_configs()
            configs_data = [config.model_dump() for config in configs]
            return {"success": True, "data": configs_data}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.put("/local-models/configs/{provider_type}", tags=["local-models"])
    def update_model_config(provider_type: str, data: Dict[str, Any] = Body(...), config_mgr: ModelConfigMgr = Depends(get_model_config_manager)):
        """更新指定服务商的配置"""
        try:
            api_endpoint = data.get("api_endpoint", "")
            api_key = data.get("api_key", "")
            enabled = data.get("enabled", True)
            
            config = config_mgr.update_provider_config(provider_type, api_endpoint, api_key, enabled)
            if config:
                return {"success": True, "data": config.model_dump()}
            return {"success": False, "message": "Provider not found"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.post("/local-models/configs/{provider_type}/discover", tags=["local-models"])
    async def discover_provider_models(provider_type: str, config_mgr: ModelConfigMgr = Depends(get_model_config_manager)):
        """检测并更新服务商的可用模型"""
        try:
            config = await config_mgr.discover_and_update_models_for_provider(provider_type)
            if config:
                return {"success": True, "data": config.model_dump()}
            return {"success": False, "message": "Failed to discover models. Check API endpoint and key."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.get("/local-models/roles", tags=["local-models"])
    def get_role_configs(config_mgr: ModelConfigMgr = Depends(get_model_config_manager)):
        """获取所有角色的模型分配"""
        try:
            roles = config_mgr.get_role_configs()
            return {"success": True, "data": roles}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.put("/local-models/roles/{role_type}", tags=["local-models"])
    def update_role_config(
        role_type: str, 
        data: Dict[str, Any] = Body(...), 
        config_mgr: ModelConfigMgr = Depends(get_model_config_manager)
    ):
        """更新指定角色的模型配置"""
        try:
            provider_type = data.get("provider_type")
            model_id = data.get("model_id")
            model_name = data.get("model_name") # Frontend sends this now
            
            if not provider_type or not model_id or not model_name:
                return {"success": False, "message": "Missing required fields"}
            
            config = config_mgr.update_role_config(role_type, provider_type, model_id, model_name)
            if config:
                return {"success": True, "data": config.model_dump()}
            return {"success": False, "message": "Failed to update role config"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # 返回路由对象给主应用
    return router
