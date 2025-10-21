from fastapi import APIRouter, Depends, Body
from sqlalchemy import Engine
from typing import List, Dict, Any
import logging
from tagging_mgr import TaggingMgr
from lancedb_mgr import LanceDBMgr
from models_mgr import ModelsMgr
from file_tagging_mgr import FileTaggingMgr

logger = logging.getLogger()

def get_router(get_engine: Engine, base_dir: str) -> APIRouter:
    router = APIRouter()

    def get_tagging_manager(engine: Engine = Depends(get_engine)) -> TaggingMgr:
        """FastAPI dependency to get a TaggingMgr instance."""
        lancedb_mgr = LanceDBMgr(base_dir=base_dir)
        models_mgr = ModelsMgr(engine=engine, base_dir=base_dir)
        return TaggingMgr(engine=engine, lancedb_mgr=lancedb_mgr, models_mgr=models_mgr)

    def get_file_tagging_manager(engine: Engine = Depends(get_engine)) -> FileTaggingMgr:
        """FastAPI dependency to get a FileTaggingMgr instance."""
        lancedb_mgr = LanceDBMgr(base_dir=base_dir)
        models_mgr = ModelsMgr(engine=engine, base_dir=base_dir)
        return FileTaggingMgr(engine=engine, lancedb_mgr=lancedb_mgr, models_mgr=models_mgr)

    @router.post("/tagging/search-files", response_model=List[Dict[str, Any]])
    async def search_files_by_tags(
        data: Dict[str, Any] = Body(...),
        tagging_mgr: TaggingMgr = Depends(get_tagging_manager)
    ):
        """
        Search for files by a list of tag names.
        """
        try:
            tag_names = data.get("tag_names", [])
            operator = data.get("operator", "AND")
            limit = data.get("limit", 50)
            offset = data.get("offset", 0)

            if not tag_names:
                return []

            logger.info(f"Searching files with tags: {tag_names}, operator: {operator}")
            results = tagging_mgr.search_files_by_tag_names(
                tag_names=tag_names,
                operator=operator,
                limit=limit,
                offset=offset
            )
            return results
        except Exception as e:
            logger.error(f"Error searching files by tags: {e}", exc_info=True)
            return []

    @router.get("/tagging/tag-cloud", response_model=Dict[str, Any])
    async def get_tag_cloud(
        limit: int = 50,
        min_weight: int = 1,
        tagging_mgr: TaggingMgr = Depends(get_tagging_manager),
        file_tagging_mgr: FileTaggingMgr = Depends(get_file_tagging_manager)
    ):
        """
        获取标签云数据，包含标签ID、名称、权重和类型。
        权重表示使用该标签的文件数量。
        
        返回格式:
        {
            "success": bool,
            "data": List[Dict], // 标签数据
            "error_type": str | null, // 错误类型: "model_not_configured" 或 null
            "message": str | null // 错误或成功消息
        }
        
        - **limit**: 最多返回的标签数量 (默认: 50)
        - **min_weight**: 最小权重阈值，只返回权重大于此值的标签 (默认: 1)
        """
        try:
            # 内置模型已配置，直接获取标签云数据
            # 如果模型正在加载中，标签可能为空，但不是错误状态
            logger.info(f"获取标签云数据，limit: {limit}, min_weight: {min_weight}")
            tag_cloud_data = tagging_mgr.get_tag_cloud_data(limit=limit, min_weight=min_weight)
            return {
                "success": True,
                "data": tag_cloud_data,
                "error_type": None,
                "message": f"{len(tag_cloud_data)} tags found"
            }
        except Exception as e:
            logger.error(f"获取标签云数据失败: {e}", exc_info=True)
            return {
                "success": False,
                "data": [],
                "error_type": "server_error",
                "message": f"服务器错误: {str(e)}"
            }

    return router
