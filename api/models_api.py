from fastapi import APIRouter, Depends, Body
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from sqlalchemy import Engine
from typing import List, Dict, Any, Tuple
import json
import uuid
import logging
from datetime import datetime
from chatsession_mgr import ChatSessionMgr
from db_mgr import ModelCapability, Scenario, ModelProvider
from model_config_mgr import ModelConfigMgr
from models_mgr import ModelsMgr
from model_capability_confirm import ModelCapabilityConfirm
from pydantic import BaseModel
from models_builtin import BUILTIN_MODELS, ModelsBuiltin
from builtin_openai_compat import (
    MLXVLMModelManager,
    OpenAIChatCompletionRequest,
    RequestPriority,
    get_vlm_manager,
)

logger = logging.getLogger()

def get_router(get_engine: Engine, base_dir: str) -> APIRouter:
    router = APIRouter()

    def get_model_config_manager(engine: Engine = Depends(get_engine)) -> ModelConfigMgr:
        return ModelConfigMgr(engine)
    
    def get_models_manager(engine: Engine = Depends(get_engine)) -> ModelsMgr:
        return ModelsMgr(engine, base_dir=base_dir)

    def get_model_capability_confirm(engine: Engine = Depends(get_engine)) -> ModelCapabilityConfirm:
        return ModelCapabilityConfirm(engine, base_dir=base_dir)

    def get_chat_session_manager(engine: Engine = Depends(get_engine)) -> ChatSessionMgr:
        return ChatSessionMgr(engine)

    def get_models_builtin_manager(engine: Engine = Depends(get_engine)) -> ModelsBuiltin:
        return ModelsBuiltin(engine, base_dir=base_dir)

    def get_mlx_vlm_manager() -> MLXVLMModelManager:
        """获取 MLX-VLM 模型管理器的全局单例"""
        return get_vlm_manager()

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
            logger.error(f"Error discovering models from provider {id}: {e}")
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
    def get_model_for_global_capability(
        model_capability: str, 
        config_mgr: ModelConfigMgr = Depends(get_model_config_manager),
        engine: Engine = Depends(get_engine)
        ):
        """获取全局指定能力的模型分配"""
        try:
            capability = ModelCapability(model_capability)
            config = config_mgr.get_model_for_global_capability(capability)
            if config is not None:
                with Session(engine) as session:
                    provider = session.exec(
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
    async def assign_global_capability_to_model(
        model_capability: str, 
        data: Dict[str, Any] = Body(...), 
        config_mgr: ModelConfigMgr = Depends(get_model_config_manager),
        engine: Engine = Depends(get_engine),
        vlm_manager: MLXVLMModelManager = Depends(get_mlx_vlm_manager)
    ):
        """
        指定某个模型为全局的ModelCapability某项能力
        model_id为0表示取消全局分配
        
        注意：此API会触发智能卸载逻辑，如果所有能力都切换到其他模型，
        MLX-VLM 模型将自动卸载以释放内存。
        """
        try:
            model_id = data.get("model_id")
            if model_id is None:
                return {"success": False, "message": "Missing model_id"}
            
            try:
                capability = ModelCapability(model_capability)
            except ValueError:
                return {"success": False, "message": f"'{model_capability}' is not a valid ModelCapability"}
            
            # 执行能力分配
            success = config_mgr.assign_global_capability_to_model(model_config_id=model_id, capability=capability)
            if not success:
                return {"success": False, "message": "Failed to set model for global capability"}
            
            # 触发智能卸载检查
            try:
                unloaded = await vlm_manager.check_and_unload_if_unused(engine)
                if unloaded:
                    logger.info("MLX-VLM model auto-unloaded after capability reassignment")
            except Exception as e:
                # 卸载失败不应影响能力分配的成功
                logger.error(f"Smart unload failed: {e}", exc_info=True)
            
            return {"success": True}
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
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager),
        engine: Engine = Depends(get_engine)
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
                    with Session(engine) as session:
                        scenario = session.get(Scenario, chat_session.scenario_id)
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

    # ==================== 内置模型管理 API ====================
    
    @router.get("/models/builtin/list", tags=["models", "builtin"])
    def list_builtin_models(models_builtin: ModelsBuiltin = Depends(get_models_builtin_manager)):
        """获取所有内置模型列表及下载状态"""
        try:
            models = models_builtin.get_supported_models()
            return {"success": True, "data": models}
        except Exception as e:
            logger.error(f"获取内置模型列表失败: {e}")
            return {"success": False, "message": str(e)}
    
    @router.post("/models/builtin/initialize", tags=["models", "builtin"])
    async def initialize_builtin_model(
        request: Dict[str, Any] = Body(...),
        models_builtin: ModelsBuiltin = Depends(get_models_builtin_manager)
    ):
        """
        初始化内置模型（用于 Splash 页面）
        
        检查模型是否已下载，如果未下载则启动异步下载任务。
        下载进度通过 bridge events 实时推送到前端。
        
        Args:
            request: {"mirror": "huggingface" | "hf-mirror"}
        
        Returns:
            {"status": "ready", "model_path": "..."}  # 模型已就绪
            {"status": "downloading", "progress": 0}  # 正在下载
            {"status": "error", "message": "..."}     # 出错
        """
        try:
            model_id = "qwen3-vl-4b"  # 固定为默认模型
            mirror = request.get("mirror", "huggingface")
            
            # 检查模型是否已下载
            if models_builtin.is_model_downloaded(model_id):
                model_path = models_builtin.get_model_path(model_id)
                logger.info(f"Model {model_id} already downloaded at: {model_path}")
                return {
                    "status": "ready",
                    "model_path": model_path,
                    "message": "Model already downloaded"
                }
            
            # 启动异步下载任务
            import asyncio
            asyncio.create_task(
                models_builtin.download_model_async(model_id, mirror)
            )
            
            logger.info(f"Started async download for {model_id} using mirror: {mirror}")
            return {
                "status": "downloading",
                "progress": 0,
                "message": f"Download started using {mirror}"
            }
            
        except Exception as e:
            logger.error(f"初始化内置模型失败: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }
    
    @router.get("/models/builtin/download-status", tags=["models", "builtin"])
    def get_download_status(models_builtin: ModelsBuiltin = Depends(get_models_builtin_manager)):
        """
        获取内置模型下载状态
        
        Returns:
            {"downloaded": bool, "model_path": str | None}
        """
        try:
            model_id = "qwen3-vl-4b"
            
            is_downloaded = models_builtin.is_model_downloaded(model_id)
            model_path = models_builtin.get_model_path(model_id) if is_downloaded else None
            
            return {
                "success": True,
                "downloaded": is_downloaded,
                "model_path": model_path
            }
        except Exception as e:
            logger.error(f"获取下载状态失败: {e}")
            return {"success": False, "message": str(e)}
    
    @router.post("/models/builtin/{model_id}/download", tags=["models", "builtin"])
    async def download_builtin_model(model_id: str, models_builtin: ModelsBuiltin = Depends(get_models_builtin_manager)):
        """
        触发内置模型下载
        
        下载进度通过统一桥接器事件推送到前端：
        - model-download-progress: 下载进度更新（节流，每秒最多1次）
        - model-download-completed: 下载完成
        - model-download-failed: 下载失败
        
        前端应该监听这些事件来更新UI。
        """
        try:
            # 检查模型是否已下载
            if models_builtin.is_model_downloaded(model_id):
                return {"success": False, "message": "Model already downloaded"}
            
            # 启动异步下载任务
            from threading import Thread
            
            def download_task():
                try:
                    # 下载进度会自动通过 bridge_events 推送到前端
                    models_builtin.download_model(model_id)
                    logger.info(f"Model {model_id} downloaded successfully in background thread")
                except Exception as e:
                    logger.error(f"Background download failed for {model_id}: {e}", exc_info=True)
            
            # 在后台线程中启动下载
            thread = Thread(target=download_task, daemon=True)
            thread.start()
            
            return {"success": True, "message": "Download started", "model_id": model_id}
            
        except Exception as e:
            logger.error(f"启动模型下载失败: {e}")
            return {"success": False, "message": str(e)}
    
    @router.delete("/models/builtin/{model_id}", tags=["models", "builtin"])
    def delete_builtin_model(model_id: str, models_builtin: ModelsBuiltin = Depends(get_models_builtin_manager)):
        """删除已下载的内置模型"""
        try:
            success = models_builtin.delete_model(model_id)
            
            if success:
                return {"success": True, "message": "Model deleted successfully"}
            else:
                return {"success": False, "message": "Failed to delete model"}
                
        except Exception as e:
            logger.error(f"删除内置模型失败: {e}")
            return {"success": False, "message": str(e)}
    
    @router.get("/models/builtin/server/status", tags=["models", "builtin"])
    def get_builtin_server_status(models_builtin: ModelsBuiltin = Depends(get_models_builtin_manager)):
        """获取内置模型服务器状态"""
        try:
            status = models_builtin.get_server_status()
            return {"success": True, "data": status}
        except Exception as e:
            logger.error(f"获取服务器状态失败: {e}")
            return {"success": False, "message": str(e)}
    
    @router.post("/models/builtin/server/start", tags=["models", "builtin"])
    def start_builtin_server(data: Dict[str, Any] = Body(...), models_builtin: ModelsBuiltin = Depends(get_models_builtin_manager)):
        """启动内置模型服务器"""
        try:
            model_id = data.get("model_id")
            if not model_id:
                return {"success": False, "message": "model_id is required"}
            
            
            # 检查模型是否已下载
            if not models_builtin.is_model_downloaded(model_id):
                return {"success": False, "message": f"Model {model_id} not downloaded"}
            
            success = models_builtin.start_mlx_server(model_id)
            
            if success:
                status = models_builtin.get_server_status()
                return {"success": True, "message": "Server started successfully", "data": status}
            else:
                return {"success": False, "message": "Failed to start server"}
                
        except Exception as e:
            logger.error(f"启动服务器失败: {e}")
            return {"success": False, "message": str(e)}
    
    @router.post("/models/builtin/server/stop", tags=["models", "builtin"])
    def stop_builtin_server(models_builtin: ModelsBuiltin = Depends(get_models_builtin_manager)):
        """停止内置模型服务器"""
        try:
            success = models_builtin.stop_mlx_server()
            
            if success:
                return {"success": True, "message": "Server stopped successfully"}
            else:
                return {"success": False, "message": "Failed to stop server"}
                
        except Exception as e:
            logger.error(f"停止服务器失败: {e}")
            return {"success": False, "message": str(e)}
    
    @router.post("/models/builtin/{model_id}/auto-assign", tags=["models", "builtin"])
    def auto_assign_builtin_model(model_id: str, models_builtin: ModelsBuiltin = Depends(get_models_builtin_manager)):
        """
        自动分配内置模型到未配置的能力
        
        智能分配策略:
        - 仅分配到未配置的能力 (新手友好)
        - 不覆盖已配置的能力 (熟手尊重)
        
        Returns:
            {
                "success": bool,
                "assigned_capabilities": List[str],  # 已分配的能力列表
                "message": str
            }
        """
        try:
            # 检查模型是否已下载
            if not models_builtin.is_model_downloaded(model_id):
                return {
                    "success": False,
                    "assigned_capabilities": [],
                    "message": f"Model {model_id} is not downloaded"
                }
            
            # 执行自动分配
            assigned = models_builtin.auto_assign_capabilities(
                model_id=model_id,
                base_dir=base_dir
            )
            
            if len(assigned) > 0:
                return {
                    "success": True,
                    "assigned_capabilities": assigned,
                    "message": f"Successfully assigned {len(assigned)} capabilities"
                }
            else:
                return {
                    "success": True,
                    "assigned_capabilities": [],
                    "message": "No unassigned capabilities found"
                }
                
        except Exception as e:
            logger.error(f"自动分配失败: {e}", exc_info=True)
            return {
                "success": False,
                "assigned_capabilities": [],
                "message": str(e)
            }
    
    # ==================== OpenAI 兼容 API ====================
    
    @router.post("/v1/chat/completions", tags=["models", "openai-compat"])
    async def openai_chat_completions(
        request: dict, 
        models_builtin: ModelsBuiltin = Depends(get_models_builtin_manager),
        mlx_vlm_manager: MLXVLMModelManager = Depends(get_mlx_vlm_manager)
    ):
        """
        OpenAI 兼容的 /v1/chat/completions 接口
        
        支持内置 MLX-VLM 模型，完全兼容 OpenAI API 格式
        
        使用方式:
        ```python
        from openai import OpenAI
        
        client = OpenAI(
            base_url="http://127.0.0.1:60315/v1",
            api_key="dummy"  # 内置模型不需要 API key
        )
        
        response = client.chat.completions.create(
            model="qwen3-vl-4b",  # 使用 model_id
            messages=[
                {"role": "user", "content": "Hello!"}
            ]
        )
        ```
        """
        
        try:
            # 解析请求
            openai_request = OpenAIChatCompletionRequest(**request)
            
            # 获取模型路径
            model_id = openai_request.model
            
            # 支持两种模型标识符:
            # 1. model_id (如 "qwen3-vl-4b")
            # 2. hf_model_id (如 "mlx-community/Qwen2.5-VL-3B-Instruct-4bit")
            model_path = None
            
            if model_id in BUILTIN_MODELS:
                # 直接使用 model_id
                model_path = models_builtin.get_model_path(model_id)
            else:
                # 尝试通过 hf_model_id 查找
                for mid, config in BUILTIN_MODELS.items():
                    if config["hf_model_id"] == model_id:
                        model_path = models_builtin.get_model_path(mid)
                        break
            
            # 检查模型是否已下载
            if not model_path:
                return {
                    "error": {
                        "message": f"Model {model_id} not found or not downloaded. Please download it first.",
                        "type": "invalid_request_error",
                        "code": "model_not_found"
                    }
                }
            
            # 使用队列系统调用生成逻辑
            # 默认所有聊天请求都是高优先级 (priority=1)
            # 如果未来需要支持批量任务,可以通过 Query 参数传入 priority=10
            logger.info(f"Enqueueing completion request for model: {model_id}, path: {model_path}")
            logger.info(f"Request stream mode: {openai_request.stream}")
            
            # 聊天请求使用 HIGH 优先级
            response = await mlx_vlm_manager.enqueue_request(
                request=openai_request,
                model_path=model_path,
                priority=RequestPriority.HIGH
            )
            
            logger.info(f"Response type: {type(response)}")
            return response
            
        except Exception as e:
            logger.error(f"OpenAI 兼容接口错误: {e}", exc_info=True)
            return {
                "error": {
                    "message": str(e),
                    "type": "internal_server_error",
                    "code": "generation_failed"
                }
            }

    return router