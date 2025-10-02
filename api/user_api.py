"""
用户API路由 - 处理OAuth回调和用户相关操作
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException, Header, Depends, Body
from fastapi.responses import HTMLResponse
from sqlalchemy import Engine
from user_mgr import UserManager
from bridge_events import BridgeEventSender

logger = logging.getLogger(__name__)


def get_router(get_engine) -> APIRouter:
    """创建并返回用户API路由"""
    router = APIRouter()
    bridge_emitter = BridgeEventSender()
    
    def get_user_manager(engine: Engine = Depends(get_engine)) -> UserManager:
        """获取用户管理器实例"""
        return UserManager(engine)
    
    @router.get("/api/auth/success")
    async def oauth_success_callback(
        request: Request,
        user_mgr: UserManager = Depends(get_user_manager)
    ):
        """
        接收Better-Auth的OAuth成功回调
        
        查询参数:
        - provider: OAuth提供商 (google/github)
        - oauth_id: OAuth用户唯一ID
        - email: 用户邮箱
        - name: 用户名
        - avatar_url: 头像URL (可选)
        
        返回: HTML页面告知用户成功，并通过Bridge事件通知前端
        """
        try:
            # 从查询参数获取用户信息
            params = dict(request.query_params)
            
            # 🔧 修复: provider 不应该有默认值,如果缺失应该报错
            provider = params.get('provider')
            oauth_id = params.get('oauth_id')
            email = params.get('email')
            name = params.get('name')
            avatar_url = params.get('avatar_url')
            
            logger.info(f"收到OAuth成功回调: provider={provider}, email={email}")
            
            # 验证所有必需参数
            if not all([provider, oauth_id, email, name]):
                logger.error(f"缺少必要参数: {params}")
                raise HTTPException(status_code=400, detail="缺少必要的用户信息参数(provider, oauth_id, email, name)")
            
            # 保存或更新用户信息
            user = user_mgr.get_or_create_user(
                oauth_provider=provider,
                oauth_id=oauth_id,
                email=email,
                name=name,
                avatar_url=avatar_url
            )
            
            # 准备发送给前端的用户数据
            user_data = {
                "success": True,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "avatar_url": user.avatar_url,
                    "oauth_provider": user.oauth_provider
                },
                "token": user.session_token,
                "token_expires_at": user.token_expires_at.isoformat() if user.token_expires_at else None
            }
            
            # 通过Bridge事件发送给Rust进程
            bridge_emitter.send_event('oauth-login-success', user_data)
            
            logger.info(f"OAuth登录成功事件已发送: user_id={user.id}, email={user.email}")
            
            # 返回成功页面
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>登录成功 - Knowledge Focus</title>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    * {{
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }}
                    body {{ 
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: #333;
                        display: flex; 
                        justify-content: center; 
                        align-items: center; 
                        height: 100vh; 
                        margin: 0; 
                        line-height: 1.6;
                    }}
                    .container {{ 
                        background: rgba(255, 255, 255, 0.95);
                        backdrop-filter: blur(10px);
                        border-radius: 20px;
                        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                        padding: 3rem 2.5rem;
                        text-align: center;
                        max-width: 90%;
                        width: 450px;
                        border: 1px solid rgba(255, 255, 255, 0.2);
                    }}
                    .icon {{
                        font-size: 4.5rem;
                        margin-bottom: 1.5rem;
                        display: block;
                        animation: bounce 1s ease;
                    }}
                    @keyframes bounce {{
                        0%, 100% {{ transform: translateY(0); }}
                        50% {{ transform: translateY(-20px); }}
                    }}
                    h1 {{
                        color: #2d3748;
                        font-size: 2rem;
                        margin-bottom: 1rem;
                        font-weight: 600;
                    }}
                    .subtitle {{
                        color: #718096;
                        font-size: 1.1rem;
                        margin-bottom: 2rem;
                        line-height: 1.8;
                    }}
                    .user-info {{
                        background: #f7fafc;
                        border: 1px solid #e2e8f0;
                        border-radius: 12px;
                        padding: 1.5rem;
                        margin: 1.5rem 0;
                        text-align: left;
                    }}
                    .user-info img {{
                        width: 60px;
                        height: 60px;
                        border-radius: 50%;
                        margin-bottom: 1rem;
                        border: 3px solid #fff;
                        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                    }}
                    .user-info p {{
                        color: #4a5568;
                        font-size: 0.95rem;
                        margin: 0.5rem 0;
                    }}
                    .user-info strong {{
                        color: #2d3748;
                    }}
                    .button {{
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        border: none;
                        padding: 14px 28px;
                        border-radius: 10px;
                        cursor: pointer;
                        margin: 0.5rem;
                        font-size: 1rem;
                        font-weight: 500;
                        transition: all 0.3s ease;
                        min-width: 140px;
                        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
                    }}
                    .button:hover {{
                        transform: translateY(-2px);
                        box-shadow: 0 6px 16px rgba(102, 126, 234, 0.4);
                    }}
                    .footer {{
                        margin-top: 2.5rem;
                        padding-top: 1.5rem;
                        border-top: 1px solid #e2e8f0;
                        font-size: 0.85rem;
                        color: #a0aec0;
                    }}
                    .status {{
                        display: inline-block;
                        padding: 0.5rem 1rem;
                        background: #c6f6d5;
                        border: 1px solid #9ae6b4;
                        border-radius: 6px;
                        color: #22543d;
                        font-size: 0.9rem;
                        margin-bottom: 1rem;
                        font-weight: 500;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="icon">🎉</div>
                    <h1>登录成功！</h1>
                    <div class="status">✓ 已连接到 Knowledge Focus</div>
                    <p class="subtitle">欢迎回来！正在同步您的账户信息...</p>
                    
                    <div class="user-info">
                        {f'<img src="{avatar_url}" alt="Avatar">' if avatar_url else ''}
                        <p><strong>用户名:</strong> {name}</p>
                        <p><strong>邮箱:</strong> {email}</p>
                        <p><strong>提供商:</strong> {provider.capitalize()}</p>
                    </div>
                    
                    <button class="button" onclick="window.close()">关闭窗口</button>
                    
                    <div class="footer">
                        Knowledge Focus · 智能知识管理平台
                    </div>
                </div>
                <script>
                    // 3秒后自动关闭窗口
                    setTimeout(() => {{
                        window.close();
                    }}, 3000);
                    
                    // 如果无法关闭窗口，显示提示
                    setTimeout(() => {{
                        const container = document.querySelector('.container');
                        const status = document.querySelector('.status');
                        if (container && status) {{
                            status.textContent = '✓ 同步完成';
                            const hint = document.createElement('p');
                            hint.style.cssText = 'margin-top: 1rem; color: #718096; font-size: 0.9rem;';
                            hint.textContent = '您可以关闭此窗口并返回应用';
                            container.querySelector('.footer').before(hint);
                        }}
                    }}, 3500);
                </script>
            </body>
            </html>
            """
            
            return HTMLResponse(content=html_content)
            
        except Exception as e:
            logger.error(f"处理OAuth回调失败: {e}", exc_info=True)
            
            # 发送错误事件
            error_data = {
                "success": False,
                "error": str(e)
            }
            bridge_emitter.send_event('oauth-login-error', error_data)
            
            # 返回错误页面
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>登录失败 - Knowledge Focus</title>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    * {{
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }}
                    body {{ 
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif;
                        background: linear-gradient(135deg, #fc466b 0%, #3f5efb 100%);
                        color: #333;
                        display: flex; 
                        justify-content: center; 
                        align-items: center; 
                        height: 100vh; 
                        margin: 0; 
                        line-height: 1.6;
                    }}
                    .container {{ 
                        background: rgba(255, 255, 255, 0.95);
                        backdrop-filter: blur(10px);
                        border-radius: 16px;
                        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                        padding: 3rem 2rem;
                        text-align: center;
                        max-width: 90%;
                        width: 400px;
                        border: 1px solid rgba(255, 255, 255, 0.2);
                    }}
                    .icon {{
                        font-size: 4rem;
                        margin-bottom: 1rem;
                        display: block;
                    }}
                    h1 {{
                        color: #e53e3e;
                        font-size: 1.75rem;
                        margin-bottom: 1rem;
                        font-weight: 600;
                    }}
                    .subtitle {{
                        color: #718096;
                        font-size: 1rem;
                        margin-bottom: 1rem;
                    }}
                    .error-details {{
                        background: #fed7d7;
                        border: 1px solid #feb2b2;
                        border-radius: 6px;
                        padding: 0.75rem;
                        margin: 1rem 0;
                        font-size: 0.85rem;
                        color: #c53030;
                    }}
                    .button {{
                        background: linear-gradient(135deg, #fc466b 0%, #3f5efb 100%);
                        color: white;
                        border: none;
                        padding: 12px 24px;
                        border-radius: 8px;
                        cursor: pointer;
                        margin: 0.5rem;
                        font-size: 0.9rem;
                        font-weight: 500;
                        transition: all 0.3s ease;
                        min-width: 120px;
                    }}
                    .button:hover {{
                        transform: translateY(-2px);
                        box-shadow: 0 4px 12px rgba(252, 70, 107, 0.4);
                    }}
                    .footer {{
                        margin-top: 2rem;
                        padding-top: 1rem;
                        border-top: 1px solid #e2e8f0;
                        font-size: 0.8rem;
                        color: #a0aec0;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="icon">❌</div>
                    <h1>登录失败</h1>
                    <p class="subtitle">处理OAuth回调时发生错误</p>
                    
                    <div class="error-details">
                        错误信息: {str(e)}
                    </div>
                    
                    <button class="button" onclick="window.close()">关闭窗口</button>
                    
                    <div class="footer">
                        Knowledge Focus · 如需帮助请联系技术支持
                    </div>
                </div>
            </body>
            </html>
            """
            
            return HTMLResponse(content=html_content, status_code=500)
    
    @router.get("/api/user/profile")
    async def get_user_profile(
        authorization: str = Header(None),
        user_mgr: UserManager = Depends(get_user_manager)
    ):
        """
        获取当前用户信息
        
        Headers:
        - Authorization: Bearer {token}
        
        返回: 用户信息
        """
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="未提供有效的认证token")
        
        token = authorization.replace("Bearer ", "")
        user = user_mgr.get_user_by_token(token)
        
        if not user:
            raise HTTPException(status_code=401, detail="Token无效或已过期")
        
        return {
            "success": True,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "avatar_url": user.avatar_url,
                "oauth_provider": user.oauth_provider,
                "created_at": user.created_at.isoformat(),
                "updated_at": user.updated_at.isoformat()
            }
        }
    
    @router.post("/api/user/logout")
    async def logout_user(
        data: Dict[str, Any] = Body(...),
        user_mgr: UserManager = Depends(get_user_manager)
    ):
        """
        用户退出登录
        
        请求体:
        - user_id: 用户ID
        
        返回: 操作结果
        """
        user_id = data.get("user_id")
        
        if not user_id:
            raise HTTPException(status_code=400, detail="缺少user_id参数")
        
        success = user_mgr.logout_user(user_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="用户不存在")
        
        return {
            "success": True,
            "message": "退出登录成功"
        }
    
    @router.post("/api/user/validate-token")
    async def validate_token(
        data: Dict[str, Any] = Body(...),
        user_mgr: UserManager = Depends(get_user_manager)
    ):
        """
        验证token有效性
        
        请求体:
        - token: JWT token字符串
        
        返回: 验证结果
        """
        token = data.get("token")
        
        if not token:
            raise HTTPException(status_code=400, detail="缺少token参数")
        
        result = user_mgr.validate_token(token)
        
        return result
    
    return router
