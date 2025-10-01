"""
用户管理器 - 处理OAuth用户的CRUD操作
"""

import logging
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import Engine
from sqlmodel import Session, select
from db_mgr import User

logger = logging.getLogger(__name__)

# JWT 配置 - 在生产环境应该从环境变量读取
JWT_SECRET = "your-secret-key-change-in-production"  # TODO: 从环境变量读取
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_MONTHS = 6


class UserManager:
    """用户管理器类"""
    
    def __init__(self, engine: Engine):
        self.engine = engine
    
    def generate_jwt_token(self, user_id: int, email: str, name: str) -> str:
        """生成JWT token
        
        Args:
            user_id: 用户ID
            email: 用户邮箱
            name: 用户名
            
        Returns:
            JWT token字符串
        """
        expire = datetime.utcnow() + timedelta(days=30 * TOKEN_EXPIRE_MONTHS)
        payload = {
            "user_id": user_id,
            "email": email,
            "name": name,
            "exp": expire
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return token
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证JWT token
        
        Args:
            token: JWT token字符串
            
        Returns:
            解码后的payload，如果token无效返回None
        """
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token已过期")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"无效的Token: {e}")
            return None
    
    def get_or_create_user(
        self,
        oauth_provider: str,
        oauth_id: str,
        email: str,
        name: str,
        avatar_url: Optional[str] = None
    ) -> User:
        """获取或创建用户，每次登录都更新用户信息和token
        
        Args:
            oauth_provider: OAuth提供商 (google/github)
            oauth_id: OAuth用户唯一ID
            email: 用户邮箱
            name: 用户名
            avatar_url: 头像URL
            
        Returns:
            用户对象
        """
        with Session(self.engine) as session:
            # 尝试查找现有用户
            statement = select(User).where(
                User.oauth_provider == oauth_provider,
                User.oauth_id == oauth_id
            )
            user = session.exec(statement).first()
            
            if user:
                # 用户存在，更新信息和token
                logger.info(f"用户已存在，更新信息: {email}")
                user.email = email
                user.name = name
                user.avatar_url = avatar_url
                user.updated_at = datetime.now()
                
                # 生成新的token
                token = self.generate_jwt_token(user.id, email, name)
                user.session_token = token
                user.token_expires_at = datetime.utcnow() + timedelta(days=30 * TOKEN_EXPIRE_MONTHS)
                
                session.add(user)
                session.commit()
                session.refresh(user)
                
                logger.info(f"用户信息已更新: {email}, User ID: {user.id}")
            else:
                # 用户不存在，创建新用户
                logger.info(f"创建新用户: {email}")
                
                # 生成初始token
                # 注意：此时user.id还不存在，需要先插入数据库获取ID后再生成token
                user = User(
                    oauth_provider=oauth_provider,
                    oauth_id=oauth_id,
                    email=email,
                    name=name,
                    avatar_url=avatar_url,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                
                session.add(user)
                session.commit()
                session.refresh(user)
                
                # 现在可以生成带有user_id的token了
                token = self.generate_jwt_token(user.id, email, name)
                user.session_token = token
                user.token_expires_at = datetime.utcnow() + timedelta(days=30 * TOKEN_EXPIRE_MONTHS)
                
                session.add(user)
                session.commit()
                session.refresh(user)
                
                logger.info(f"新用户创建成功: {email}, User ID: {user.id}")
            
            return user
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """根据ID获取用户
        
        Args:
            user_id: 用户ID
            
        Returns:
            用户对象，如果不存在返回None
        """
        with Session(self.engine) as session:
            user = session.get(User, user_id)
            return user
    
    def get_user_by_token(self, token: str) -> Optional[User]:
        """根据token获取用户
        
        Args:
            token: JWT token字符串
            
        Returns:
            用户对象，如果token无效或用户不存在返回None
        """
        payload = self.verify_token(token)
        if not payload:
            return None
        
        user_id = payload.get("user_id")
        if not user_id:
            return None
        
        return self.get_user_by_id(user_id)
    
    def logout_user(self, user_id: int) -> bool:
        """用户退出登录，清除token
        
        Args:
            user_id: 用户ID
            
        Returns:
            是否成功
        """
        with Session(self.engine) as session:
            user = session.get(User, user_id)
            if not user:
                logger.warning(f"用户不存在: {user_id}")
                return False
            
            # 清除token
            user.session_token = None
            user.token_expires_at = None
            user.updated_at = datetime.now()
            
            session.add(user)
            session.commit()
            
            logger.info(f"用户已退出登录: {user.email}, User ID: {user_id}")
            return True
    
    def validate_token(self, token: str) -> Dict[str, Any]:
        """验证token有效性
        
        Args:
            token: JWT token字符串
            
        Returns:
            包含验证结果的字典
        """
        payload = self.verify_token(token)
        if not payload:
            return {
                "valid": False,
                "message": "Token无效或已过期"
            }
        
        user_id = payload.get("user_id")
        user = self.get_user_by_id(user_id)
        
        if not user:
            return {
                "valid": False,
                "message": "用户不存在"
            }
        
        if user.session_token != token:
            return {
                "valid": False,
                "message": "Token已失效，请重新登录"
            }
        
        return {
            "valid": True,
            "user_id": user.id,
            "email": user.email,
            "name": user.name,
            "avatar_url": user.avatar_url
        }
