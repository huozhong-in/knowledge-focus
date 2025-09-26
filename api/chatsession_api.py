"""
聊天会话API端点
提供会话管理、消息持久化、Pin文件管理等RESTful接口
"""

from fastapi import APIRouter, Depends, Body, HTTPException, Query
from sqlmodel import Session, select
from sqlalchemy import Engine
from typing import Dict, Any, Optional
import logging
from chatsession_mgr import ChatSessionMgr
from models_mgr import ModelsMgr
from db_mgr import Tool

logger = logging.getLogger()


def get_router(get_engine: Engine, base_dir: str) -> APIRouter:
    router = APIRouter()

    def get_chat_session_manager(engine: Engine = Depends(get_engine)) -> ChatSessionMgr:
        return ChatSessionMgr(engine=engine)
    
    def get_models_manager(engine: Engine = Depends(get_engine)) -> ModelsMgr:
        return ModelsMgr(engine=engine, base_dir=base_dir)

    # ==================== 会话管理端点 ====================

    @router.post("/chat/sessions", tags=["chat-sessions"])
    def create_session(
        data: Dict[str, Any] = Body(...),
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """创建新的聊天会话"""
        try:
            name = data.get("name")
            metadata = data.get("metadata", {})
            
            session = chat_mgr.create_session(name=name, metadata=metadata)
            
            return {
                    "success": True,
                    "data": {
                        "id": session.id,
                        "name": session.name,
                        "created_at": session.created_at.isoformat(),
                        "updated_at": session.updated_at.isoformat(),
                        "metadata": session.metadata_json or {},
                        "is_active": session.is_active,
                        "scenario_id": session.scenario_id
                    }
                }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/chat/sessions/smart", tags=["chat-sessions"])
    def create_smart_session(
        data: Dict[str, Any] = Body(...),
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager),
        models_mgr: ModelsMgr = Depends(get_models_manager)
    ):
        """创建智能命名的聊天会话"""
        try:
            first_message_content = data.get("first_message_content", "")
            metadata = data.get("metadata", {})
            
            if not first_message_content.strip():
                raise HTTPException(status_code=400, detail="first_message_content is required for smart session creation")
            
            # 使用LLM生成智能会话名称
            smart_title = models_mgr.generate_session_title(first_message_content)
            
            # 创建会话
            session = chat_mgr.create_session(name=smart_title, metadata=metadata)
            
            return {
                "success": True,
                "data": {
                    "id": session.id,
                    "name": session.name,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "metadata": session.metadata_json or {},
                    "is_active": session.is_active
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating smart session: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/chat/sessions", tags=["chat-sessions"])
    def get_sessions(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页大小"),
        search: Optional[str] = Query(None, description="搜索关键词"),
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """获取聊天会话列表"""
        try:
            sessions, total = chat_mgr.get_sessions(
                page=page,
                page_size=page_size,
                search=search
            )
            
            sessions_data = []
            for session in sessions:
                # 获取会话统计信息
                stats = chat_mgr.get_session_stats(session.id)
                
                sessions_data.append({
                    "id": session.id,
                    "name": session.name,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "metadata": session.metadata_json or {},
                    "is_active": session.is_active,
                    "scenario_id": session.scenario_id,
                    "stats": stats
                })
            
            return {
                "success": True,
                "data": {
                    "sessions": sessions_data,
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total": total,
                        "pages": (total + page_size - 1) // page_size
                    }
                }
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/chat/sessions/{session_id}", tags=["chat-sessions"])
    def get_session(
        session_id: int,
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager),
        engine: Engine = Depends(get_engine)
    ):
        """获取指定会话详情"""
        try:
            session = chat_mgr.get_session(session_id)
            if not session or not session.is_active:
                raise HTTPException(status_code=404, detail="Session not found")
            
            stats = chat_mgr.get_session_stats(session_id)
            
            # 恢复前端工具勾选所需：返回会话选择的工具列表
            selected_tools = session.selected_tool_names or []

            # 可选：返回前端需要呈现的工具配置状态（例如 Tavily 是否已配置 api_key）
            # 返回配置状态和 API Key（用于前端预设）
            tool_configs: Dict[str, Any] = {}
            try:
                with Session(engine) as s:
                    tavily_tool = s.exec(
                        select(Tool).where(Tool.name == "search_use_tavily")
                    ).first()
                    tavily_api_key = ""
                    if tavily_tool and tavily_tool.metadata_json:
                        tavily_api_key = tavily_tool.metadata_json.get("api_key", "") or ""
                    tool_configs["search_use_tavily"] = {
                        "has_api_key": bool(tavily_api_key),
                        "api_key": tavily_api_key,  # 返回实际 API Key 供前端使用
                    }
            except Exception:
                # 安全兜底，不影响主流程
                tool_configs["search_use_tavily"] = {
                    "has_api_key": False,
                    "api_key": "",
                }
            
            return {
                "success": True,
                "data": {
                    "id": session.id,
                    "name": session.name,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "metadata": session.metadata_json or {},
                    "is_active": session.is_active,
                    "scenario_id": session.scenario_id,
                    "stats": stats,
                    "selected_tools": selected_tools,
                    "tool_configs": tool_configs,
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.put("/chat/sessions/{session_id}", tags=["chat-sessions"])
    def update_session(
        session_id: int,
        data: Dict[str, Any] = Body(...),
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """更新会话信息"""
        try:
            name = data.get("name")
            metadata = data.get("metadata")
            
            session = chat_mgr.update_session(
                session_id=session_id,
                name=name,
                metadata=metadata
            )
            
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            
            return {
                "success": True,
                "data": {
                    "id": session.id,
                    "name": session.name,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "metadata": session.metadata_json or {},
                    "is_active": session.is_active,
                    "scenario_id": session.scenario_id
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/chat/sessions/{session_id}", tags=["chat-sessions"])
    def delete_session(
        session_id: int,
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """删除会话（软删除）"""
        try:
            success = chat_mgr.delete_session(session_id)
            
            if not success:
                raise HTTPException(status_code=404, detail="Session not found")
            
            return {"success": True, "message": "Session deleted successfully"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== 工具管理端点 ====================
    # change_session_tools
    @router.put("/chat/sessions/{session_id}/tools", tags=["chat-sessions"])
    def change_session_tools(
        session_id: int,
        data: Dict[str, Any] = Body(...),
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """更改会话关联的工具列表"""
        try:
            add_tools = data.get("add_tools", [])
            remove_tools = data.get("remove_tools", [])
            
            result = chat_mgr.change_session_tools(session_id, add_tools=add_tools, remove_tools=remove_tools)
            return {
                "success": True,
                "data": result
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== 消息管理端点 ====================

    @router.get("/chat/sessions/{session_id}/messages", tags=["chat-messages"])
    def get_messages(
        session_id: int,
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(30, ge=1, le=100, description="每页大小"),
        latest_first: bool = Query(True, description="是否最新消息在前"),
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """获取会话消息列表"""
        try:
            # 验证会话存在
            session = chat_mgr.get_session(session_id)
            if not session or not session.is_active:
                raise HTTPException(status_code=404, detail="Session not found")
            
            messages, total = chat_mgr.get_messages(
                session_id=session_id,
                page=page,
                page_size=page_size,
                latest_first=latest_first
            )
            
            messages_data = []
            for msg in messages:
                messages_data.append({
                    "id": msg.id,
                    "message_id": msg.message_id,
                    "role": msg.role,
                    "content": msg.content,
                    "parts": msg.parts or [],  # 直接使用，SQLModel已处理JSON序列化
                    "metadata": msg.metadata_json or {},  # 直接使用，SQLModel已处理JSON序列化
                    "sources": msg.sources or [],  # 直接使用，SQLModel已处理JSON序列化
                    "created_at": msg.created_at.isoformat()
                })
            
            return {
                "success": True,
                "data": {
                    "messages": messages_data,
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total": total,
                        "pages": (total + page_size - 1) // page_size
                    }
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/chat/sessions/{session_id}/messages", tags=["chat-messages"])
    def save_message(
        session_id: int,
        data: Dict[str, Any] = Body(...),
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """保存聊天消息"""
        try:
            # 验证会话存在
            session = chat_mgr.get_session(session_id)
            if not session or not session.is_active:
                raise HTTPException(status_code=404, detail="Session not found")
            
            message_id = data.get("message_id")
            role = data.get("role")
            content = data.get("content")
            parts = data.get("parts")
            metadata = data.get("metadata")
            sources = data.get("sources")
            
            if not message_id or not role:
                raise HTTPException(status_code=400, detail="message_id and role are required")
            
            message = chat_mgr.save_message(
                session_id=session_id,
                message_id=message_id,
                role=role,
                content=content,
                parts=parts,
                metadata=metadata,
                sources=sources
            )
            
            return {
                "success": True,
                "data": {
                    "id": message.id,
                    "message_id": message.message_id,
                    "role": message.role,
                    "content": message.content,
                    "parts": message.parts or [],  # 直接使用，SQLModel已处理JSON序列化
                    "metadata": message.metadata_json or {},  # 直接使用，SQLModel已处理JSON序列化
                    "sources": message.sources or [],  # 直接使用，SQLModel已处理JSON序列化
                    "created_at": message.created_at.isoformat()
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== Pin文件管理端点 ====================

    @router.get("/chat/sessions/{session_id}/pinned-files", tags=["chat-pin-files"])
    def get_pinned_files(
        session_id: int,
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """获取会话Pin文件列表"""
        try:
            # 验证会话存在
            session = chat_mgr.get_session(session_id)
            if not session or not session.is_active:
                raise HTTPException(status_code=404, detail="Session not found")
            
            pinned_files = chat_mgr.get_pinned_files(session_id)
            
            files_data = []
            for file in pinned_files:
                files_data.append({
                    "id": file.id,
                    "file_path": file.file_path,
                    "file_name": file.file_name,
                    "pinned_at": file.pinned_at.isoformat(),
                    "metadata": file.metadata_json or {}
                })
            
            return {
                "success": True,
                "data": {"pinned_files": files_data}
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/chat/sessions/{session_id}/pin-file", tags=["chat-pin-files"])
    def pin_file(
        session_id: int,
        data: Dict[str, Any] = Body(...),
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """为会话Pin文件"""
        try:
            # 验证会话存在
            session = chat_mgr.get_session(session_id)
            if not session or not session.is_active:
                raise HTTPException(status_code=404, detail="Session not found")
            
            file_path = data.get("file_path")
            file_name = data.get("file_name")
            metadata = data.get("metadata", {})
            
            if not file_path or not file_name:
                raise HTTPException(status_code=400, detail="file_path and file_name are required")
            
            pin_file = chat_mgr.pin_file(
                session_id=session_id,
                file_path=file_path,
                file_name=file_name,
                metadata=metadata
            )
            
            return {
                "success": True,
                "data": {
                    "id": pin_file.id,
                    "file_path": pin_file.file_path,
                    "file_name": pin_file.file_name,
                    "pinned_at": pin_file.pinned_at.isoformat(),
                    "metadata": pin_file.metadata_json or {}
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/chat/sessions/{session_id}/pinned-files", tags=["chat-pin-files"])
    def unpin_file(
        session_id: int,
        file_path: str = Query(..., description="要取消Pin的文件路径"),
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """取消Pin文件"""
        try:
            # 验证会话存在
            session = chat_mgr.get_session(session_id)
            if not session or not session.is_active:
                raise HTTPException(status_code=404, detail="Session not found")
            
            success = chat_mgr.unpin_file(session_id, file_path)
            
            if not success:
                raise HTTPException(status_code=404, detail="Pinned file not found")
            
            return {"success": True, "message": "File unpinned successfully"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router
