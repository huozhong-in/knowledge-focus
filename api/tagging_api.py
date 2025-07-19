from fastapi import APIRouter, Depends, Body
from sqlmodel import Session
from typing import List, Dict, Any
import logging

from tagging_mgr import TaggingMgr
from lancedb_mgr import LanceDBMgr
from models_mgr import ModelsMgr

logger = logging.getLogger(__name__)

def get_router(get_session: callable) -> APIRouter:
    router = APIRouter()

    def get_tagging_manager(session: Session = Depends(get_session)) -> TaggingMgr:
        """FastAPI dependency to get a TaggingMgr instance."""
        # These dependencies will be resolved by FastAPI for each request.
        db_path = session.get_bind().url.database
        base_dir = "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in"
        lancedb_mgr = LanceDBMgr(base_dir=base_dir)
        models_mgr = ModelsMgr(session=session)
        return TaggingMgr(session=session, lancedb_mgr=lancedb_mgr, models_mgr=models_mgr)

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

    @router.get("/tagging/tag-cloud", response_model=List[Dict[str, Any]])
    async def get_tag_cloud(
        limit: int = 100,
        min_weight: int = 1,
        tagging_mgr: TaggingMgr = Depends(get_tagging_manager)
    ):
        """
        获取标签云数据，包含标签ID、名称、权重和类型。
        权重表示使用该标签的文件数量。
        
        - **limit**: 最多返回的标签数量 (默认: 100)
        - **min_weight**: 最小权重阈值，只返回权重大于此值的标签 (默认: 1)
        """
        try:
            logger.info(f"获取标签云数据，limit: {limit}, min_weight: {min_weight}")
            tag_cloud_data = tagging_mgr.get_tag_cloud_data(limit=limit, min_weight=min_weight)
            return tag_cloud_data
        except Exception as e:
            logger.error(f"获取标签云数据失败: {e}", exc_info=True)
            return []

    return router
