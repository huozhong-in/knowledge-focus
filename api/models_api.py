from fastapi import APIRouter, Depends, Body, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session
from typing import Dict, Any
import json
import uuid
from chatsession_mgr import ChatSessionMgr
from db_mgr import ModelCapability
from model_config_mgr import ModelConfigMgr
from models_mgr import ModelsMgr
from model_capability_confirm import ModelCapabilityConfirm

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
            provider_id = data.get("id", id)  # 使用路径参数作为默认值
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
            # config 是 List[ModelConfiguration]，空列表也是有效结果
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
            # 验证能力值是否有效
            capability = ModelCapability(model_capability)
            config = config_mgr.get_model_for_global_capability(capability)
            if config is not None:
                # 获取提供商信息以构建provider_key
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
            
            # 验证能力值是否有效
            try:
                capability = ModelCapability(model_capability)  # 直接传递字符串值
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

    @router.post("/chat/stream", tags=["models"])
    async def chat_stream(
        request_data: Dict[str, Any] = Body(...),
        models_mgr: ModelsMgr = Depends(get_models_manager)
    ):
        """处理聊天流式请求"""
        try:
            messages = request_data.get("messages", [])
            # 可选：会话ID（用于持久化）；未提供则仅流式返回不落库
            _session_id: int | None = request_data.get("session_id")
            model_config = request_data.get("model_config", {})

            if not messages or not model_config:
                raise HTTPException(status_code=400, detail="Missing messages or model_config")

            provider_type = model_config.get("provider_type")
            model_name = model_config.get("model_name")

            if not provider_type or not model_name:
                raise HTTPException(status_code=400, detail="Missing provider_type or model_name in model_config")

            return StreamingResponse(
                models_mgr.stream_chat(
                    messages=messages
                ),
                media_type="text/event-stream"
            )
        except Exception as e:
            # Log the exception for debugging
            print(f"Error in chat_stream: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/chat/ui-stream", tags=["models"])
    async def chat_ui_stream(
        request_data: Dict[str, Any] = Body(...),
        models_mgr: ModelsMgr = Depends(get_models_manager),
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """
        处理AI SDK v5格式的聊天流式请求
        兼容UIMessage格式，返回SSE事件流
        """
        try:
            # 解析AI SDK v5格式的请求
            _trigger = request_data.get("trigger", "submit-message")
            _chat_id = request_data.get("chatId", str(uuid.uuid4()))
            _message_id = request_data.get("messageId")
            messages = request_data.get("messages", [])
            session_id: int | None = request_data.get("session_id")

            if not messages:
                raise HTTPException(status_code=400, detail="Missing messages")

            # 若提供了session_id，则在流式生成前持久化本次请求中的最新一条用户消息
            if session_id and messages:
                # 找到最后一条 user 角色的消息（通常就是本次输入）
                last_user_msg = None
                for m in reversed(messages):
                    if m.get("role") == "user":
                        last_user_msg = m
                        break
                        
                if last_user_msg is not None:
                    try:
                        if "parts" in last_user_msg:
                            # 提取text类型的parts
                            text_parts = [part.get("text", "") for part in last_user_msg.get("parts", []) if part.get("type") == "text"]
                            content_text = " ".join(text_parts) if text_parts else ""
                            ui_parts = last_user_msg.get("parts", [])
                        else:
                            content_text = last_user_msg.get("content", "")
                            ui_parts = [{"type": "text", "text": content_text}]

                        # 使用ChatSessionMgr保存用户消息
                        chat_mgr.save_message(
                            session_id=session_id,
                            message_id=str(uuid.uuid4()),
                            role="user",
                            content=content_text,
                            parts=ui_parts,
                            metadata=last_user_msg.get("metadata"),
                            sources=last_user_msg.get("sources")
                        )
                        print(f"[DEBUG] Persisted user message for session {session_id}")
                    except Exception as user_persist_err:
                        print(f"[WARN] Failed to persist user message: {user_persist_err}")

            # 转换UIMessage格式到标准消息格式（等价于ModelMessage）
            converted_messages = []
            for msg in messages:
                if "parts" in msg:
                    # 提取text类型的parts
                    text_parts = [part.get("text", "") for part in msg.get("parts", []) if part.get("type") == "text"]
                    content = " ".join(text_parts) if text_parts else ""
                else:
                    content = msg.get("content", "")

                converted_messages.append({
                    "role": msg.get("role", "user"),
                    "content": content
                })

            async def generate_ui_stream():
                """生成AI SDK v5兼容的SSE流"""
                try:
                    response_id = str(uuid.uuid4())
                    accumulated_text = ""

                    # 发送消息开始事件 - AI SDK标准格式
                    yield f"data: {json.dumps({'type': 'start', 'messageId': response_id})}\n\n"

                    # 发送文本开始事件
                    yield f"data: {json.dumps({'type': 'text-start', 'id': response_id})}\n\n"

                    # 调用现有的stream_chat方法
                    print("[DEBUG] Starting stream_chat")
                    chunk_count = 0
                    async for content_chunk in models_mgr.stream_chat(
                        messages=converted_messages
                    ):
                        chunk_count += 1
                        print(f"[DEBUG] Received chunk {chunk_count}: '{content_chunk[:50]}...'")

                        if content_chunk and not content_chunk.startswith("Error:"):
                            # 发送文本增量事件
                            ui_chunk = {
                                "type": "text-delta",
                                "delta": content_chunk,
                                "id": f"msg_{uuid.uuid4().hex}"
                            }
                            chunk_data = f"data: {json.dumps(ui_chunk)}\n\n"
                            print(f"[DEBUG] Sending chunk: {chunk_data}")
                            yield chunk_data
                            accumulated_text += content_chunk
                        elif content_chunk.startswith("Error:"):
                            # 发送错误事件
                            error_chunk = {
                                "type": "error",
                                "errorText": content_chunk
                            }
                            yield f"data: {json.dumps(error_chunk)}\n\n"
                            break

                    print(f"[DEBUG] Stream completed, sent {chunk_count} chunks")

                    # 流结束后：若提供了session_id，则持久化完整助手消息（更便于历史回放与上下文拼接）
                    if session_id and accumulated_text.strip():
                        try:
                            assistant_parts = [
                                {"type": "text", "text": accumulated_text}
                            ]
                            
                            # 使用ChatSessionMgr保存助手消息
                            chat_mgr.save_message(
                                session_id=session_id,
                                message_id=response_id,
                                role="assistant",
                                content=accumulated_text,
                                parts=assistant_parts,
                            )
                            print(f"[DEBUG] Persisted assistant message for session {session_id}, message_id={response_id}")
                        except Exception as persist_err:
                            # 持久化失败不影响流
                            print(f"[WARN] Failed to persist assistant message: {persist_err}")

                    # 发送文本结束和消息完成事件 - AI SDK标准格式
                    yield f"data: {json.dumps({'type': 'text-end', 'id': response_id})}\n\n"
                    yield f"data: {json.dumps({'type': 'finish'})}\n\n"
                    yield "data: [DONE]\n\n"

                except Exception as e:
                    # 发送错误事件
                    error_chunk = {
                        "type": "error",
                        "errorText": f"Stream generation error: {str(e)}"
                    }
                    yield f"data: {json.dumps(error_chunk)}\n\n"
                    # yield f"data: {json.dumps({'type': 'text-end', 'id': response_id})}\n\n"
                    # yield f"data: {json.dumps({'type': 'finish'})}\n\n"
                    # yield "data: [DONE]\n\n"

            return StreamingResponse(
                generate_ui_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "x-vercel-ai-ui-message-stream": "v1"
                }
            )
        except Exception as e:
            print(f"Error in chat_ui_stream: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # 返回路由对象给主应用
    return router
