"""
文件搜索工具 - 帮助AI找到用户想要的文件
"""

from typing import Dict
from pydantic_ai import RunContext
from backend_tool_caller import g_backend_tool_caller
import logging

logger = logging.getLogger()

async def search_pdf_files(ctx: RunContext[int], description: str, limit: int = 5) -> Dict:
    """
    根据用户描述搜索PDF文件
    
    Args:
        ctx: 运行上下文，包含session_id
        description: 用户对文件的描述，比如"关于AI的文档"、"那个PDF文件"等
        limit: 返回结果的最大数量
        
    Returns:
        包含匹配文件列表的字典
    """
    try:
        session_id = ctx.deps
        logger.info(f"Session {session_id}: 搜索PDF文件，描述: {description}")
        
        # 调用前端工具进行文件搜索
        result = await g_backend_tool_caller.call_frontend_tool(
            "search_pdf_files",
            description=description,
            limit=limit,
            sessionId=session_id
        )
        
        if isinstance(result, dict) and result.get("success"):
            files = result.get("files", [])
            logger.info(f"找到 {len(files)} 个匹配的PDF文件")
            return {
                "success": True,
                "files": files,
                "message": f"找到 {len(files)} 个匹配的PDF文件"
            }
        else:
            return {
                "success": False,
                "files": [],
                "message": "没有找到匹配的PDF文件"
            }
            
    except Exception as e:
        logger.error(f"搜索PDF文件失败: {e}")
        return {
            "success": False,
            "files": [],
            "message": f"搜索失败: {str(e)}"
        }

async def get_recent_pdf_files(ctx: RunContext[int], limit: int = 10) -> Dict:
    """
    获取最近访问或下载的PDF文件
    
    Args:
        ctx: 运行上下文，包含session_id
        limit: 返回结果的最大数量
        
    Returns:
        包含最近PDF文件列表的字典
    """
    try:
        session_id = ctx.deps
        logger.info(f"Session {session_id}: 获取最近的PDF文件")
        
        result = await g_backend_tool_caller.call_frontend_tool(
            "get_recent_pdf_files",
            limit=limit,
            sessionId=session_id
        )
        
        if isinstance(result, dict) and result.get("success"):
            files = result.get("files", [])
            return {
                "success": True,
                "files": files,
                "message": f"找到 {len(files)} 个最近的PDF文件"
            }
        else:
            return {
                "success": False,
                "files": [],
                "message": "没有找到最近的PDF文件"
            }
            
    except Exception as e:
        logger.error(f"获取最近PDF文件失败: {e}")
        return {
            "success": False,
            "files": [],
            "message": f"获取失败: {str(e)}"
        }

async def browse_folder_for_pdfs(ctx: RunContext[int], folder_path: str = "") -> Dict:
    """
    浏览指定文件夹中的PDF文件
    
    Args:
        ctx: 运行上下文，包含session_id
        folder_path: 要浏览的文件夹路径，空字符串表示常用文件夹
        
    Returns:
        包含文件夹中PDF文件列表的字典
    """
    try:
        session_id = ctx.deps
        logger.info(f"Session {session_id}: 浏览文件夹 {folder_path} 中的PDF文件")
        
        result = await g_backend_tool_caller.call_frontend_tool(
            "browse_folder_for_pdfs",
            folderPath=folder_path,
            sessionId=session_id
        )
        
        if isinstance(result, dict) and result.get("success"):
            files = result.get("files", [])
            folder = result.get("currentFolder", folder_path)
            return {
                "success": True,
                "files": files,
                "currentFolder": folder,
                "message": f"在 {folder} 中找到 {len(files)} 个PDF文件"
            }
        else:
            return {
                "success": False,
                "files": [],
                "currentFolder": folder_path,
                "message": f"无法浏览文件夹 {folder_path}"
            }
            
    except Exception as e:
        logger.error(f"浏览文件夹失败: {e}")
        return {
            "success": False,
            "files": [],
            "currentFolder": folder_path,
            "message": f"浏览失败: {str(e)}"
        }
