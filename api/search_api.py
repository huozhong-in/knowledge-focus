from fastapi import APIRouter, Depends, Body
from sqlalchemy import Engine
from typing import Dict, Any
from lancedb_mgr import LanceDBMgr
from models_mgr import ModelsMgr
from search_mgr import SearchManager
import logging
logger = logging.getLogger()

def get_router(get_engine: Engine, base_dir: str) -> APIRouter:
    router = APIRouter()

    def get_lancedb_manager() -> LanceDBMgr:
        """获取LanceDB管理器实例"""
        return LanceDBMgr(base_dir=base_dir)
    
    def get_models_manager(engine: Engine = Depends(get_engine)) -> ModelsMgr:
        return ModelsMgr(engine=engine, base_dir=base_dir)

    def get_search_manager(engine: Engine = Depends(get_engine)) -> SearchManager:
        return SearchManager(engine=engine, lancedb_mgr=get_lancedb_manager(), models_mgr=get_models_manager(engine))

    # =============================================================================
    # 📊 向量内容搜索API端点
    # =============================================================================
    @router.post("/search/content")
    def search_document_content(
        request: Dict[str, Any] = Body(...),
        search_mgr: SearchManager = Depends(get_search_manager)
    ):
        """
        文档内容的自然语言检索
        
        参数:
        - query: 自然语言查询文本
        - top_k: 返回的最大结果数 (可选，默认10)
        - document_ids: 文档ID过滤列表 (可选)
        - distance_threshold: 相似度阈值 (可选)
        
        返回:
        - success: 是否成功
        - results: 格式化的检索结果
        - query_info: 查询元信息
        """
        try:
            # 提取参数
            query = request.get("query", "").strip()
            top_k = request.get("top_k", 10)
            document_ids = request.get("document_ids")
            distance_threshold = request.get("distance_threshold")
            
            logger.info(f"[SEARCH API] Content search request: '{query[:50]}...'")
            
            # 基础验证
            if not query:
                return {
                    "success": False,
                    "error": "查询内容不能为空",
                    "results": None
                }
            
            # 执行搜索
            search_result = search_mgr.search_documents(
                query=query,
                top_k=top_k,
                document_ids=document_ids,
                distance_threshold=distance_threshold
            )
            
            # 返回结果
            logger.info(f"[SEARCH API] Search completed with {search_result.get('success', False)} status")
            return search_result
            
        except Exception as e:
            logger.error(f"[SEARCH API] Content search failed: {e}")
            return {
                "success": False,
                "error": f"搜索失败: {str(e)}",
                "results": None
            }

    @router.post("/documents/{document_id}/search/content")  
    def search_document_content_by_id(
        document_id: int,
        request: Dict[str, Any] = Body(...),
        search_mgr: SearchManager = Depends(get_search_manager)
    ):
        """
        在指定文档内进行向量内容检索
        
        参数:
        - document_id: 文档ID
        - query: 自然语言查询文本
        - top_k: 返回的最大结果数 (可选，默认10)
        - distance_threshold: 相似度阈值 (可选)
        
        返回:
        - success: 是否成功
        - results: 格式化的检索结果
        - query_info: 查询元信息
        """
        try:
            # 提取参数
            query = request.get("query", "").strip()
            top_k = request.get("top_k", 10)
            distance_threshold = request.get("distance_threshold")
            
            logger.info(f"[SEARCH API] Document {document_id} content search: '{query[:50]}...'")
            
            # 基础验证
            if not query:
                return {
                    "success": False,
                    "error": "查询内容不能为空",
                    "results": None
                }
            
            # 执行搜索（限制在指定文档）
            search_result = search_mgr.search_documents(
                query=query,
                top_k=top_k,
                document_ids=[document_id],  # 限制在指定文档
                distance_threshold=distance_threshold
            )
            
            # 添加文档ID信息到结果中
            if search_result.get("success", False):
                if "query_info" not in search_result:
                    search_result["query_info"] = {}
                search_result["query_info"]["target_document_id"] = document_id
            
            logger.info(f"[SEARCH API] Document {document_id} search completed")
            return search_result
            
        except Exception as e:
            logger.error(f"[SEARCH API] Document {document_id} content search failed: {e}")
            return {
                "success": False,
                "error": f"文档内搜索失败: {str(e)}",
                "results": None
            }


    return router
