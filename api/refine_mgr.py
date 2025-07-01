from sqlmodel import Session, create_engine
from typing import Dict, Any
from sqlmodel import Session, select
from db_mgr import (
    FileScreeningResult, FileScreenResult, 
    Task, TaskType, TaskStatus, TaskResult, FileScreenResult as FileScreeningStatus
)
from datetime import datetime
import logging
import os
from parsing_mgr import ParsingMgr, PARSEABLE_EXTENSIONS

logger = logging.getLogger(__name__)

class RefineManager:
    """文件信息精炼类，使用粗筛结果表中的元数据和文件内容给文件打标签"""
    
    def __init__(self, session: Session):
        self.session = session
        self.parsing_mgr = ParsingMgr(session)  # 初始化解析管理器

    def process_all_pending_screening_results(self) -> Dict[str, Any]:
        """处理所有待处理的文件筛选结果"""
        processed_count = 0
        success_count = 0
        failed_count = 0
        
        # Fetch pending results that are parsable
        stmt = select(FileScreeningResult).where(
            FileScreeningResult.status == FileScreeningStatus.PENDING,
            FileScreeningResult.extension.in_(PARSEABLE_EXTENSIONS)
        ).limit(100) # Process in batches
        
        results = self.session.exec(stmt).all()

        if not results:
            logger.info("No pending screening results to process.")
            return {"success": True, "processed": 0, "success_count": 0, "failed_count": 0, "error": "No pending files"}

        logger.info(f"Found {len(results)} pending screening results to process.")

        for result in results:
            processed_count += 1
            try:
                logger.info(f"Processing file: {result.file_path}")
                success = self.parsing_mgr.parse_and_tag_file(result)
                if success:
                    result.status = FileScreeningStatus.PROCESSED
                    success_count += 1
                else:
                    result.status = FileScreeningStatus.FAILED
                    failed_count += 1
                
                self.session.add(result)

            except Exception as e:
                logger.error(f"Error processing file {result.file_path}: {e}", exc_info=True)
                result.status = FileScreeningStatus.FAILED
                result.error_message = str(e)
                self.session.add(result)
                failed_count += 1
            finally:
                # Commit after each file to save progress incrementally
                self.session.commit()

        logger.info(f"Finished processing batch. Total: {processed_count}, Success: {success_count}, Failed: {failed_count}")
        return {"success": True, "processed": processed_count, "success_count": success_count, "failed_count": failed_count}

    def create_refine_task(self, file_path:str) -> int:
        """
        创建一个精炼任务，处理指定文件的筛选结果。
        This is now primarily handled by the main task creation logic, but this method
        can still be used for manually triggering a refinement for a single file.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File {file_path} not found")
        
        # Check if a screening result exists
        screening_result = self.session.exec(
            select(FileScreeningResult).where(FileScreeningResult.file_path == file_path)
        ).first()
        
        if not screening_result:
            # This case should be rare if the file comes from the UI, 
            # as it should have been screened already.
            # We can create a basic screening result on the fly here if needed.
            raise ValueError(f"No screening result found for file {file_path}")

        # Create a new task for this specific file
        task = Task(
            task_name=f"Refine single file: {os.path.basename(file_path)}",
            task_type=TaskType.REFINE.value,
            status=TaskStatus.PENDING.value,
            extra_data={"file_path": file_path} # Pass file_path to the processor
        )
        
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        
        return task.id

# 测试用代码
if __name__ == "__main__":
    db_file = "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db"
    session = Session(create_engine(f'sqlite:///{db_file}'))
