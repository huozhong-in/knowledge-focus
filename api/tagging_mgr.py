from config import singleton
from sqlmodel import (
    create_engine,
    Session, 
    select,
    text,
)
from sqlalchemy import Engine
from db_mgr import Tags, FileScreeningResult, TagsType
from typing import List, Dict, Any
import logging
import time
import os
from lancedb_mgr import LanceDBMgr
from models_mgr import ModelsMgr
# from bridge_events import BridgeEventSender

logger = logging.getLogger()

@singleton
class TaggingMgr:
    def __init__(self, engine: Engine, lancedb_mgr: LanceDBMgr, models_mgr: ModelsMgr) -> None:
        self.engine = engine
        self.lancedb_mgr = lancedb_mgr
        self.models_mgr = models_mgr
        
        # # 初始化桥接事件发送器
        # self.bridge_events = BridgeEventSender("tagging_mgr")
        
        # 标签缓存
        self._tag_name_cache = {}  # 名称 -> ID的映射
        self._tag_id_cache = {}    # ID -> 标签对象的映射
        self._cache_timestamp = 0  # 缓存时间戳
        self._cache_ttl = 300      # 缓存有效期(秒)
        # 预热缓存
        self._warm_cache()
        
        # 确保FTS索引是最新的
        try:
            # 检查FTS表是否存在且结构正确
            with Session(self.engine) as session:
                result = session.exec(text("SELECT name FROM sqlite_master WHERE type='table' AND name='t_files_fts'"))
                if not result.fetchone():
                    logger.warning("FTS表不存在，将尝试重建")
                    self.rebuild_fts_index()
        except Exception as e:
            logger.error(f"检查FTS表时出错: {e}")
            # 不抛出异常，让应用可以继续运行
    
    def _warm_cache(self) -> None:
        """预热标签缓存，加载所有标签到内存"""
        try:
            tags = self.get_all_tags()
            self._tag_name_cache = {tag.name: tag.id for tag in tags}
            self._tag_id_cache = {tag.id: tag for tag in tags}
            self._cache_timestamp = time.time()
            logger.info(f"标签缓存预热成功，共加载 {len(tags)} 个标签")
        except Exception as e:
            logger.error(f"标签缓存预热失败: {e}")
    
    def _refresh_cache_if_needed(self) -> None:
        """检查缓存是否过期，需要刷新"""
        current_time = time.time()
        if current_time - self._cache_timestamp > self._cache_ttl:
            self._warm_cache()
    
    def get_tag_id_from_cache(self, tag_name: str) -> int | None:
        """从缓存中获取标签ID，如不存在返回None"""
        self._refresh_cache_if_needed()
        return self._tag_name_cache.get(tag_name)

    def get_tag_from_cache(self, tag_id: int) -> Tags | None:
        """从缓存中获取标签对象，如不存在返回None"""
        self._refresh_cache_if_needed()
        return self._tag_id_cache.get(tag_id)

    def get_or_create_tags(self, tag_names: List[str], tag_type: TagsType = TagsType.USER) -> List[Tags]:
        """
        Retrieves existing tags or creates new ones for a list of names.
        This is more efficient than calling get_or_create_tag for each tag.
        """
        if not tag_names:
            return []

        # Find which tags already exist
        with Session(self.engine) as session:
            existing_tags_query = session.exec(select(Tags).where(Tags.name.in_(tag_names)))
            existing_tags = existing_tags_query.all()
            existing_names = {tag.name for tag in existing_tags}

            # Determine which tags are new
            new_tag_names = [name for name in tag_names if name not in existing_names]

        # Create new tags if any
        new_tags = []
        if new_tag_names:
            with Session(self.engine) as session:
                for name in new_tag_names:
                    # Per PRD, LLM tags are added to the pool. 'user' type is appropriate.
                    new_tag = Tags(name=name, type=tag_type)
                    session.add(new_tag)
                    new_tags.append(new_tag)
                
                try:
                    session.commit()
                    # Refresh new tags to get their IDs
                    for tag in new_tags:
                        session.refresh(tag)
                    
                    # # 发送标签更新通知，但仅当实际创建了新标签时
                    # if new_tags:
                    #     self.notify_tags_updated()
                except Exception as e:
                    logger.error(f"Error creating new tags: {e}")
                    session.rollback()
                
                    # 处理唯一约束错误，避免无限递归
                    if "UNIQUE constraint failed" in str(e):
                        # 直接查询已存在的标签
                        existing_tags_query = session.exec(select(Tags).where(Tags.name.in_(new_tag_names)))
                        additional_existing_tags = existing_tags_query.all()
                        return existing_tags + additional_existing_tags
                    else:
                        # 仅在非唯一约束错误时进行递归，避免无限递归
                        return self.get_or_create_tags(tag_names, tag_type)

        return existing_tags + new_tags

    def get_all_tags(self) -> List[Tags]:
        """
        Retrieves all tags from the database.
        """
        with Session(self.engine) as session:
            return session.exec(select(Tags)).all()

    def get_all_tag_names_from_cache(self) -> List[str]:
        """从缓存中获取所有标签的名称"""
        self._refresh_cache_if_needed()
        return list(self._tag_name_cache.keys())

    def link_tags_to_file(self, screening_result: Dict[str, Any], tag_ids: List[int]) -> Dict[str, Any]:
        """
        Links a list of tag IDs to a file screening result object.
        This updates the `tags_display_ids` column, and a database trigger
        should handle updating the FTS table.
        """
        # Combine new tags with existing ones, ensuring no duplicates and sorted order
        tags_display_ids = screening_result.get('tags_display_ids', '')
        existing_ids = set(int(tid) for tid in tags_display_ids.split(',') if tid) if tags_display_ids else set()
        all_ids = sorted(list(existing_ids.union(set(tag_ids))))

        # Convert list of ints to a comma-separated string
        tags_str = ",".join(map(str, all_ids))
        
        screening_result['tags_display_ids'] = tags_str
        return screening_result

    def get_tag_ids_by_names(self, tag_names: List[str]) -> List[int]:
        """
        通过标签名列表获取对应的标签ID列表。
        不存在的标签名将被忽略。
        
        Args:
            tag_names: 标签名列表
        
        Returns:
            对应的标签ID列表
        """
        if not tag_names:
            return []
        
        # 先从缓存中查找
        tag_ids = []
        missing_names = []
        
        for name in tag_names:
            tag_id = self.get_tag_id_from_cache(name)
            if tag_id is not None:
                tag_ids.append(tag_id)
            else:
                missing_names.append(name)
        
        # 如果所有标签都在缓存中找到，直接返回
        if not missing_names:
            return tag_ids
            
        # 否则查询数据库获取缓存中没有的标签
        with Session(self.engine) as session:
            tags_query = session.exec(select(Tags).where(Tags.name.in_(missing_names)))
            tags = tags_query.all()
            
            # 更新缓存并合并结果
            for tag in tags:
                self._tag_name_cache[tag.name] = tag.id
                self._tag_id_cache[tag.id] = tag
                tag_ids.append(tag.id)
            
            return tag_ids
    
    def build_tags_search_query(self, tag_ids: List[int], operator: str = "AND") -> str:
        """
        构建用于FTS5 MATCH查询的字符串。
        
        Args:
            tag_ids: 标签ID列表
            operator: 查询操作符，可以是 "AND", "OR" 或其他FTS5支持的操作符
            
        Returns:
            用于FTS5 MATCH查询的字符串，例如: "1 AND 5 AND 10"
        """
        if not tag_ids:
            return ""
            
        # 确保ID是整数且转为字符串
        tag_ids_str = [str(tid) for tid in tag_ids]
        
        # 构建查询字符串
        # 正确处理单个标签的情况
        if len(tag_ids_str) == 1:
            return tag_ids_str[0]
        else:
            return " {} ".format(operator).join(tag_ids_str)
    
    def get_file_ids_by_tags(self, tag_ids: List[int], operator: str = "AND") -> List[int]:
        """
        通过标签ID列表，查询包含这些标签的文件ID列表。
        
        Args:
            tag_ids: 标签ID列表
            operator: 查询操作符，可以是 "AND"(必须包含所有标签) 或 "OR"(包含任一标签)
            
        Returns:
            匹配条件的文件ID列表
        """
        if not tag_ids:
            return []
            
        # 构建FTS5查询
        query_str = self.build_tags_search_query(tag_ids, operator)
        
        # 执行FTS5查询
        sql = text("""
        SELECT file_id FROM t_files_fts 
        WHERE tags_search_ids MATCH :query_str
        """).bindparams(query_str=query_str)

        with Session(self.engine) as session:
            result = session.exec(sql)
            # 提取文件ID
            return [row[0] for row in result.fetchall()]
    
    def get_tags_display_ids_as_list(self, tags_display_ids: str) -> List[int]:
        """
        将逗号分隔的标签ID字符串转换为ID列表
        
        Args:
            tags_display_ids: 逗号分隔的标签ID字符串，如 "1,5,10"
            
        Returns:
            标签ID列表，如 [1, 5, 10]
        """
        if not tags_display_ids:
            return []
            
        return [int(tid) for tid in tags_display_ids.split(',') if tid.strip()]
    
    def get_tags_by_ids(self, tag_ids: List[int]) -> List[Tags]:
        """
        通过标签ID列表获取对应的标签对象列表
        
        Args:
            tag_ids: 标签ID列表
            
        Returns:
            Tags对象列表
        """
        if not tag_ids:
            return []
        with Session(self.engine) as session:
            return session.exec(select(Tags).where(Tags.id.in_(tag_ids))).all()

    def search_files_by_tag_names(self, tag_names: List[str], 
                                operator: str = "AND", 
                                offset: int = 0, 
                                limit: int = 50) -> List[dict]:
        """
        Lightweight search: searches for files by a list of tag names.
        Suitable for real-time feedback during user input.
        
        Args:
            tag_names: List of tag names.
            operator: Query logical operator ("AND" or "OR").
            offset: Pagination offset.
            limit: Number of records per page.
            
        Returns:
            A list of matching file information dictionaries.
        """
        # 1. Get tag IDs
        tag_ids = self.get_tag_ids_by_names(tag_names)
        if not tag_ids:
            return []
            
        # 2. Get file IDs
        file_ids = self.get_file_ids_by_tags(tag_ids, operator)
        
        # 3. Apply pagination
        paginated_ids = file_ids[offset:offset+limit] if file_ids else []
        
        # 4. Get file details
        results = []
        for file_id in paginated_ids:
            with Session(self.engine) as session:
                file_result = session.get(FileScreeningResult, file_id)
                if file_result:
                    # 获取标签名称列表
                    tag_names_list = []
                    if file_result.tags_display_ids:
                        tag_ids = self.get_tags_display_ids_as_list(file_result.tags_display_ids)
                        tags = self.get_tags_by_ids(tag_ids)
                        tag_names_list = [tag.name for tag in tags]
                    
                    results.append({
                        'id': file_id,
                        'path': file_result.file_path,
                        'file_name': os.path.basename(file_result.file_path),
                        'extension': os.path.splitext(file_result.file_path)[1][1:] if '.' in file_result.file_path else None,
                        'tags_display_ids': file_result.tags_display_ids,
                        'tags': tag_names_list
                    })
                
        return results
    
    def full_text_search(self, query_text: str, offset: int = 0, limit: int = 50) -> List[dict]:
        """
        重量级搜索：结合标签和内容的完整搜索
        适用于用户点击搜索按钮后的精确搜索
        
        Args:
            query_text: 用户查询文本
            offset: 分页起始位置
            limit: 每页记录数
            
        Returns:
            匹配的文件信息列表，包括匹配评分
        """
        # 这里应该实现完整的搜索策略：
        # 1. 提取查询文本中可能的标签
        # 2. 对剩余文本进行全文检索
        # 3. 结合两者结果进行排序
        
        # 简单实现示例 - 在实际应用中应该替换为真正的全文检索
        words = [w.strip() for w in query_text.split() if w.strip()]
        
        # 先尝试作为标签匹配
        tag_results = self.search_files_by_tag_names(words, "OR", 0, 1000)
        
        # 在这里添加更复杂的全文检索逻辑
        # 例如使用SQLite的FTS5对文件内容进行搜索
        # 或者使用外部搜索引擎如Elasticsearch、Meilisearch等
        
        # 将结果排序并分页
        # 这里简单返回标签匹配结果
        return tag_results[offset:offset+limit]
    
    def recommend_related_tags(self, tag_ids: List[int], limit: int = 5) -> List[Tags]:
        """
        根据给定的标签推荐相关标签
        基于共同出现频率的简单协同过滤算法
        
        Args:
            tag_ids: 当前使用的标签ID列表
            limit: 最大推荐数量
            
        Returns:
            推荐的相关标签列表
        """
        if not tag_ids:
            # 如果没有输入标签，返回最流行的标签
            return self.get_popular_tags(limit)
            
        # 查询包含当前标签的所有文件
        file_ids = self.get_file_ids_by_tags(tag_ids, "AND")
        if not file_ids:
            return []
            
        # 从这些文件中统计其他标签的出现频率
        tag_frequency = {}
        for file_id in file_ids:
            with Session(self.engine) as session:
                file_result = session.get(FileScreeningResult, file_id)
                if file_result and file_result.tags_display_ids:
                    file_tag_ids = [int(tid) for tid in file_result.tags_display_ids.split(',') if tid]
                    for tid in file_tag_ids:
                        if tid not in tag_ids:  # 排除已经选择的标签
                            tag_frequency[tid] = tag_frequency.get(tid, 0) + 1
        
        # 按频率排序
        sorted_tags = sorted(tag_frequency.items(), key=lambda x: x[1], reverse=True)
        top_tag_ids = [tid for tid, _ in sorted_tags[:limit]]
        
        # 获取标签详情
        return self.get_tags_by_ids(top_tag_ids)
    
    def get_popular_tags(self, limit: int = 10) -> List[Tags]:
        """
        获取最流行的标签（使用最频繁的标签）
        
        Args:
            limit: 最大返回数量
            
        Returns:
            流行标签列表
        """
        # 统计每个标签的出现次数
        tag_frequency = {}
        # 获取所有文件的标签ID字符串
        with Session(self.engine) as session:
            files_query = session.exec(select(FileScreeningResult.tags_display_ids)
                                        .where(FileScreeningResult.tags_display_ids.is_not(None))
                                        .where(FileScreeningResult.tags_display_ids != ""))
            files_tag_ids = files_query.all()
            
            for tags_str in files_tag_ids:
                if tags_str[0]:  # 确保不是None或空字符串
                    for tag_id in tags_str[0].split(','):
                        if tag_id.strip():
                            tid = int(tag_id.strip())
                            tag_frequency[tid] = tag_frequency.get(tid, 0) + 1
        
        # 按出现频率排序
        sorted_tags = sorted(tag_frequency.items(), key=lambda x: x[1], reverse=True)
        top_tag_ids = [tid for tid, _ in sorted_tags[:limit]]
        
        # 获取标签详情
        if not top_tag_ids:
            return []
            
        return self.get_tags_by_ids(top_tag_ids)

    def generate_and_link_tags_for_file(self, file_result: Dict[str, Any], file_summary: str) -> bool:
        """
        Orchestrates the entire vector-based tagging process for a single file.
        """
        if not file_summary:
            logger.warning(f"File summary is empty for {file_result.get('file_path', 'unknown')}. Skipping tagging.")
            return False

        # 1. Get embedding for the file summary
        summary_vector = self.models_mgr.get_embedding(file_summary)
        if len(summary_vector) == 0:
            logger.error(f"Failed to generate embedding for {file_result.get('file_path', 'unknown')}. Skipping tagging.")
            return False

        # 2. Search for candidate tags in LanceDB
        candidate_results = self.lancedb_mgr.search_tags(summary_vector)
        candidate_tags = [tag['text'] for tag in candidate_results]

        # 3. Get final tags from the LLM
        final_tag_names = self.models_mgr.get_tags_from_llm(file_result.get('file_path', 'unknown'), file_summary, candidate_tags)
        if len(final_tag_names) == 0:
            logger.warning(f"LLM returned no tags for {file_result.get('file_path', 'unknown')}. Skipping linking.")
            return False

        # 4. Get or create tag objects in SQLite
        # We use LLM type here as specified in the PRD
        tag_objects = self.get_or_create_tags(final_tag_names, tag_type=TagsType.LLM)

        # 5. For any newly created tags, add them to LanceDB
        newly_created_tags = [tag for tag in tag_objects if tag.name not in candidate_tags]
        if newly_created_tags:
            new_tags_for_lancedb = []
            for tag in newly_created_tags:
                tag_vector = self.models_mgr.get_embedding(tag.name)
                if tag_vector:
                    new_tags_for_lancedb.append({"vector": tag_vector, "text": tag.name, "tag_id": tag.id})
            
            if new_tags_for_lancedb:
                self.lancedb_mgr.add_tags(new_tags_for_lancedb)

        # 6. Link the final tags to the file in SQLite
        final_tag_ids = [tag.id for tag in tag_objects]
        file_result = self.link_tags_to_file(file_result, final_tag_ids)
        with Session(self.engine) as session:
            try:
                # 使用merge而不是add，自动判断是插入还是更新
                # merge会根据主键判断记录是否存在，存在则更新，不存在则插入
                session.merge(FileScreeningResult(**file_result))
                session.commit()
            except Exception as e:
                logger.error(f"Failed to link tags to file {file_result.get('file_path', 'unknown')}: {e}")
                session.rollback()
                return False
        # # 7. 通知文件处理完成
        # self.notify_file_processing_completed(file_result.get('file_path', 'unknown'), len(final_tag_ids))

        logger.info(f"Successfully generated and linked {len(final_tag_ids)} tags for {file_result.get('file_path', 'unknown')}")
        return True

    def rebuild_fts_index(self) -> bool:
        """
        重建FTS5索引，通常在表结构变更或修复问题后使用。
        该函数会清空FTS表并从t_file_screening_results重新填充数据。
        
        Returns:
            是否重建成功
        """
        try:
            # 清空FTS表
            with Session(self.engine) as session:
                session.exec(text("DELETE FROM t_files_fts"))
                
                # 获取所有文件筛选结果
                file_results_query = session.exec(select(FileScreeningResult)
                                                    .where(FileScreeningResult.tags_display_ids.is_not(None))
                                                    .where(FileScreeningResult.tags_display_ids != ""))
                file_results = file_results_query.all()
                
                # 重新填充FTS表
                for result in file_results:
                    if result.tags_display_ids:
                        # 将逗号分隔的ID转换为空格分隔
                        tags_search_ids = result.tags_display_ids.replace(',', ' ')
                        # 插入FTS表
                        sql = text("INSERT INTO t_files_fts (file_id, tags_search_ids) VALUES (:file_id, :tags_search_ids)").bindparams(
                            file_id=result.id, 
                            tags_search_ids=tags_search_ids
                        )
                        session.exec(sql)
                
                session.commit()
                logger.info(f"成功重建FTS索引，共处理 {len(file_results)} 条记录")
                return True
        except Exception as e:
            logger.error(f"重建FTS索引失败: {e}")
            return False

    def get_tag_cloud_data(self, limit: int = 50, min_weight: int = 1) -> List[Dict]:
        """
        获取标签云数据，包含标签ID、名称、权重和类型
        
        Args:
            limit: 返回的最大标签数量
            min_weight: 最小权重阈值，只返回权重大于或等于此值的标签
        
        Returns:
            包含标签信息的字典列表，每个字典包含id、name、weight和type字段
        """
        try:
            # 执行SQL查询，获取标签及其关联的文件数量
            # 使用精确匹配避免部分匹配问题，在tags_display_ids两端加逗号后匹配完整的标签ID
            query = text("""
                SELECT t.id, t.name, t.type, COUNT(DISTINCT fsr.id) as weight
                FROM t_tags t
                LEFT JOIN t_file_screening_results fsr ON (',' || fsr.tags_display_ids || ',') LIKE '%,' || t.id || ',%'
                GROUP BY t.id, t.name, t.type
                HAVING COUNT(DISTINCT fsr.id) >= :min_weight
                ORDER BY weight DESC
                LIMIT :limit
            """).bindparams(limit=limit, min_weight=min_weight)
            with Session(self.engine) as session:
                result = session.exec(query)
                
                # 构建返回结果
                tag_cloud = []
                for row in result:
                    tag_cloud.append({
                        "id": row[0],
                        "name": row[1],
                        "type": row[2],
                        "weight": row[3]
                    })
                    
                return tag_cloud
        except Exception as e:
            logger.error(f"获取标签云数据失败: {e}")
            return []

    # def notify_tags_updated(self):
    #     """
    #     向前端通知标签已更新
        
    #     使用统一桥接模式向前端发送事件通知。
    #     """
    #     try:
    #         self.bridge_events.tags_updated("标签数据已更新，前端应刷新标签云")
    #     except Exception as e:
    #         logger.error(f"发送标签更新通知失败: {e}")
    
    # def notify_file_processing_completed(self, file_path: str, tags_count: int):
    #     """
    #     通知文件处理完成
        
    #     Args:
    #         file_path: 处理的文件路径
    #         tags_count: 添加的标签数量
    #     """
    #     try:
    #         self.bridge_events.file_processed(
    #             file_path=file_path,
    #             tags_count=tags_count,
    #             description=f"文件 {os.path.basename(file_path)} 已处理完成，添加了 {tags_count} 个标签"
    #         )
    #         logger.info(f"已发送文件处理完成通知: {file_path}")
    #     except Exception as e:
    #         logger.error(f"发送文件处理完成通知失败: {e}")

# 测试用代码
if __name__ == '__main__':
    import sys
    logger.setLevel(logging.INFO)
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    from config import TEST_DB_PATH
    import pathlib
    base_dir = pathlib.Path(TEST_DB_PATH).parent
    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
    lancedb_mgr = LanceDBMgr(base_dir=base_dir)
    models_mgr = ModelsMgr(engine=engine, base_dir=base_dir)
    tagging_mgr = TaggingMgr(
        engine=engine,
        lancedb_mgr=lancedb_mgr,
        models_mgr=models_mgr
    )

    # # 重建FTS索引
    # print("重建FTS索引...")
    # tagging_mgr.rebuild_fts_index()
    # print("FTS索引重建完成")

    # 测试根据标签搜索文件
    test_tag_names = ["AI驱动浏览器自动化"]
    print(f"搜索包含标签 {test_tag_names} 的文件...")
    search_results = tagging_mgr.search_files_by_tag_names(test_tag_names, operator="AND", offset=0, limit=10)
    print(f"搜索结果数量: {len(search_results)}")
    for i, result in enumerate(search_results):
        print(f"{i+1}. ID: {result['id']}, 路径: {result['path']}")
        print(f"   标签IDs: {result['tags_display_ids']}")
        # 获取标签名称
        if result['tags_display_ids']:
            tag_ids = tagging_mgr.get_tags_display_ids_as_list(result['tags_display_ids'])
            tags = tagging_mgr.get_tags_by_ids(tag_ids)
            print(f"   标签名称: {[tag.name for tag in tags]}")
    
    # 测试标签推荐
    # if search_results:
    #     first_result = search_results[0]
    #     first_tags = tagging_mgr.get_tags_display_ids_as_list(first_result['tags_display_ids'])
    #     print(f"\n为文件 {first_result['path']} 推荐相关标签...")
    #     related_tags = tagging_mgr.recommend_related_tags(first_tags, limit=5)
    #     print(f"推荐标签: {[tag.name for tag in related_tags]}")

    # # 测试标签云
    # print("\n获取标签云数据...")
    # tag_cloud = tagging_mgr.get_tag_cloud_data()
    # print(f"标签云数据: {tag_cloud}")