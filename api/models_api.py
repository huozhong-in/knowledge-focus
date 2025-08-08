from fastapi import APIRouter, Depends, Body, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from typing import List, Dict, Any
import json
import uuid
from datetime import datetime
from db_mgr import SystemConfig, ChatMessage
from model_config_mgr import ModelConfigMgr
from models_mgr import ModelsMgr
from chatsession_mgr import ChatSessionMgr

def get_router(external_get_session: callable) -> APIRouter:
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

    def get_models_manager(session: Session = Depends(external_get_session)) -> ModelsMgr:
        return ModelsMgr(session)
    
    def get_chat_session_manager(session: Session = Depends(external_get_session)) -> ChatSessionMgr:
        return ChatSessionMgr(session)

    @router.post("/chat/stream", tags=["local-models"])
    async def chat_stream(
        request_data: Dict[str, Any] = Body(...),
        models_mgr: ModelsMgr = Depends(get_models_manager)
    ):
        """处理聊天流式请求"""
        try:
            messages = request_data.get("messages", [])
            # 可选：会话ID（用于持久化）；未提供则仅流式返回不落库
            session_id: int | None = request_data.get("session_id")
            model_config = request_data.get("model_config", {})

            if not messages or not model_config:
                raise HTTPException(status_code=400, detail="Missing messages or model_config")

            provider_type = model_config.get("provider_type")
            model_name = model_config.get("model_name")

            if not provider_type or not model_name:
                raise HTTPException(status_code=400, detail="Missing provider_type or model_name in model_config")

            return StreamingResponse(
                models_mgr.stream_chat(
                    provider_type=provider_type,
                    model_name=model_name,
                    messages=messages
                ),
                media_type="text/event-stream"
            )
        except Exception as e:
            # Log the exception for debugging
            print(f"Error in chat_stream: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/chat/ui-stream", tags=["local-models"])
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
            trigger = request_data.get("trigger", "submit-message")
            chat_id = request_data.get("chatId", str(uuid.uuid4()))
            message_id = request_data.get("messageId")
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

                    # 获取系统配置的基础模型
                    try:
                        key = "selected_model_for_base"
                        config_entry = models_mgr.session.exec(select(SystemConfig).where(SystemConfig.key == key)).first()

                        if not config_entry or not config_entry.value or config_entry.value == 'null':
                            raise ValueError("No base model configuration found")

                        role_config = json.loads(config_entry.value)
                        provider_type = role_config.get("provider_type")
                        model_name = role_config.get("model_id")  # 注意：数据库中存储的是model_id

                        if not provider_type or not model_name:
                            raise ValueError("Incomplete base model configuration")

                    except Exception as config_error:
                        # 如果配置获取失败，返回错误
                        error_chunk = {
                            "type": "error",
                            "errorText": f"Model configuration error: {str(config_error)}"
                        }
                        yield f"data: {json.dumps(error_chunk)}\n\n"
                        yield f"data: {json.dumps({'type': 'text-end', 'id': response_id})}\n\n"
                        yield f"data: {json.dumps({'type': 'finish'})}\n\n"
                        yield "data: [DONE]\n\n"
                        return

                    # 调用现有的stream_chat方法
                    print(f"[DEBUG] Starting stream_chat with provider: {provider_type}, model: {model_name}")
                    chunk_count = 0
                    async for content_chunk in models_mgr.stream_chat(
                        provider_type=provider_type,
                        model_name=model_name,
                        messages=converted_messages
                    ):
                        chunk_count += 1
                        print(f"[DEBUG] Received chunk {chunk_count}: '{content_chunk[:50]}...'")

                        if content_chunk and not content_chunk.startswith("Error:"):
                            # 发送文本增量事件
                            ui_chunk = {
                                "type": "text-delta",
                                "delta": content_chunk,
                                "id": str(uuid.uuid4())
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
                                parts=assistant_parts
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

            return StreamingResponse(
                generate_ui_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                }
            )
        except Exception as e:
            print(f"Error in chat_ui_stream: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # 返回路由对象给主应用
    return router
