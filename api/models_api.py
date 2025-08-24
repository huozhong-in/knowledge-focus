from fastapi import APIRouter, Depends, Body
from fastapi.responses import StreamingResponse
from sqlmodel import Session
from typing import List, Dict, Any
import json
import uuid
import logging
from chatsession_mgr import ChatSessionMgr
from db_mgr import ModelCapability
from model_config_mgr import ModelConfigMgr
from models_mgr import ModelsMgr
from model_capability_confirm import ModelCapabilityConfirm
from pydantic import BaseModel

logger = logging.getLogger(__name__)

def get_router(external_get_session: callable) -> APIRouter:
    router = APIRouter()

    def get_model_config_manager(session: Session = Depends(external_get_session)) -> ModelConfigMgr:
        return ModelConfigMgr(session)
    
    def get_models_manager(session: Session = Depends(external_get_session)) -> ModelsMgr:
        return ModelsMgr(session)

    def get_model_capability_confirm(session: Session = Depends(external_get_session)) -> ModelCapabilityConfirm:
        return ModelCapabilityConfirm(session)

    def get_chat_session_manager(session: Session = Depends(external_get_session)) -> ChatSessionMgr:
        return ChatSessionMgr(session)

    @router.get("/models/providers", tags=["models"])
    def get_all_provider_configs(config_mgr: ModelConfigMgr = Depends(get_model_config_manager)):
        """获取所有本地模型服务商的配置"""
        try:
            configs = config_mgr.get_all_provider_configs()
            configs_data = [config.model_dump() for config in configs]
            return {"success": True, "data": configs_data}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.post("/models/providers", tags=["models"])
    def create_provider(data: Dict[str, Any] = Body(...), config_mgr: ModelConfigMgr = Depends(get_model_config_manager)):
        """创建新的模型提供商"""
        try:
            provider_type = data.get("provider_type", "")
            display_name = data.get("display_name", "")
            base_url = data.get("base_url", "")
            api_key = data.get("api_key", "")
            extra_data_json = data.get("extra_data_json", {})
            is_active = data.get("is_active", True)
            use_proxy = data.get("use_proxy", False)
            
            provider = config_mgr.create_provider(
                provider_type=provider_type,
                display_name=display_name,
                base_url=base_url,
                api_key=api_key,
                extra_data_json=extra_data_json,
                is_active=is_active,
                use_proxy=use_proxy
            )
            return {"success": True, "data": provider.model_dump()}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.delete("/models/provider/{id}", tags=["models"])
    def delete_provider(id: int, config_mgr: ModelConfigMgr = Depends(get_model_config_manager)):
        """删除模型提供商（仅限用户添加的提供商）"""
        try:
            success = config_mgr.delete_provider(provider_id=id)
            if success:
                return {"success": True, "message": "Provider deleted successfully"}
            else:
                return {"success": False, "message": "Cannot delete system provider or provider not found"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.put("/models/provider/{id}", tags=["models"])
    async def update_provider_config(id: int, data: Dict[str, Any] = Body(...), config_mgr: ModelConfigMgr = Depends(get_model_config_manager)):
        """更新指定服务商的配置"""
        try:
            provider_id = data.get("id", id)
            display_name = data.get("display_name", "")
            base_url = data.get("base_url", "")
            api_key = data.get("api_key", "")
            extra_data_json = data.get("extra_data_json", {})
            is_active = data.get("is_active", True)
            use_proxy = data.get("use_proxy", False)

            config = config_mgr.update_provider_config(
                id=provider_id, 
                display_name=display_name, 
                base_url=base_url, 
                api_key=api_key, 
                extra_data_json=extra_data_json, 
                is_active=is_active,
                use_proxy=use_proxy
            )
            if config:
                return {"success": True, "data": config.model_dump()}
            return {"success": False, "message": "Provider not found"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.post("/models/provider/{id}/discover", tags=["models"])
    async def discover_models_from_provider(id: int, config_mgr: ModelConfigMgr = Depends(get_model_config_manager)):
        """检测并更新服务商的可用模型"""
        try:
            config = await config_mgr.discover_models_from_provider(id=id)
            return {"success": True, "data": [model.model_dump() for model in config]}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.get("/models/provider/{id}", tags=["models"])
    def get_provider_models(id: int, config_mgr: ModelConfigMgr = Depends(get_model_config_manager)):
        """获取指定服务商的所有模型配置"""
        try:
            models = config_mgr.get_models_by_provider(provider_id=id)
            return {"success": True, "data": [model.model_dump() for model in models]}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.get("/models/capabilities", tags=["models"])
    def get_sorted_capability_names(mc_mgr: ModelCapabilityConfirm = Depends(get_model_capability_confirm)):
        """获取所有模型能力名称"""
        capabilities = mc_mgr.get_sorted_capability_names()
        return {"success": True, "data": capabilities}
    
    @router.get("/models/confirm_capability/{model_id}", tags=["models"])
    async def confirm_model_capability(model_id: int, mc_mgr: ModelCapabilityConfirm = Depends(get_model_capability_confirm)):
        """确认指定模型所有能力"""
        try:
            capability_dict = await mc_mgr.confirm_model_capability_dict(model_id, save_config=True)
            return {"success": True, "data": capability_dict}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.get("/models/global_capability/{model_capability}", tags=["models"])
    def get_model_for_global_capability(model_capability: str, config_mgr: ModelConfigMgr = Depends(get_model_config_manager)):
        """获取全局指定能力的模型分配"""
        try:
            capability = ModelCapability(model_capability)
            config = config_mgr.get_model_for_global_capability(capability)
            if config is not None:
                from sqlmodel import select
                from db_mgr import ModelProvider
                provider = config_mgr.session.exec(
                    select(ModelProvider).where(ModelProvider.id == config.provider_id)
                ).first()
                
                if provider:
                    provider_key = f"{provider.provider_type}-{provider.id}"
                    return {
                        "success": True, 
                        "data": {
                            "capability": model_capability,
                            "provider_key": provider_key,
                            "model_id": str(config.id)
                        }
                    }
                else:
                    return {"success": False, "message": "Provider not found"}
            else:
                return {"success": False, "message": "Model not found"}
        except ValueError:
            return {"success": False, "message": f"'{model_capability}' is not a valid ModelCapability"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    @router.post("/models/global_capability/{model_capability}", tags=["models"])
    def assign_global_capability_to_model(model_capability: str, data: Dict[str, Any] = Body(...), config_mgr: ModelConfigMgr = Depends(get_model_config_manager)):
        """指定某个模型为全局的ModelCapability某项能力"""
        try:
            model_id = data.get("model_id")
            if not model_id:
                return {"success": False, "message": "Missing model_id"}
            
            try:
                capability = ModelCapability(model_capability)
            except ValueError:
                return {"success": False, "message": f"'{model_capability}' is not a valid ModelCapability"}
            
            success = config_mgr.assign_global_capability_to_model(model_config_id=model_id, capability=capability)
            if success:
                return {"success": True}
            else:
                return {"success": False, "message": "Failed to set model for global capability"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @router.put("/models/model/{model_id}/toggle", tags=["models"])
    def toggle_model_enabled(model_id: int, data: Dict[str, Any] = Body(...), config_mgr: ModelConfigMgr = Depends(get_model_config_manager)):
        """切换模型的启用/禁用状态"""
        try:
            is_enabled = data.get("is_enabled")
            if is_enabled is None:
                return {"success": False, "message": "Missing is_enabled"}
            
            success = config_mgr.toggle_model_enabled(model_id=model_id, is_enabled=is_enabled)
            if success:
                return {"success": True, "message": "Model status updated successfully"}
            else:
                return {"success": False, "message": "Failed to update model status"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    class AgentChatRequest(BaseModel):
        messages: List[Dict[str, Any]]
        session_id: int

    @router.post("/chat/agent-stream", tags=["models"])
    async def agent_chat_stream(
        request: AgentChatRequest,
        models_mgr: ModelsMgr = Depends(get_models_manager),
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """
        Handles agentic chat sessions that require tools and session context.
        Streams responses according to the Vercel AI SDK v5 protocol.
        """
        async def stream_generator():
            # 1. 保存用户消息
            # Vercel AI SDK UI在每次请求时都会发送所有历史消息
            # 我们只保存最后一条用户消息
            last_user_message = None
            if request.messages and request.messages[-1].get("role") == "user":
                last_user_message = request.messages[-1]
                
            if last_user_message is None:
                # 如果没有找到用户消息，返回错误
                yield f"data: {json.dumps({'type': 'error', 'errorText': 'No user message found'})}\n\n"
                return

            # 提取用户消息内容
            content_text = last_user_message.get("content", "").strip()
            if not content_text:
                yield f"data: {json.dumps({'type': 'error', 'errorText': 'No user message content found'})}\n\n"
                return

            chat_mgr.save_message(
                session_id=request.session_id,
                message_id=last_user_message.get("id", str(uuid.uuid4())),  # 使用id而不是chatId
                role="user",
                content=content_text,
                # parts可以包含非文本内容，如图片，所以直接保存
                parts=last_user_message.get("parts") or [{"type": "text", "text": content_text}],
                metadata=last_user_message.get("metadata"),
                sources=last_user_message.get("sources")
            )

            # 2. 流式生成并保存助手消息
            assistant_message_id = f"asst_{uuid.uuid4().hex}"
            accumulated_parts = []  # 保存parts以便用户切换会话时能“恢复现场”，看到完整内容
            accumulated_text_content = ""  # 保存纯文本内容，便于搜索和摘要等文本处理

            try:
                # 直接转发stream_agent_chat的标准化SSE输出
                async for sse_chunk in models_mgr.stream_agent_chat(
                    messages=request.messages, 
                    session_id=request.session_id
                ):
                    # stream_agent_chat已经返回符合Vercel AI SDK v5标准的SSE格式
                    # 直接传递给前端，无需额外转换
                    yield sse_chunk
                    
                    # 解析SSE数据以便累积保存（用于持久化）
                    if sse_chunk.startswith('data: ') and not sse_chunk.strip().endswith('[DONE]'):
                        try:
                            sse_data = sse_chunk[6:].strip()  # 移除 'data: ' 前缀
                            if sse_data:
                                parsed_data = json.loads(sse_data)
                                accumulated_parts.append(parsed_data)
                                
                                # 累积文本内容用于保存
                                if parsed_data.get('type') == 'text-delta':
                                    accumulated_text_content += parsed_data.get('delta', '')
                        except json.JSONDecodeError:
                            # 忽略无法解析的数据行
                            pass

            except Exception as e:
                logger.error(f"Error in agent_chat_stream: {e}")
                # 发送标准错误事件
                error_event = f'data: {json.dumps({"type": "error", "errorText": str(e)})}\n'
                yield error_event
            
            finally:
                # 3. 在流结束后，将完整的助手消息（包含所有parts）持久化
                if accumulated_parts:
                    chat_mgr.save_message(
                        session_id=request.session_id,
                        message_id=assistant_message_id,
                        role="assistant",
                        content=accumulated_text_content.strip(),
                        parts=accumulated_parts
                    )
                    logger.info(f"Saved assistant message {assistant_message_id} with {len(accumulated_parts)} parts.")

        return StreamingResponse(
            stream_generator(), 
            media_type="text/event-stream",  # 标准SSE媒体类型
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "x-vercel-ai-ui-message-stream": "v1"
            }
        )

    return router