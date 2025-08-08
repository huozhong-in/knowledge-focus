"""
聊天会话API端点
提供会话管理、消息持久化、Pin文件管理等RESTful接口
"""

from fastapi import APIRouter, Depends, Body, HTTPException, Query
from sqlmodel import Session
from typing import List, Dict, Any, Optional
import json
import logging

from chatsession_mgr import ChatSessionMgr

logger = logging.getLogger(__name__)


def get_router(external_get_session: callable) -> APIRouter:
    router = APIRouter()

    def get_chat_session_manager(session: Session = Depends(external_get_session)) -> ChatSessionMgr:
        return ChatSessionMgr(session)

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
                    "metadata": json.loads(session.metadata_json or "{}"),
                    "is_active": session.is_active
                }
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/chat/sessions/smart", tags=["chat-sessions"])
    def create_smart_session(
        data: Dict[str, Any] = Body(...),
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """创建智能命名的聊天会话"""
        try:
            first_message_content = data.get("first_message_content", "")
            metadata = data.get("metadata", {})
            
            if not first_message_content.strip():
                raise HTTPException(status_code=400, detail="first_message_content is required for smart session creation")
            
            # 使用LLM生成智能会话名称
            from models_mgr import ModelsMgr
            models_mgr = ModelsMgr(chat_mgr.session)
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
                    "metadata": json.loads(session.metadata_json or "{}"),
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
                    "metadata": json.loads(session.metadata_json or "{}"),
                    "is_active": session.is_active,
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
        chat_mgr: ChatSessionMgr = Depends(get_chat_session_manager)
    ):
        """获取指定会话详情"""
        try:
            session = chat_mgr.get_session(session_id)
            if not session or not session.is_active:
                raise HTTPException(status_code=404, detail="Session not found")
            
            stats = chat_mgr.get_session_stats(session_id)
            
            return {
                "success": True,
                "data": {
                    "id": session.id,
                    "name": session.name,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "metadata": json.loads(session.metadata_json or "{}"),
                    "is_active": session.is_active,
                    "stats": stats
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
                    "metadata": json.loads(session.metadata_json or "{}"),
                    "is_active": session.is_active
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
                    "parts": json.loads(msg.parts or "[]"),
                    "metadata": json.loads(msg.metadata_json or "{}"),
                    "sources": json.loads(msg.sources or "[]"),
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
                    "parts": json.loads(message.parts or "[]"),
                    "metadata": json.loads(message.metadata_json or "{}"),
                    "sources": json.loads(message.sources or "[]"),
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
                    "metadata": json.loads(file.metadata_json or "{}")
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
                    "metadata": json.loads(pin_file.metadata_json or "{}")
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
