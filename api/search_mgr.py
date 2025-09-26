"""
搜索管理器 - P0核心功能
专门负责向量内容检索的查询处理和结果组织
"""

import logging
from typing import List, Dict, Any, Optional
from sqlmodel import Session, select
from sqlalchemy import Engine
from lancedb_mgr import LanceDBMgr
from models_mgr import ModelsMgr
from db_mgr import ParentChunk, Document

logger = logging.getLogger()

class QueryProcessor:
    """查询预处理器 - P0核心"""
    
    def __init__(self, models_mgr: ModelsMgr):
        self.models_mgr = models_mgr
    
    def clean_query(self, query: str) -> str:
        """基础文本清理和标准化"""
        if not query:
            return ""
        
        # 基础清理：去除多余空白、统一大小写
        cleaned = query.strip()
        
        # 移除多余的空白字符
        import re
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        logger.debug(f"Query cleaned: '{query}' -> '{cleaned}'")
        return cleaned
    
    def validate_query(self, query: str) -> tuple[bool, str]:
        """基础查询验证"""
        if not query or not query.strip():
            return False, "查询不能为空"
        
        # 长度限制验证
        if len(query) > 1000:
            return False, "查询文本过长，请控制在1000字符以内"
        
        if len(query.strip()) < 2:
            return False, "查询文本过短，请输入至少2个字符"
        
        return True, ""
    
    def generate_vector(self, query: str) -> List[float]:
        """生成查询向量"""
        try:
            vector = self.models_mgr.get_embedding(query)
            logger.debug(f"Generated vector for query: '{query[:50]}...'")
            return vector
        except Exception as e:
            logger.error(f"Failed to generate vector for query '{query}': {e}")
            raise
    
    def detect_query_type(self, query: str) -> str:
        """简单的问题类型识别"""
        query_lower = query.lower()
        
        # 图像相关关键词
        image_keywords = ['图片', '图像', '图表', '截图', '照片', '图', '示意图', '架构图']
        if any(keyword in query_lower for keyword in image_keywords):
            return "image"
        
        # 表格相关关键词  
        table_keywords = ['表格', '表', '数据', '统计', '列表']
        if any(keyword in query_lower for keyword in table_keywords):
            return "table"
        
        # 默认为文本查询
        return "text"


class ResultFormatter:
    """结果格式化器 - P0核心"""
    
    def __init__(self, engine: Engine):
        self.engine = engine

    def format_for_llm(self, search_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """组织检索结果为LLM友好格式"""
        if not search_results:
            return {
                "context": "",
                "sources": [],
                "total_chunks": 0
            }
        
        try:
            # 获取所有相关的父块内容
            parent_chunk_ids = [result['parent_chunk_id'] for result in search_results]
            parent_chunks = self._get_parent_chunks_content(parent_chunk_ids)
            
            # 组织上下文信息
            context_parts = []
            sources = []
            
            for i, result in enumerate(search_results):
                parent_chunk_id = result['parent_chunk_id']
                parent_chunk = parent_chunks.get(parent_chunk_id)
                
                if parent_chunk:
                    # 添加来源信息
                    source_info = {
                        "chunk_id": parent_chunk_id,
                        "document_id": result['document_id'], 
                        "chunk_type": parent_chunk.chunk_type,
                        "similarity": 1.0 - result.get('_distance', 0.0),  # 转换为相似度分数
                        "content_preview": result['retrieval_content'][:100] + "..."
                    }
                    sources.append(source_info)
                    
                    # 添加上下文内容
                    chunk_content = f"[来源-{i+1}] ({parent_chunk.chunk_type}类型)\n{parent_chunk.content}\n"
                    context_parts.append(chunk_content)
            
            # 合并所有上下文
            full_context = "\n" + "="*50 + "\n".join(context_parts)
            
            return {
                "context": full_context,
                "sources": sources,
                "total_chunks": len(search_results)
            }
            
        except Exception as e:
            logger.error(f"Failed to format search results: {e}")
            return {
                "context": "格式化检索结果时发生错误",
                "sources": [],
                "total_chunks": 0
            }
    
    def _get_parent_chunks_content(self, parent_chunk_ids: List[int]) -> Dict[int, ParentChunk]:
        """批量获取父块内容"""
        try:
            with Session(self.engine) as session:
                stmt = select(ParentChunk).where(ParentChunk.id.in_(parent_chunk_ids))
                chunks = session.exec(stmt).all()
                
                # 转换为字典以便快速查找
                chunks_dict = {chunk.id: chunk for chunk in chunks}
                logger.debug(f"Retrieved {len(chunks_dict)} parent chunks")
                return chunks_dict
            
        except Exception as e:
            logger.error(f"Failed to get parent chunks: {e}")
            return {}


class ContextEnhancer:
    """上下文增强器 - P0核心"""
    
    def __init__(self, engine: Engine):
        self.engine = engine

    def get_parent_chunks_by_ids(self, parent_chunk_ids: List[int]) -> List[Dict[str, Any]]:
        """通过parent_chunk_id获取完整父块内容"""
        try:
            with Session(self.engine) as session:
                stmt = select(ParentChunk).where(ParentChunk.id.in_(parent_chunk_ids))
                chunks = session.exec(stmt).all()
                
                # 转换为字典格式，包含chunk类型信息
                result = []
                for chunk in chunks:
                    chunk_data = {
                        "id": chunk.id,
                        "document_id": chunk.document_id, 
                        "chunk_type": chunk.chunk_type,
                        "content": chunk.content,
                        "metadata": chunk.metadata_json
                    }
                    result.append(chunk_data)
                
                logger.info(f"Retrieved {len(result)} parent chunks with full content")
                return result
            
        except Exception as e:
            logger.error(f"Failed to get parent chunks by IDs: {e}")
            return []
    
    def add_chunk_type_info(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """为检索结果添加chunk类型信息"""
        if not search_results:
            return search_results
        
        try:
            # 获取所有相关的父块
            parent_chunk_ids = [result['parent_chunk_id'] for result in search_results]
            parent_chunks = self._get_chunks_type_info(parent_chunk_ids)
            
            # 为每个结果添加类型信息
            enhanced_results = []
            for result in search_results:
                enhanced_result = result.copy()
                parent_chunk_id = result['parent_chunk_id']
                
                if parent_chunk_id in parent_chunks:
                    chunk_info = parent_chunks[parent_chunk_id]
                    enhanced_result['chunk_type'] = chunk_info['chunk_type']
                    enhanced_result['document_name'] = chunk_info['document_name']
                else:
                    enhanced_result['chunk_type'] = 'unknown'
                    enhanced_result['document_name'] = 'unknown'
                
                enhanced_results.append(enhanced_result)
            
            return enhanced_results
            
        except Exception as e:
            logger.error(f"Failed to add chunk type info: {e}")
            return search_results
    
    def _get_chunks_type_info(self, parent_chunk_ids: List[int]) -> Dict[int, Dict[str, str]]:
        """获取chunk类型和文档信息"""
        try:
            # 联查获取chunk和document信息
            with Session(self.engine) as session:
                stmt = select(ParentChunk, Document).join(
                    Document, ParentChunk.document_id == Document.id
                ).where(ParentChunk.id.in_(parent_chunk_ids))
                
                results = session.exec(stmt).all()
                
                chunks_info = {}
                for chunk, document in results:
                    # 从文件路径中提取文件名
                    import os
                    file_name = os.path.basename(document.file_path) if document.file_path else 'Unknown'
                    
                    chunks_info[chunk.id] = {
                        'chunk_type': chunk.chunk_type,
                        'document_name': file_name
                    }
                
                return chunks_info
            
        except Exception as e:
            logger.error(f"Failed to get chunks type info: {e}")
            return {}


class SearchManager:
    """
    搜索管理器主类 - P0核心功能
    统一管理向量内容检索的完整流程
    """
    
    def __init__(self, engine: Engine, lancedb_mgr: LanceDBMgr, models_mgr: ModelsMgr):
        self.engine = engine
        self.lancedb_mgr = lancedb_mgr
        self.models_mgr = models_mgr
        
        # 初始化各个组件
        self.query_processor = QueryProcessor(models_mgr)
        self.result_formatter = ResultFormatter(self.engine)
        self.context_enhancer = ContextEnhancer(self.engine)
    
    def search_documents(self, query: str, top_k: int = 10, 
                        document_ids: Optional[List[int]] = None,
                        distance_threshold: Optional[float] = None) -> Dict[str, Any]:
        """
        主要搜索接口 - 支持自然语言查询文档内容
        
        Args:
            query: 自然语言查询文本
            top_k: 返回的最大结果数
            document_ids: 可选的文档ID过滤列表
            distance_threshold: 可选的相似度阈值
            
        Returns:
            包含检索结果的字典：
            {
                "success": bool,
                "results": {...},  # 格式化的检索结果
                "raw_results": [...],  # 原始LanceDB结果
                "query_info": {...}   # 查询元信息
            }
        """
        try:
            # 1. 查询预处理和验证
            valid, error_msg = self.query_processor.validate_query(query)
            if not valid:
                return {
                    "success": False,
                    "error": error_msg,
                    "results": None
                }
            
            cleaned_query = self.query_processor.clean_query(query)
            query_type = self.query_processor.detect_query_type(cleaned_query)
            
            logger.info(f"Processing search query: '{cleaned_query}' (type: {query_type})")
            
            # 2. 执行向量检索
            raw_results = self.lancedb_mgr.search_by_query(
                query_text=cleaned_query,
                models_mgr=self.models_mgr,
                top_k=top_k,
                document_ids=document_ids,
                distance_threshold=distance_threshold
            )
            
            if not raw_results:
                return {
                    "success": True,
                    "results": {
                        "context": "未找到相关内容",
                        "sources": [],
                        "total_chunks": 0
                    },
                    "raw_results": [],
                    "query_info": {
                        "original_query": query,
                        "cleaned_query": cleaned_query,
                        "query_type": query_type
                    }
                }
            
            # 3. 增强检索结果（添加类型信息）
            enhanced_results = self.context_enhancer.add_chunk_type_info(raw_results)
            
            # 4. 格式化为LLM友好的格式
            formatted_results = self.result_formatter.format_for_llm(enhanced_results)
            
            logger.info(f"Search completed: {len(enhanced_results)} results found")
            
            return {
                "success": True,
                "results": formatted_results,
                "raw_results": enhanced_results,
                "query_info": {
                    "original_query": query,
                    "cleaned_query": cleaned_query,
                    "query_type": query_type,
                    "document_filter": document_ids,
                    "distance_threshold": distance_threshold
                }
            }
            
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            return {
                "success": False,
                "error": f"检索失败: {str(e)}",
                "results": None
            }
    
    def get_parent_chunks_by_ids(self, parent_chunk_ids: List[int]) -> List[Dict[str, Any]]:
        """获取指定ID的父块完整内容"""
        return self.context_enhancer.get_parent_chunks_by_ids(parent_chunk_ids)
    
    def format_search_results(self, raw_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """格式化原始检索结果"""
        return self.result_formatter.format_for_llm(raw_results)


# 功能测试代码
if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(level=logging.INFO)
    # init SQLite session
    from config import TEST_DB_PATH
    from sqlmodel import create_engine
    from pathlib import Path
    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
    # LanceDB
    db_directory = Path(TEST_DB_PATH).parent
    lancedb_mgr = LanceDBMgr(base_dir=db_directory)
    # 模型管理器
    models_mgr = ModelsMgr(engine, base_dir=db_directory)
    
    # 1. testing SearchManager
    search_mgr = SearchManager(engine, lancedb_mgr, models_mgr)
    logger.info("SearchManager 核心功能模块已创建完成")
    results = search_mgr.search_documents(
        query="人工智能", top_k=5,
        document_ids=[3, 2],  # 假设我们只关心文档ID为3和2的结果
        distance_threshold=0.05)  # 更合适的阈值：保留距离小于0.05的结果
    logger.info(f"Search results: {results}")

    # 2. testing ContextEnhancer
    # context_enhancer = ContextEnhancer(engine)
    # parent_chunk_ids = [1, 2, 3]  # 假设我们有一些父块ID需要查询
    # parent_chunks = context_enhancer.get_parent_chunks_by_ids(parent_chunk_ids)
    # logger.info(f"Retrieved parent chunks: {parent_chunks}")

    # 3. testing QueryProcessor
    # query_processor = QueryProcessor(models_mgr)
    # query = "什么是人工智能？"
    # cleaned_query = query_processor.clean_query(query)
    # is_valid, validation_message = query_processor.validate_query(cleaned_query)
    # if is_valid:
    #     vector = query_processor.generate_vector(cleaned_query)
    #     query_type = query_processor.detect_query_type(cleaned_query)
    #     logger.info(f"Query processed successfully: {cleaned_query}, Type: {query_type}, Vector: {vector[:5]}...")
    # else:
    #     logger.error(f"Query validation failed: {validation_message}")

    # 4. testing ResultFormatter
    # result_formatter = ResultFormatter(engine)
    # sample_results = [
    #     {
    #         "parent_chunk_id": 1,
    #         "document_id": 1,
    #         "retrieval_content": "这是一个测试内容，用于验证结果格式化功能。",
    #         "_distance": 0.15
    #     },
    #     {
    #         "parent_chunk_id": 2,
    #         "document_id": 2,
    #         "retrieval_content": "另一个测试内容，检查格式化是否正确。",
    #         "_distance": 0.10
    #     }
    # ]
    # formatted_results = result_formatter.format_for_llm(sample_results)
    # logger.info(f"Formatted results: {formatted_results}")