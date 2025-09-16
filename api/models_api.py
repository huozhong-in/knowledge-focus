from fastapi import APIRouter, Depends, Body
from fastapi.responses import StreamingResponse
from sqlmodel import Session
from typing import List, Dict, Any, Tuple
import json
import uuid
import logging
from datetime import datetime
from chatsession_mgr import ChatSessionMgr
from db_mgr import ModelCapability, Scenario
from model_config_mgr import ModelConfigMgr
from models_mgr import ModelsMgr
from model_capability_confirm import ModelCapabilityConfirm
from pydantic import BaseModel

logger = logging.getLogger(__name__)

def get_router(external_get_session: callable, base_dir: str) -> APIRouter:
    router = APIRouter()

    def get_model_config_manager(session: Session = Depends(external_get_session)) -> ModelConfigMgr:
        return ModelConfigMgr(session)
    
    def get_models_manager(session: Session = Depends(external_get_session)) -> ModelsMgr:
        return ModelsMgr(session, base_dir=base_dir)

    def get_model_capability_confirm(session: Session = Depends(external_get_session)) -> ModelCapabilityConfirm:
        return ModelCapabilityConfirm(session, base_dir=base_dir)

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
        session_id: int = None  # 使session_id可选，以防前端没有发送
        scenario_id: int = 0  # 场景即状态图的一个大的分支，前端要明确感知并有效配合

        @classmethod
        def model_validate(cls, data):
            # 如果session_id在body中而不是顶级字段，尝试提取
            if isinstance(data, dict):
                if 'session_id' not in data and hasattr(data, 'get'):
                    # 检查是否在嵌套的body中
                    if 'body' in data and isinstance(data['body'], dict):
                        session_id = data['body'].get('session_id')
                        if session_id:
                            data['session_id'] = session_id
                
                # 确保messages是列表
                if 'messages' in data and not isinstance(data['messages'], list):
                    data['messages'] = [data['messages']]
            
            return super().model_validate(data)

    @router.post("/chat/agent-stream", tags=["models"])
    async def agent_chat_stream(
        request: AgentChatRequest,
        config_mgr: ModelConfigMgr = Depends(get_model_config_manager),
        models_mgr: ModelsMgr = Depends(get_models_manager),
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """
        Handles agentic chat sessions that require tools and session context.
        Streams responses according to the Vercel AI SDK v5 protocol.
        """
        def _accumulate_parts(sse_chunk: Any) -> Tuple[str, List[Dict[str, Any]]]:
            accumulated_text_content = ""
            accumulated_parts = [] 
            if sse_chunk.startswith('data: ') and not sse_chunk.strip().endswith('[DONE]'):
                try:
                    sse_data = sse_chunk[6:].strip()  # 移除 'data: ' 前缀
                    if sse_data:
                        parsed_data = json.loads(sse_data)
                        # 记录各种类型的parts，参考 https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol
                        if parsed_data.get('type') == 'text-delta':
                            # 只累积text-delta事件来构建单独保存的文本内容
                            accumulated_text_content += parsed_data.get('delta', '')
                        if parsed_data.get('type') in [
                                'start',
                                'text-start',
                                'text-delta', 
                                'text-end',
                                'reasoning-start',
                                'reasoning-delta',
                                'reasoning-end',
                                'tool-input-available', 
                                'tool-output-available',
                                'finish',
                                ]:
                            accumulated_parts.append(parsed_data)
                        else:
                            # data: {"type":"error","errorText":"error message"}
                            pass  # 忽略其他类型
                except json.JSONDecodeError:
                    # 忽略无法解析的数据行
                    pass
            return accumulated_text_content, accumulated_parts
        
        async def stream_generator():
            # * 检查必须有文本模型或视觉模型配置好了
            if not (config_mgr.get_spec_model_config(ModelCapability.TEXT) or config_mgr.get_spec_model_config(ModelCapability.VISUAL)):
                logger.error("No text or visual model configured")
                # 发送标准错误事件
                error_event = f'data: {json.dumps({"type": "error", "errorText": "No text or visual model configured"})}\n'
                yield error_event
            
            try:
                # 保存用户消息
                # Vercel AI SDK UI在每次请求时都会发送所有历史消息
                # 我们只保存最后一条用户消息
                last_user_message = None
                if request.messages and len(request.messages) > 0:
                    # 确保messages是列表且最后一个元素是字典
                    last_message = request.messages[-1]
                    logger.info(f"Last message: {last_message}, type: {type(last_message)}")
                    
                    if isinstance(last_message, dict) and last_message.get("role") == "user":
                        last_user_message = last_message
                    elif isinstance(last_message, str):
                        # 如果是字符串，尝试解析JSON
                        try:
                            last_message = json.loads(last_message)
                            if last_message.get("role") == "user":
                                last_user_message = last_message
                        except json.JSONDecodeError:
                            logger.error(f"Failed to parse message as JSON: {last_message}")
                
                if last_user_message is None:
                    # 如果没有找到用户消息，返回错误
                    yield f"data: {json.dumps({'type': 'error', 'errorText': 'No user message found'})}\n\n"
                    return

                logger.info(f"Processing user message: {last_user_message}")
            
            except Exception as e:
                logger.error(f"Error in initial processing: {e}")
                yield f"data: {json.dumps({'type': 'error', 'errorText': f'Initial processing error: {str(e)}'})}\n\n"
                return

            # 提取用户消息内容 - 兼容AI SDK v5的parts格式
            content_text = ""
            
            # AI SDK v5格式：优先从parts中提取文本
            if "parts" in last_user_message:
                for part in last_user_message["parts"]:
                    if part.get("type") == "text":
                        content_text += part.get("text", "")
            
            # 备用：检查传统的content字段
            if not content_text:
                content_text = last_user_message.get("content", "")
            
            content_text = content_text.strip()
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

            # 流式生成并保存助手消息
            assistant_message_id = f"asst_{uuid.uuid4().hex}"
            accumulated_text_content = ""  # 保存纯文本内容，便于搜索和摘要等文本处理
            accumulated_parts = []  # 用于累积不同类型的parts内容，保存到数据库，以便用户切换会话时能“恢复现场”

            try:
                # 检查是否为共读场景
                chat_session = chat_mgr.get_session(request.session_id)
                if chat_session and chat_session.scenario_id:
                    logger.info(f"检测到场景模式，scenario_id: {chat_session.scenario_id}")
                    # 获取场景信息  
                    scenario = chat_mgr.session.get(Scenario, chat_session.scenario_id)
                    if scenario and scenario.name == "co_reading":
                        logger.info("启动PDF共读模式")
                        # 调用共读流协议处理函数
                        async for sse_chunk in models_mgr.coreading_v5_compatible(
                            messages=[last_user_message],
                            session_id=request.session_id,
                        ):
                            yield sse_chunk
                            # 解析SSE数据以便累积保存（用于持久化）
                            accumulated_text_content_delta, accumulated_parts_delta = _accumulate_parts(sse_chunk)
                            accumulated_text_content += accumulated_text_content_delta
                            accumulated_parts.extend(accumulated_parts_delta)
                else:
                    chunk_count = 0
                    async for sse_chunk in models_mgr.stream_agent_chat_v5_compatible(
                        messages=[last_user_message],  # 传递包含最后一条用户消息的列表
                        session_id=request.session_id
                    ):
                        chunk_count += 1
                        # 直接传递给前端，无需额外转换
                        yield sse_chunk
                        
                        # 解析SSE数据以便累积保存（用于持久化）
                        accumulated_text_content_delta, accumulated_parts_delta = _accumulate_parts(sse_chunk)
                        accumulated_text_content += accumulated_text_content_delta
                        accumulated_parts.extend(accumulated_parts_delta)


            except Exception as e:
                logger.error(f"Error in agent_chat_stream: {e}")
                # 发送标准错误事件
                error_event = f'data: {json.dumps({"type": "error", "errorText": str(e)})}\n'
                yield error_event
            
            finally:
                # 在流结束后，将完整的助手消息持久化到数据库
                if accumulated_text_content.strip():
                    chat_mgr.save_message(
                        session_id=request.session_id,
                        message_id=assistant_message_id,
                        role="assistant",
                        content=accumulated_text_content.strip(),
                        parts=accumulated_parts
                    )
                    logger.info(f"Saved assistant message {assistant_message_id} with content length: {len(accumulated_text_content.strip())}")
                else:
                    logger.warning(f"No content to save for assistant message {assistant_message_id}")
                # # 清理截图文件
                # screenshots_dir = Path(base_dir).parent / "tauri-plugin-screenshots"
                # for image_path in screenshots_dir.glob("*.png"):
                #     # 清理24小时以上的旧文件
                #     if (datetime.now() - datetime.fromtimestamp(image_path.stat().st_mtime)).days >= 1:
                #         image_path.unlink(missing_ok=True)

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

    @router.post("/chat/sessions/{session_id}/scenario", tags=["chat"])
    async def manage_session_scenario(
        session_id: int,
        data: Dict[str, Any] = Body(...),
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """
        管理会话场景模式
        
        Args:
            session_id: 会话ID
            action: 操作类型 - "enter_co_reading" 进入共读模式, "exit_co_reading" 退出共读模式
            pdf_path: PDF文件路径（进入共读模式时必需）
        
        Returns:
            {"success": True, "scenario_id": int/None}
        """
        try:
            # 从JSON body中提取参数
            action = data.get("action")
            pdf_path = data.get("pdf_path")
            
            if not action:
                return {"success": False, "message": "Action is required"}
            
            if action == "enter_co_reading":
                if not pdf_path:
                    return {"success": False, "message": "PDF path is required for co_reading mode"}
                
                # 获取co_reading场景ID
                scenario_id = chat_mgr.get_scenario_id_by_name("co_reading")
                if not scenario_id:
                    return {"success": False, "message": "co_reading scenario not found in database"}
                
                # 更新会话场景配置
                updated_session = chat_mgr.update_session_scenario(
                    session_id=session_id,
                    scenario_id=scenario_id,
                    metadata={"pdf_path": pdf_path, "entered_at": str(datetime.now())}
                )
                
                if updated_session:
                    logger.info(f"会话 {session_id} 已切换到共读模式，PDF: {pdf_path}")
                    # 手动处理metadata字段映射，确保返回解析后的对象而不是JSON字符串
                    session_data = updated_session.model_dump()
                    # metadata_json已经是Dict对象，直接赋值
                    session_data["metadata"] = updated_session.metadata_json
                    return {"success": True, "data": session_data}
                else:
                    return {"success": False, "message": "Failed to update session or session not found"}
            
            elif action == "exit_co_reading":
                # 退出共读模式，清除scenario_id
                updated_session = chat_mgr.update_session_scenario(
                    session_id=session_id,
                    scenario_id=None,
                    metadata={"exited_at": str(datetime.now())}
                )
                
                if updated_session:
                    logger.info(f"会话 {session_id} 已退出共读模式")
                    # 手动处理metadata字段映射，确保返回解析后的对象而不是JSON字符串
                    session_data = updated_session.model_dump()
                    # metadata_json已经是Dict对象，直接赋值
                    session_data["metadata"] = updated_session.metadata_json
                    return {"success": True, "data": session_data}
                else:
                    return {"success": False, "message": "Failed to update session or session not found"}
            
            else:
                return {"success": False, "message": f"Unknown action: {action}"}
        
        except Exception as e:
            logger.error(f"管理会话场景失败: {e}")
            return {"success": False, "message": str(e)}



    return router