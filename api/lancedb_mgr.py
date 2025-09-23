from config import singleton, EMBEDDING_DIMENSIONS
import lancedb
from lancedb.pydantic import LanceModel, Vector
from typing import List
import os
import logging

logger = logging.getLogger()

# Pydantic model for the tags table in LanceDB
class Tags(LanceModel):
    vector: Vector(EMBEDDING_DIMENSIONS)  # type: ignore
    text: str
    tag_id: int

# 设计意图:
# - vector_id: 这是关键的“外键”，当我们从LanceDB检索到相似向量后，通过这个ID能快速在t_child_chunks表中找到它的详细信息，并进一步找到它的父块。
# - 冗余元数据 (parent_chunk_id, document_id): 这是一个重要的性能优化。它允许我们在向量搜索时进行“元数据预过滤”(pre-filtering)。例如，当用户希望“只在文档A和文档B中搜索”时，我们可以告诉LanceDB：“请只在document_id为A或B的向量中进行相似度搜索”。这能极大地缩小搜索范围，提高效率。
class VectorRecord(LanceModel):
    # 这是与SQLite中 t_child_chunks.vector_id 对应的值，我们用它来连接两个数据库
    vector_id: str
    vector: Vector(EMBEDDING_DIMENSIONS)  # type: ignore
    # 在向量库中冗余一些元数据，可以极大地加速“预过滤”
    parent_chunk_id: int
    document_id: int
    # 冗余用于检索的文本，便于调试和某些场景下的直接使用
    retrieval_content: str

@singleton
class LanceDBMgr:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir  # 保存基础目录路径供其他组件使用
        self.uri = os.path.join(base_dir, "lancedb")
        self.db = lancedb.connect(self.uri)
        self.tags_tbl = None
        self.vectors_tbl = None

    def init_tags_table(self, table_name: str = "tags"):
        """Initializes the LanceDB table for tags."""
        try:
            # First try to create with exist_ok=True
            self.tags_tbl = self.db.create_table(table_name, schema=Tags, exist_ok=True)
            # logger.info(f"LanceDB table '{table_name}' initialized successfully at {self.uri}")
        except ValueError as e:
            if "Schema Error" in str(e):
                # If schema doesn't match, drop the existing table and recreate
                logger.warning(f"Schema mismatch detected. Dropping existing table '{table_name}' and recreating...")
                try:
                    self.db.drop_table(table_name)
                    self.tags_tbl = self.db.create_table(table_name, schema=Tags)
                    logger.info(f"LanceDB table '{table_name}' recreated successfully at {self.uri}")
                except Exception as recreate_error:
                    logger.error(f"Failed to recreate LanceDB table: {recreate_error}")
                    raise
            else:
                logger.error(f"Failed to initialize LanceDB table: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to initialize LanceDB table: {e}")
            raise

    def init_vectors_table(self, table_name: str = "vectors"):
        """Initializes the LanceDB table for multivector retrieval."""
        try:
            # First try to create with exist_ok=True
            self.vectors_tbl = self.db.create_table(table_name, schema=VectorRecord, exist_ok=True)
            # logger.info(f"LanceDB vectors table '{table_name}' initialized successfully at {self.uri}")
        except ValueError as e:
            if "Schema Error" in str(e):
                # If schema doesn't match, drop the existing table and recreate
                logger.warning(f"Schema mismatch detected. Dropping existing vectors table '{table_name}' and recreating...")
                try:
                    self.db.drop_table(table_name)
                    self.vectors_tbl = self.db.create_table(table_name, schema=VectorRecord)
                    logger.info(f"LanceDB vectors table '{table_name}' recreated successfully at {self.uri}")
                except Exception as recreate_error:
                    logger.error(f"Failed to recreate LanceDB vectors table: {recreate_error}")
                    raise
            else:
                logger.error(f"Failed to initialize LanceDB vectors table: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to initialize LanceDB vectors table: {e}")
            raise

    def add_tags(self, tags_data: List[dict]):
        """
        Adds or updates tags in the LanceDB table.
        
        Args:
            tags_data: A list of dictionaries, each with 'vector', 'text', and 'tag_id'.
        """
        if not self.tags_tbl:
            self.init_tags_table()
        
        if not tags_data:
            return

        try:
            self.tags_tbl.add(tags_data)
            logger.info(f"Successfully added {len(tags_data)} tags to LanceDB.")
        except Exception as e:
            logger.error(f"Failed to add tags to LanceDB: {e}")

    def add_vectors(self, vector_records: List[dict]):
        """
        Adds vector records to the LanceDB vectors table.
        
        Args:
            vector_records: A list of dictionaries representing VectorRecord instances.
        """
        if not self.vectors_tbl:
            self.init_vectors_table()
        
        if not vector_records:
            return

        try:
            self.vectors_tbl.add(vector_records)
            logger.info(f"Successfully added {len(vector_records)} vectors to LanceDB.")
        except Exception as e:
            logger.error(f"Failed to add vectors to LanceDB: {e}")

    def search_tags(self, query_vector: List[float], limit: int = 10) -> List[dict]:
        """
        Searches for similar tags based on a query vector.
        
        Args:
            query_vector: The vector to search with.
            limit: The maximum number of results to return.
            
        Returns:
            A list of dictionaries representing the nearest tags.
        """
        if not self.tags_tbl:
            self.init_tags_table()

        try:
            results = self.tags_tbl.search(query_vector).limit(limit).to_pydantic(Tags)
            logger.info(f"LanceDB search found {len(results)} results.")
            # Convert Pydantic models to dictionaries for easier use
            return [result.model_dump() for result in results]
        except Exception as e:
            logger.error(f"Failed to search tags in LanceDB: {e}")
            return []

    def search_vectors(self, query_vector: List[float], limit: int = 50, 
                      document_ids: List[int] = None, distance_threshold: float = None) -> List[dict]:
        """
        Searches for similar vectors in the multivector table.
        
        Args:
            query_vector: The vector to search with.
            limit: The maximum number of results to return.
            document_ids: Optional list of document IDs to filter by.
            distance_threshold: Optional similarity threshold (cosine distance).
            
        Returns:
            A list of dictionaries representing the nearest vectors.
        """
        if not self.vectors_tbl:
            self.init_vectors_table()

        try:
            # 使用余弦相似度进行搜索 (LanceDB默认使用cosine距离)
            query = self.vectors_tbl.search(query_vector).limit(limit)
            
            # Apply document filter if provided
            if document_ids:
                # Convert to comma-separated string for SQL IN clause
                doc_ids_str = ','.join(map(str, document_ids))
                query = query.where(f"document_id IN ({doc_ids_str})")
            
            # 先获取原始结果（包含距离信息）
            raw_results = query.to_list()
            logger.info(f"LanceDB vector search found {len(raw_results)} results,")
            
            # 转换为Pydantic对象但保留距离信息
            results = query.to_pydantic(VectorRecord)
            
            # Convert Pydantic models to dictionaries and add distance info
            results_dict = []
            for i, result in enumerate(results):
                result_dict = result.model_dump(exclude={"vector"})
                # 从原始结果中添加距离信息
                if i < len(raw_results) and '_distance' in raw_results[i]:
                    result_dict['_distance'] = raw_results[i]['_distance']
                    # logger.info(f"Distance: {result_dict['_distance']}")
                results_dict.append(result_dict)
            
            # Apply distance threshold filtering if provided
            if distance_threshold is not None:
                filtered_results = []
                for result in results_dict:
                    # LanceDB returns _distance field in results
                    if '_distance' in result and result['_distance'] <= distance_threshold:
                        filtered_results.append(result)
                results_dict = filtered_results
                logger.info(f"After distance {distance_threshold} filtering: {len(results_dict)} results remain.")

            return results_dict
        except Exception as e:
            logger.error(f"Failed to search vectors in LanceDB: {e}")
            return []

    def search_by_query(self, query_text: str, models_mgr, top_k: int = 10, 
                       document_ids: List[int] = None, distance_threshold: float = None) -> List[dict]:
        """
        基础查询接口 - P0核心功能
        通过自然语言查询文档内容
        
        Args:
            query_text: 自然语言查询文本
            models_mgr: 模型管理器，用于生成embedding
            top_k: 返回的最大结果数
            document_ids: 可选的文档ID过滤列表
            distance_threshold: 可选的相似度阈值
            
        Returns:
            包含检索结果的字典列表，每个结果包含：
            - vector_id: 向量ID
            - parent_chunk_id: 父块ID  
            - document_id: 文档ID
            - retrieval_content: 检索内容
            - _distance: 相似度距离
        """
        try:
            # 1. 生成查询向量
            query_vector = models_mgr.get_embedding(query_text)
            logger.info(f"Generated query vector for: '{query_text[:50]}...'")
            
            # 2. 执行向量检索
            results = self.search_vectors(
                query_vector=query_vector,
                limit=top_k,
                document_ids=document_ids,
                distance_threshold=distance_threshold
            )

            logger.info(f"Query '{query_text[:50]}...' returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Failed to search by query '{query_text}': {e}")
            return []

    def search_by_vector(self, query_vector: List[float], top_k: int = 10, 
                        filters: dict = None) -> List[dict]:
        """
        通过向量直接进行检索
        
        Args:
            query_vector: 查询向量
            top_k: 返回的最大结果数
            filters: 过滤条件字典，如 {"document_ids": [1,2,3]}
            
        Returns:
            检索结果列表
        """
        try:
            document_ids = None
            distance_threshold = None
            
            if filters:
                document_ids = filters.get('document_ids')
                distance_threshold = filters.get('distance_threshold')
            
            results = self.search_vectors(
                query_vector=query_vector,
                limit=top_k,
                document_ids=document_ids,
                distance_threshold=distance_threshold
            )
            
            logger.info(f"Vector search returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Failed to search by vector: {e}")
            return []

# for testing purposes
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # SQLite DB
    from config import TEST_DB_PATH
    from sqlmodel import create_engine, Session
    session = Session(create_engine(f'sqlite:///{TEST_DB_PATH}'))
    # LanceDB
    from pathlib import Path
    lancedb_mgr = LanceDBMgr(base_dir=Path(TEST_DB_PATH).parent)
    # 模型管理器
    from models_mgr import ModelsMgr
    models_mgr = ModelsMgr(session, base_dir=Path(TEST_DB_PATH).parent)
    
    # # prepare the tables
    # sample_tags = [
    #     {"vector": [0.1] * EMBEDDING_DIMENSIONS, "text": "人工智能", "tag_id": 1},
    #     {"vector": [0.2] * EMBEDDING_DIMENSIONS, "text": "机器学习", "tag_id": 2},
    # ]
    
    # lancedb_mgr.add_tags(sample_tags)
    
    # # prepare the vectors
    # search_results = lancedb_mgr.search_tags(query_vector=[0.15] * EMBEDDING_DIMENSIONS)
    # print("Search results:", search_results)

    # test search_by_query()
    results = lancedb_mgr.search_by_query(
        query_text="咨询顾问",
        models_mgr=models_mgr,
        top_k=5,
        document_ids=[3, 2],  # 假设我们只关心文档ID为3和2的结果
        distance_threshold=0.05  # 更合适的阈值：保留距离小于0.05的结果
    )
    logger.info("Search by query results: %s", results)