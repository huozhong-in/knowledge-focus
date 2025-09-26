"""
聊天会话管理模块
处理会话创建、消息存储、Pin文件管理等功能
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from sqlmodel import Session, select, desc, and_
from sqlalchemy import Engine
from db_mgr import ChatSession, ChatMessage, ChatSessionPinFile

logger = logging.getLogger()


class ChatSessionMgr:
    """聊天会话管理器"""

    def __init__(self, engine: Engine):
        self.engine = engine

    # ==================== 会话管理 ====================
    
    def create_session(self, name: str = None, metadata: Dict[str, Any] = None) -> ChatSession:
        """
        创建新的聊天会话
        
        Args:
            name: 会话名称，如果为空则自动生成
            metadata: 会话元数据
            
        Returns:
            创建的会话对象
        """
        if not name:
            name = f"New chat {datetime.now().strftime('%m-%d %H:%M')}"
            
        session_obj = ChatSession(
            name=name,
            metadata_json=metadata or {},
            is_active=True
        )
        with Session(self.engine) as session:
            session.add(session_obj)
            session.commit()
            session.refresh(session_obj)
            return session_obj
    
    def get_sessions(self, page: int = 1, page_size: int = 20, search: str = None) -> Tuple[List[ChatSession], int]:
        """
        获取会话列表
        
        Args:
            page: 页码（从1开始）
            page_size: 每页大小
            search: 搜索关键词（在name中搜索）
            
        Returns:
            (会话列表, 总数量)
        """
        query = select(ChatSession).where(ChatSession.is_active)
        
        # 添加搜索条件
        if search:
            query = query.where(ChatSession.name.contains(search))
            
        # 获取总数
        count_query = select(ChatSession.id).where(ChatSession.is_active)
        if search:
            count_query = count_query.where(ChatSession.name.contains(search))
        with Session(self.engine) as session:
            total = len(session.exec(count_query).all())
            # 分页查询，按更新时间倒序
            sessions = session.exec(
                query.order_by(desc(ChatSession.updated_at))
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            
            return list(sessions), total
    
    def get_session(self, session_id: int) -> Optional[ChatSession]:
        """获取指定会话"""
        with Session(self.engine) as session:
            return session.get(ChatSession, session_id)
    
    def update_session(self, session_id: int, name: str = None, metadata: Dict[str, Any] = None) -> Optional[ChatSession]:
        """
        更新会话信息
        
        Args:
            session_id: 会话ID
            name: 新的会话名称
            metadata: 新的元数据
            
        Returns:
            更新后的会话对象
        """
        with Session(self.engine) as session:
            session_obj = session.get(ChatSession, session_id)
            if not session_obj or not session_obj.is_active:
                return None
                
            if name is not None:
                session_obj.name = name
            if metadata is not None:
                session_obj.metadata_json = metadata
                
            session_obj.updated_at = datetime.now()
            
            session.add(session_obj)
            session.commit()
            session.refresh(session_obj)
            
            return session_obj
    
    def delete_session(self, session_id: int) -> bool:
        """
        软删除会话（将is_active设为False）
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否删除成功
        """
        with Session(self.engine) as session:
            session_obj = session.get(ChatSession, session_id)
            if not session_obj:
                return False
                
            session_obj.is_active = False
            session_obj.updated_at = datetime.now()
            
            session.add(session_obj)
            session.commit()
            
            return True

    # ==================== 场景管理 ====================
    
    def get_scenario_id_by_name(self, name: str) -> Optional[int]:
        """
        根据场景名称获取场景ID
        
        Args:
            name: 场景名称（如"co_reading"）
            
        Returns:
            场景ID，如果未找到则返回None
        """
        from db_mgr import Scenario
        with Session(self.engine) as session:
            stmt = select(Scenario).where(Scenario.name == name)
            scenario = session.exec(stmt).first()
            return scenario.id if scenario else None

    def update_session_scenario(
        self, 
        session_id: int, 
        scenario_id: Optional[int], 
        metadata: Dict[str, Any] = None
    ) -> Optional[ChatSession]:
        """
        更新会话的场景配置
        
        Args:
            session_id: 会话ID
            scenario_id: 场景ID，None表示清除场景
            metadata: 额外的元数据（如PDF路径等）
            
        Returns:
            更新后的会话对象
        """
        with Session(self.engine) as session:
            session_obj = session.get(ChatSession, session_id)
            if not session_obj or not session_obj.is_active:
                return None
            
            # 更新scenario_id
            session_obj.scenario_id = scenario_id
            
            # 合并元数据
            if metadata is not None:
                current_metadata = {}
                if session_obj.metadata_json:
                    # metadata_json是JSON列，已经自动反序列化为dict，无需手动json.loads
                    if isinstance(session_obj.metadata_json, dict):
                        current_metadata = session_obj.metadata_json
                    else:
                        # 兼容旧数据：如果是字符串则尝试解析
                        try:
                            current_metadata = json.loads(session_obj.metadata_json)
                        except (json.JSONDecodeError, TypeError):
                            current_metadata = {}
                
                # 合并新的元数据
                current_metadata.update(metadata)
                # 直接赋值dict对象，SQLAlchemy的JSON列会自动序列化
                session_obj.metadata_json = current_metadata
            
            session_obj.updated_at = datetime.now()
            
            session.add(session_obj)
            session.commit()
            session.refresh(session_obj)
            
            return session_obj
    
    # 给定会话增加和减少工具
    def change_session_tools(
            self,
            session_id: int,
            add_tools: List[str] = None,
            remove_tools: List[str] = None
    ) -> bool:
        """
        增加或减少会话可用的工具
        
        Args:
            session_id: 会话ID
            add_tools: 需要添加的工具ID列表
            remove_tools: 需要移除的工具ID列表
            
        Returns:
            是否操作成功
        """
        with Session(self.engine) as session:
            session_obj = session.get(ChatSession, session_id)
            if not session_obj:
                return False
            
            current_tools = set(session_obj.selected_tool_names or [])
            
            if add_tools:
                current_tools.update(add_tools)
            if remove_tools:
                current_tools.difference_update(remove_tools)
            
            session_obj.selected_tool_names = list(current_tools)
            session_obj.updated_at = datetime.now()
            
            session.add(session_obj)
            session.commit()
            
            return True

    # ==================== 消息管理 ====================
    
    def save_message(
        self, 
        session_id: int, 
        message_id: str, 
        role: str, 
        content: str = None,
        parts: List[Dict[str, Any]] = None,
        metadata: Dict[str, Any] = None,
        sources: List[Dict[str, Any]] = None
    ) -> ChatMessage:
        """
        保存聊天消息
        
        Args:
            session_id: 会话ID
            message_id: 消息唯一ID
            role: 消息角色（user/assistant/tool）
            content: 消息文本内容
            parts: UIMessage.parts数组
            metadata: 消息元数据
            sources: RAG来源信息
            
        Returns:
            保存的消息对象
        """
        message = ChatMessage(
            session_id=session_id,
            message_id=message_id,
            role=role,
            content=content,
            parts=parts or [],
            metadata_json=metadata or {},
            sources=sources or []
        )
        with Session(self.engine) as session:
            session.add(message)
            session.commit()
            session.refresh(message)

        # 更新会话的updated_at
        self._update_session_timestamp(session_id)
        
        return message
    
    def get_messages(
        self, 
        session_id: int, 
        page: int = 1, 
        page_size: int = 30,
        latest_first: bool = True
    ) -> Tuple[List[ChatMessage], int]:
        """
        获取会话的消息列表
        
        Args:
            session_id: 会话ID
            page: 页码
            page_size: 每页大小
            latest_first: 是否最新消息在前
            
        Returns:
            (消息列表, 总数量)
        """
        # 获取总数
        with Session(self.engine) as session:
            total = len(session.exec(
                select(ChatMessage.id).where(ChatMessage.session_id == session_id)
            ).all())
            
            # 分页查询
            query = select(ChatMessage).where(ChatMessage.session_id == session_id)
            
            if latest_first:
                query = query.order_by(desc(ChatMessage.created_at))
            else:
                query = query.order_by(ChatMessage.created_at)
                
            messages = session.exec(
                query.offset((page - 1) * page_size).limit(page_size)
            ).all()
            
            return list(messages), total
    
    def get_recent_messages(self, session_id: int, limit: int = 10) -> List[ChatMessage]:
        """获取会话的最近N条消息，用作恢复聊天现场"""
        with Session(self.engine) as session:
            messages = session.exec(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(desc(ChatMessage.created_at))
                .limit(limit)
            ).all()
        
            # 返回时间正序的消息
            return list(reversed(messages))

    # ==================== Pin文件管理 ====================
    
    def pin_file(
        self, 
        session_id: int, 
        file_path: str, 
        file_name: str, 
        metadata: Dict[str, Any] = None
    ) -> ChatSessionPinFile:
        """
        为会话Pin一个文件
        
        Args:
            session_id: 会话ID
            file_path: 文件路径
            file_name: 文件名
            metadata: 文件元数据
            
        Returns:
            创建的Pin文件对象
        """
        # 检查是否已经Pin过
        with Session(self.engine) as session:
            existing = session.exec(
                select(ChatSessionPinFile)
                .where(and_(
                    ChatSessionPinFile.session_id == session_id,
                    ChatSessionPinFile.file_path == file_path
                ))
            ).first()
            
            if existing:
                return existing
            
        pin_file = ChatSessionPinFile(
            session_id=session_id,
            file_path=file_path,
            file_name=file_name,
            metadata_json=metadata or {}
        )
        with Session(self.engine) as session:
            session.add(pin_file)
            session.commit()
            session.refresh(pin_file)

        # 更新会话时间戳
        self._update_session_timestamp(session_id)
        
        return pin_file
    
    def unpin_file(self, session_id: int, file_path: str) -> bool:
        """
        取消Pin文件
        
        Args:
            session_id: 会话ID
            file_path: 文件路径
            
        Returns:
            是否成功取消
        """
        with Session(self.engine) as session:
            pin_file = session.exec(
                select(ChatSessionPinFile)
                .where(and_(
                    ChatSessionPinFile.session_id == session_id,
                    ChatSessionPinFile.file_path == file_path
                ))
            ).first()
            
            if not pin_file:
                return False
                
            session.delete(pin_file)
            session.commit()
        
        # 更新会话时间戳
        self._update_session_timestamp(session_id)
        
        return True
    
    def get_pinned_files(self, session_id: int) -> List[ChatSessionPinFile]:
        """获取会话的Pin文件列表"""
        with Session(self.engine) as session:
            return list(session.exec(
                select(ChatSessionPinFile)
                .where(ChatSessionPinFile.session_id == session_id)
                .order_by(ChatSessionPinFile.pinned_at)
            ).all())

    def get_pinned_document_ids(self, session_id: int) -> List[int]:
        """
        获取会话Pin文件对应的文档ID列表
        用于RAG检索时限定搜索范围
        
        Returns:
            List[int]: 文档ID列表，如果找不到对应文档则跳过
        """
        from db_mgr import Document
        
        # 获取session的所有pin文件路径
        pin_files = self.get_pinned_files(session_id)
        if not pin_files:
            return []
        
        # 通过file_path查找对应的Document记录
        document_ids = []
        file_paths = [pf.file_path for pf in pin_files]
        with Session(self.engine) as session:
            documents = session.exec(
                select(Document)
                .where(Document.file_path.in_(file_paths))
            ).all()

            # 返回文档ID列表
            document_ids = [doc.id for doc in documents]
        
        logger.debug(f"会话 {session_id} Pin文件: {len(pin_files)}个, 对应文档: {len(document_ids)}个")
        return document_ids

    # ==================== 辅助方法 ====================
    
    def _update_session_timestamp(self, session_id: int):
        """更新会话的updated_at时间戳"""
        with Session(self.engine) as session:
            session_obj = session.get(ChatSession, session_id)
            if session_obj:
                session_obj.updated_at = datetime.now()
                session.add(session_obj)
                session.commit()
    
    def get_session_stats(self, session_id: int) -> Dict[str, Any]:
        """
        获取会话统计信息
        
        Returns:
            统计信息字典：消息数量、Pin文件数量等
        """
        # 消息数量
        with Session(self.engine) as session:
            message_count = len(session.exec(
                select(ChatMessage.id).where(ChatMessage.session_id == session_id)
            ).all())
            
            # Pin文件数量
            pinned_file_count = len(session.exec(
                select(ChatSessionPinFile.id).where(ChatSessionPinFile.session_id == session_id)
            ).all())
            
            return {
                "message_count": message_count,
                "pinned_file_count": pinned_file_count
            }
