from sqlmodel import (
    create_engine,
    Session, 
    select,
)
from db_mgr import Tags, FileScreeningResult, TagsType
from typing import List, Dict, Set, Optional
import logging
import time

logger = logging.getLogger(__name__)

class TaggingMgr:
    def __init__(self, session: Session) -> None:
        self.session = session
        # 标签缓存
        self._tag_name_cache = {}  # 名称 -> ID的映射
        self._tag_id_cache = {}    # ID -> 标签对象的映射
        self._cache_timestamp = 0  # 缓存时间戳
        self._cache_ttl = 300      # 缓存有效期(秒)
        # 预热缓存
        self._warm_cache()
        
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
    
    def get_tag_id_from_cache(self, tag_name: str) -> Optional[int]:
        """从缓存中获取标签ID，如不存在返回None"""
        self._refresh_cache_if_needed()
        return self._tag_name_cache.get(tag_name)
    
    def get_tag_from_cache(self, tag_id: int) -> Optional[Tags]:
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
        existing_tags_query = self.session.exec(select(Tags).where(Tags.name.in_(tag_names)))
        existing_tags = existing_tags_query.all()
        existing_names = {tag.name for tag in existing_tags}

        # Determine which tags are new
        new_tag_names = [name for name in tag_names if name not in existing_names]

        # Create new tags if any
        new_tags = []
        if new_tag_names:
            for name in new_tag_names:
                # Per PRD, LLM tags are added to the pool. 'user' type is appropriate.
                new_tag = Tags(name=name, type=tag_type)
                self.session.add(new_tag)
                new_tags.append(new_tag)
            
            try:
                self.session.commit()
                # Refresh new tags to get their IDs
                for tag in new_tags:
                    self.session.refresh(tag)
            except Exception as e:
                logger.error(f"Error creating new tags: {e}")
                self.session.rollback()
                
                # 处理唯一约束错误，避免无限递归
                if "UNIQUE constraint failed" in str(e):
                    # 直接查询已存在的标签
                    existing_tags_query = self.session.exec(select(Tags).where(Tags.name.in_(new_tag_names)))
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
        return self.session.exec(select(Tags)).all()

    def get_all_tag_names_from_cache(self) -> List[str]:
        """从缓存中获取所有标签的名称"""
        self._refresh_cache_if_needed()
        return list(self._tag_name_cache.keys())

    def link_tags_to_file(self, screening_result: FileScreeningResult, tag_ids: List[int]) -> bool:
        """
        Links a list of tag IDs to a file screening result object.
        This updates the `tags_display_ids` column, and a database trigger
        should handle updating the FTS table.
        """
        if not tag_ids or not screening_result:
            return False

        # Combine new tags with existing ones, ensuring no duplicates and sorted order
        existing_ids = set(int(tid) for tid in screening_result.tags_display_ids.split(',') if tid) if screening_result.tags_display_ids else set()
        all_ids = sorted(list(existing_ids.union(set(tag_ids))))

        # Convert list of ints to a comma-separated string
        tags_str = ",".join(map(str, all_ids))
        
        screening_result.tags_display_ids = tags_str
        self.session.add(screening_result)
        # The commit will be handled by the calling function (e.g., in ParsingMgr)
        
        return True

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
        tags_query = self.session.exec(select(Tags).where(Tags.name.in_(missing_names)))
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
        return f" {operator} ".join(tag_ids_str)
    
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
        sql = f"""
        SELECT file_id FROM t_files_fts 
        WHERE tags_search_ids MATCH ?
        """
        
        result = self.session.execute(sql, [query_str])
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
            
        return self.session.exec(select(Tags).where(Tags.id.in_(tag_ids))).all()
    
    def search_files_by_tag_names(self, tag_names: List[str], 
                                operator: str = "AND", 
                                offset: int = 0, 
                                limit: int = 50) -> List[dict]:
        """
        轻量级搜索：通过标签名列表搜索文件
        适用于用户输入过程中的实时反馈
        
        Args:
            tag_names: 标签名列表
            operator: 查询逻辑操作符 ("AND" 或 "OR")
            offset: 分页起始位置
            limit: 每页记录数
            
        Returns:
            匹配的文件信息列表 [{'id': 1, 'path': '...', ...}]
        """
        # 1. 获取标签ID
        tag_ids = self.get_tag_ids_by_names(tag_names)
        if not tag_ids:
            return []
            
        # 2. 获取文件ID
        file_ids = self.get_file_ids_by_tags(tag_ids, operator)
        
        # 3. 应用分页
        paginated_ids = file_ids[offset:offset+limit] if file_ids else []
        
        # 4. 获取文件详情
        results = []
        for file_id in paginated_ids:
            file_result = self.session.get(FileScreeningResult, file_id)
            if file_result:
                results.append({
                    'id': file_id,
                    'path': file_result.file_path,
                    # 添加其他需要的文件信息
                    'tags_display_ids': file_result.tags_display_ids
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
            file_result = self.session.get(FileScreeningResult, file_id)
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
        # 获取所有文件的标签ID字符串
        files_query = self.session.exec(select(FileScreeningResult.tags_display_ids)
                                       .where(FileScreeningResult.tags_display_ids.is_not(None))
                                       .where(FileScreeningResult.tags_display_ids != ""))
        files_tag_ids = files_query.all()
        
        # 统计每个标签的出现次数
        tag_frequency = {}
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

# 测试用代码
if __name__ == '__main__':
    db_file = "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db"
    tagging_mgr = TaggingMgr(Session(create_engine(f'sqlite:///{db_file}')))
    
    # 获取或创建标签
    test_tag_names = ["test", "example", "sample"]
    created_tags = tagging_mgr.get_or_create_tags(test_tag_names)
    print("Created or fetched tags:", created_tags)
    # 获取所有标签
    all_tags = tagging_mgr.get_all_tags()
    print("All tags:", all_tags)
    # 链接标签到文件筛选结果
    test_screening_result_id = 22  # 假设存在一个筛选结果ID为22
    test_tag_ids = [tag.id for tag in created_tags]
    tagging_mgr.link_tags_to_file(test_screening_result_id, test_tag_ids)
    tagging_mgr.session.commit()
