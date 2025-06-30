from sqlmodel import (
    create_engine,
    Session, 
    select,
)
from db_mgr import Tags, FileScreeningResult, TagsType
from typing import List
import logging

logger = logging.getLogger(__name__)

class TaggingMgr:
    def __init__(self, session: Session) -> None:
        self.session = session

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
                # Re-query to handle potential race conditions if another process created the tag
                return self.get_or_create_tags(tag_names, tag_type)

        return existing_tags + new_tags

    def get_all_tags(self) -> List[Tags]:
        """
        Retrieves all tags from the database.
        """
        return self.session.exec(select(Tags)).all()

    def link_tags_to_file(self, screening_result_id: int, tag_ids: List[int]) -> bool:
        """
        Links a list of tag IDs to a file screening result.
        This updates the `tags_display_ids` column, and a database trigger
        should handle updating the FTS table.
        """
        if not tag_ids:
            return False
            
        result = self.session.get(FileScreeningResult, screening_result_id)
        if not result:
            logger.error(f"File screening result with id {screening_result_id} not found.")
            return False

        # Combine new tags with existing ones, ensuring no duplicates and sorted order
        existing_ids = set(int(tid) for tid in result.tags_display_ids.split(',') if tid) if result.tags_display_ids else set()
        all_ids = sorted(list(existing_ids.union(set(tag_ids))))

        # Convert list of ints to a comma-separated string
        tags_str = ",".join(map(str, all_ids))
        
        result.tags_display_ids = tags_str
        self.session.add(result)
        # The commit will be handled by the calling function (e.g., in ParsingMgr)
        
        return True

if __name__ == '__main__':
    db_file = "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db"
    tagging_mgr = TaggingMgr(Session(create_engine(f'sqlite:///{db_file}')))
    
    # 示例：获取或创建标签
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
