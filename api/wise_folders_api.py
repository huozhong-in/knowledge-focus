from fastapi import APIRouter, Depends, FastAPI
from typing import Dict, Any, List
import logging
import traceback
from sqlmodel import Session, create_engine, select
from db_mgr import Task
from refine_mgr import RefineManager
import uvicorn
import sys
import os
import json

# 设置日志记录器
logger = logging.getLogger(__name__)

def get_session():
    """获取数据库会话"""
    # 当作为独立应用运行时，使用环境变量或默认路径
    if __name__ == "__main__":
        db_path = os.environ.get("DB_PATH", "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db")
        db_path = os.path.expanduser(db_path)
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        with Session(engine) as session:
            yield session
    # 当作为模块被导入时，假设外部应用(main.py)会提供其自身的session依赖
    else:
        # 这个函数在被导入时应该不会被调用，因为路由器会使用主应用的session
        # 仅用于独立运行时的情况
        raise RuntimeError("当作为模块导入时，请使用外部应用提供的session依赖")
    
# 创建一个函数，用于获取路由器
# 这样可以在导入时传入外部的session依赖
def get_router(external_get_session=None):
    """获取智慧文件夹API路由器
    
    Args:
        external_get_session: 外部提供的会话依赖函数，当作为模块导入时使用
            
    Returns:
        APIRouter: 配置好的路由器实例
    """
    # 创建路由器
    router = APIRouter(
        prefix="/wise-folders",
        tags=["wise-folders"],
        responses={404: {"description": "未找到"}},
    )
    
    # 使用外部提供的会话依赖或默认的会话依赖
    session_dependency = external_get_session if external_get_session else get_session
    
    # 定义路由器内部的依赖函数
    def get_refine_manager_for_router(session: Session = Depends(session_dependency)):
        """获取文件精炼管理类实例"""
        return RefineManager(session)
    
    # 定义路由
    @router.get("/categories")
    def get_categories(
        refine_mgr: RefineManager = Depends(get_refine_manager_for_router)
    ):
        """获取所有智慧文件夹分类
        
        Returns:
            分类列表
        """
        try:
            categories = refine_mgr.get_all_wise_folder_categories()
            return {
                "success": True,
                "categories_count": len(categories),
                "categories": categories
            }
        except Exception as e:
            logger.error(f"获取智慧文件夹分类失败: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "message": f"获取智慧文件夹分类失败: {str(e)}"
            }

    @router.get("/folders/{category_type}")
    def get_folders_by_category(
        category_type: str,
        refine_mgr: RefineManager = Depends(get_refine_manager_for_router)
    ):
        """获取指定分类下的智慧文件夹
        
        Args:
            category_type: 分类类型，如 project, category, tag, time, other
            
        Returns:
            智慧文件夹列表
        """
        try:
            folders = refine_mgr.get_folders_by_category(category_type)
            return {
                "success": True,
                "category_type": category_type,
                "folders_count": len(folders),
                "folders": folders
            }
        except Exception as e:
            logger.error(f"获取分类 {category_type} 下的智慧文件夹失败: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "message": f"获取分类下的智慧文件夹失败: {str(e)}"
            }

    @router.get("/files")
    def get_files_in_folder(
        folder_type: str,
        criteria: str,
        refine_mgr: RefineManager = Depends(get_refine_manager_for_router)
    ):
        """获取智慧文件夹中的文件
        
        Args:
            folder_type: 文件夹类型，如 project, category, tag, time, file_size
            criteria: JSON格式的条件参数
            
        Returns:
            文件列表
        """
        try:
            criteria_dict = json.loads(criteria)
            files = refine_mgr.get_files_by_folder(folder_type, criteria_dict)
            
            return {
                "success": True,
                "folder_type": folder_type,
                "criteria": criteria_dict,
                "files_count": len(files),
                "files": files
            }
        except Exception as e:
            logger.error(f"获取文件夹文件失败: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "message": f"获取文件夹文件失败: {str(e)}"
            }
    
    # 保留旧的API端点以向后兼容
    @router.get("/{task_id}")
    def get_wise_folders_legacy(
        task_id: str,
        refine_mgr: RefineManager = Depends(get_refine_manager_for_router)
    ):
        """获取指定任务的智慧文件夹（旧API，保留向后兼容）
        
        Args:
            task_id: 任务ID，如果为"all"则返回所有智慧文件夹
            
        Returns:
            智慧文件夹列表
        """
        try:
            # 获取所有分类
            categories = refine_mgr.get_all_wise_folder_categories()
            
            # 获取所有文件夹
            all_folders = []
            for category in categories:
                folders = refine_mgr.get_folders_by_category(category["type"])
                all_folders.extend(folders)
            
            return {
                "success": True,
                "task_id": task_id,
                "folders_count": len(all_folders),
                "folders": all_folders
            }
        except Exception as e:
            logger.error(f"获取智慧文件夹失败: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "message": f"获取智慧文件夹失败: {str(e)}"
            }

    @router.get("/{task_id}/files")
    def get_files_in_folder_legacy(
        task_id: str,
        folder_type: str,
        criteria: str,
        refine_mgr: RefineManager = Depends(get_refine_manager_for_router)
    ):
        """获取智慧文件夹中的文件（旧API，保留向后兼容）
        
        Args:
            task_id: 任务ID
            folder_type: 文件夹类型，如 category, tag, project, topic, entity
            criteria: JSON格式的条件参数
            
        Returns:
            文件列表
        """
        try:
            criteria_dict = json.loads(criteria)
            files = refine_mgr.get_files_by_folder(folder_type, criteria_dict)
            
            return {
                "success": True,
                "task_id": task_id,
                "folder_type": folder_type,
                "criteria": criteria_dict,
                "files_count": len(files),
                "files": files
            }
        except Exception as e:
            logger.error(f"获取文件夹文件失败: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "message": f"获取文件夹文件失败: {str(e)}"
            }
    
    return router

# 默认路由器（用于独立运行时）
router = get_router()

# 此文件可以独立运行，也可以作为模块导入
app = FastAPI(title="智慧文件夹API")

# 仅用于独立运行时，维持向后兼容
def get_refine_manager(session: Session = Depends(get_session)):
    """获取文件精炼管理类实例（用于独立运行时）"""
    return RefineManager(session)

# 为独立运行的应用添加路由
if __name__ == "__main__":
    # 为独立运行的应用添加路由
    app.include_router(router)
    
    # 独立运行时的启动代码
    import argparse
    
    parser = argparse.ArgumentParser(description="智慧文件夹API服务")
    parser.add_argument("--port", type=int, default=60316, help="API服务监听端口")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="API服务监听地址")
    parser.add_argument("--db-path", type=str, default="/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db", help="数据库文件路径")

    args = parser.parse_args()
    
    # 设置环境变量，供get_session使用
    os.environ["DB_PATH"] = args.db_path
    
    # 启动服务器
    print(f"独立模式启动 智慧文件夹API服务: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
