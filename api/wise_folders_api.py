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

# 设置日志记录器
logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(
    prefix="/wise-folders",
    tags=["wise-folders"],
    responses={404: {"description": "未找到"}},
)

# 此文件可以独立运行，也可以作为模块导入
app = FastAPI(title="智能文件夹API")

def get_session():
    """获取数据库会话"""
    db_path = os.environ.get("DB_PATH", "~/Library/Application Support/com.knowledge.focus/kf_data.db")
    db_path = os.path.expanduser(db_path)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    with Session(engine) as session:
        yield session

def get_refine_manager(session: Session = Depends(get_session)):
    """获取文件精炼管理类实例"""
    return RefineManager(session)

@router.get("/{task_id}")
def get_wise_folders(
    task_id: str,
    refine_mgr: RefineManager = Depends(get_refine_manager)
):
    """获取指定任务的智能文件夹
    
    Args:
        task_id: 任务ID
        
    Returns:
        智能文件夹列表
    """
    try:
        wise_folders = refine_mgr.get_wise_folders_by_task(task_id)
        return {
            "success": True,
            "task_id": task_id,
            "folders_count": len(wise_folders),
            "folders": wise_folders
        }
    except Exception as e:
        logger.error(f"获取智能文件夹失败: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "message": f"获取智能文件夹失败: {str(e)}"
        }

@router.get("/{task_id}/files")
def get_files_in_folder(
    task_id: str,
    folder_type: str,
    criteria: str,
    refine_mgr: RefineManager = Depends(get_refine_manager)
):
    """获取智能文件夹中的文件
    
    Args:
        task_id: 任务ID
        folder_type: 文件夹类型，如 category, tag, project, topic, entity
        criteria: JSON格式的条件参数
        
    Returns:
        文件列表
    """
    try:
        import json
        criteria_dict = json.loads(criteria)
        
        if folder_type == "category":
            files = refine_mgr.get_files_by_category(task_id, criteria_dict.get("category"))
        elif folder_type == "tag":
            files = refine_mgr.get_files_by_tag(task_id, criteria_dict.get("tag"))
        elif folder_type == "project":
            files = refine_mgr.get_files_by_project(task_id, criteria_dict.get("project"))
        elif folder_type == "topic":
            files = refine_mgr.get_files_by_topic(task_id, criteria_dict.get("topic"))
        elif folder_type == "entity":
            files = refine_mgr.get_files_by_entity(task_id, criteria_dict.get("entity"))
        elif folder_type == "time":
            files = refine_mgr.get_files_by_time_period(task_id, criteria_dict.get("time_period"))
        else:
            return {
                "success": False,
                "message": f"不支持的文件夹类型: {folder_type}"
            }
            
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
