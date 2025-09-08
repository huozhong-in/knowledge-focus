from config import singleton
from sqlmodel import Session, create_engine
from datetime import datetime
from typing import Dict, Any, List
import os
import logging
import warnings
from tagging_mgr import TaggingMgr
from db_mgr import FileScreeningResult
from markitdown import MarkItDown
from lancedb_mgr import LanceDBMgr
from model_config_mgr import ModelConfigMgr
from models_mgr import ModelsMgr
from db_mgr import FileScreenResult, ModelCapability
from sqlmodel import select, and_
import time
from bridge_events import BridgeEventSender

# 为当前模块创建日志器
logger = logging.getLogger(__name__)

def configure_parsing_warnings():
    """
    配置解析相关的警告过滤器和日志级别。
    在应用启动时调用此函数可以抑制markitdown和pdfminer的大量重复日志。
    """
    # 过滤掉pdfminer的字体警告和其他不必要的警告
    warnings.filterwarnings("ignore", category=UserWarning, module="pdfminer")
    warnings.filterwarnings("ignore", category=Warning, module="pdfminer")
    warnings.filterwarnings("ignore", category=UserWarning, module="markitdown")
    
    # 设置第三方库的日志级别为ERROR，减少噪音
    logging.getLogger('pdfminer').setLevel(logging.ERROR)
    logging.getLogger('markitdown').setLevel(logging.ERROR)
    
    logger.info("解析库的警告和日志级别配置已应用")

# 可被markitdown解析的文件扩展名
MARKITDOWN_EXTENSIONS = ['pdf', 'pptx', 'docx', 'xlsx', 'xls']
# 其他可解析的纯文本类型文件扩展名
OTHER_PARSEABLE_EXTENSIONS = ['md', 'markdown', 'txt']  # json/xml/csv也能，但意义不大
# 本业务场景所需模型能力的组合
SCENE_FILE_TAGGING: List[ModelCapability] = [ModelCapability.STRUCTURED_OUTPUT]

@singleton
class FileTaggingMgr:
    def __init__(self, session: Session, lancedb_mgr: LanceDBMgr, models_mgr: ModelsMgr) -> None:
        self.session = session
        self.lancedb_mgr = lancedb_mgr
        self.models_mgr = models_mgr
        self.model_config_mgr = ModelConfigMgr(session)
        self.tagging_mgr = TaggingMgr(session, self.lancedb_mgr, self.models_mgr)
        
        # 初始化markitdown解析器
        self.md_parser = MarkItDown(enable_plugins=False)
        # * markitdown现在明确不支持PDF中的图片导出,[出处](https://github.com/microsoft/markitdown/pull/1140#issuecomment-2968323805)
        self.bridge_event_sender = BridgeEventSender()

    def check_file_tagging_model_availability(self) -> bool:
        """
        检查是否有可用的模型。
        如果没有可用模型，返回False并记录警告
        """        
        for capa in SCENE_FILE_TAGGING:
            if self.model_config_mgr.get_spec_model_config(capa) is None:
                logger.warning(f"Model for file tagging is not available: {capa}")
                return False

        return True

    def parse_and_tag_file(self, screening_result: FileScreeningResult) -> bool:
        """
        Parses the content of a file, generates tags using the new vector-based
        workflow, and links them to the file. Does NOT commit the session.
        """
        if not screening_result or not screening_result.file_path or not os.path.exists(screening_result.file_path):
            logger.warning(f"Skipping parsing for non-existent file: {screening_result.file_path if screening_result else 'N/A'}")
            return False

        # 1. Extract content summary (a portion of the full content)
        try:
            content = self._extract_content(screening_result.file_path)
            if not content:
                logger.info(f"No content extracted from {screening_result.file_path}. Marking as processed.")
                self._update_tagged_time(screening_result)
                return True # Mark as processed even if no content
            
            # * Use a summary for efficiency
            summary = content[:3000] # Use the first 3000 characters as a summary

        except Exception as e:
            logger.error(f"Error extracting content from {screening_result.file_path}: {e}")
            screening_result.error_message = f"Content extraction failed: {e}"
            return False

        # 2. Orchestrate the new tagging process
        success = self.tagging_mgr.generate_and_link_tags_for_file(screening_result, summary)
        if success:
            self._update_tagged_time(screening_result)
            self.bridge_event_sender.tags_updated()
            return True
        else:
            return False

    def _extract_content(self, file_path: str) -> str:
        """从文件中提取文本内容。"""
        ext = file_path.split('.')[-1].lower()
        if ext in MARKITDOWN_EXTENSIONS:
            try:
                result = self.md_parser.convert(file_path, keep_data_uris=True)
                return result.text_content
            except Exception as e:
                logger.error(f"解析文件时出错 {file_path}: {e}")
                return ""
        elif ext in OTHER_PARSEABLE_EXTENSIONS:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"读取文件时出错 {file_path}: {e}")
                return ""
        else:
            # 不支持的文件类型，静默跳过
            return ""

    def _update_tagged_time(self, screening_result: FileScreeningResult):
        """Updates the tagged_time for a screening result object. Does not commit."""
        if screening_result:
            screening_result.tagged_time = datetime.now()
            self.session.add(screening_result)
    
    def process_pending_batch(self, task_id: int) -> Dict[str, Any]:
        """
        Processes a batch of pending file screening results.
        """        

        logger.info("[FILE_TAGGING_BATCH] Checking for a batch of pending files...")
        start_time = time.time()

        results = self.session.exec(
            select(FileScreeningResult)
            .where(and_(
                FileScreeningResult.status == FileScreenResult.PENDING.value,
                FileScreeningResult.task_id == task_id
            ))
        ).all()

        if not results:
            logger.info("[FILE_TAGGING_BATCH] No pending files to process in this batch.")
            return {"success": True, "processed": 0, "success_count": 0, "failed_count": 0}

        total_files = len(results)
        logger.info(f"[FILE_TAGGING_BATCH] Found {total_files} files to process in this batch.")

        processed_count = 0
        success_count = 0
        failed_count = 0

        for result in results:
            processed_count += 1
            file_process_start_time = time.time()
            logger.info(f"[FILE_TAGGING_BATCH] Processing file {processed_count}/{total_files}: {result.file_path}")

            try:
                if result.tagged_time and result.modified_time and result.tagged_time > result.modified_time:
                    logger.info(f"Skipping file, already tagged: {result.file_path}")
                    result.status = FileScreenResult.PROCESSED.value
                    self.session.add(result)
                    self.session.commit()
                    success_count += 1
                    continue
                
                if self.parse_and_tag_file(result):
                    result.status = FileScreenResult.PROCESSED.value
                    success_count += 1
                else:
                    result.status = FileScreenResult.FAILED.value
                    failed_count += 1
                
                self.session.commit()
                file_process_duration = time.time() - file_process_start_time
                logger.info(f"[FILE_TAGGING_BATCH] Finished file {processed_count}/{total_files}. Duration: {file_process_duration:.2f}s")
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"Error processing {result.file_path}: {e}")
                self.session.rollback()
                try:
                    result.status = FileScreenResult.FAILED.value
                    result.error_message = f"Unexpected error: {e}"
                    self.session.add(result)
                    self.session.commit()
                except Exception as inner_e:
                    logger.error(f"Failed to mark file as failed: {inner_e}")
                    self.session.rollback()
                failed_count += 1

        total_duration = time.time() - start_time
        logger.info(f"[FILE_TAGGING_BATCH] Finished batch. Duration: {total_duration:.2f}s")
        logger.info(f"Processed {processed_count} files. Succeeded: {success_count}, Failed: {failed_count}")
        return {"success": True, "processed": processed_count, "success_count": success_count, "failed_count": failed_count}

    def process_single_file_task(self, screening_result_id: int) -> bool:
        """
        Processes a single high-priority file parsing task.
        """

        logger.info(f"[PARSING_SINGLE] Starting to process high-priority file task for screening_result_id: {screening_result_id}")
        result = self.session.get(FileScreeningResult, screening_result_id)

        if not result:
            logger.error(f"[PARSING_SINGLE] Could not find FileScreeningResult with id: {screening_result_id}")
            return False

        try:
            if self.parse_and_tag_file(result):
                result.status = FileScreenResult.PROCESSED.value
                self.session.commit()
                logger.info(f"[PARSING_SINGLE] Successfully processed file: {result.file_path}")
                return True
            else:
                result.status = FileScreenResult.FAILED.value
                self.session.commit()
                logger.error(f"[PARSING_SINGLE] Failed to process file: {result.file_path}")
                return False
        except Exception as e:
            logger.error(f"[PARSING_SINGLE] Error processing file {result.file_path}: {e}")
            self.session.rollback()
            try:
                result.status = FileScreenResult.FAILED.value
                result.error_message = f"Unexpected error: {e}"
                self.session.add(result)
                self.session.commit()
            except Exception as inner_e:
                logger.error(f"[PARSING_SINGLE] Failed to mark file as failed: {inner_e}")
                self.session.rollback()
            return False


# 功能测试代码 - 相当于手动单元测试
if __name__ == "__main__":
    def setup_test_logging():
        """为测试设置独立的日志配置"""
        # 配置根日志记录器
        logging.basicConfig(level=logging.INFO)
        
        # 创建测试专用的日志文件处理器
        test_log_file = 'parsing_test.log'
        file_handler = logging.FileHandler(test_log_file, mode='w', encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        # 为当前模块的日志器添加文件处理器
        test_logger = logging.getLogger(__name__)
        test_logger.addHandler(file_handler)
        
        # 配置第三方库的日志级别，减少噪音
        configure_parsing_warnings()
        
        print(f"测试日志将保存到: {test_log_file}")
        return test_logger
    
    # 设置测试日志
    test_logger = setup_test_logging()
    test_logger.info("开始解析管理器功能测试")

    # 数据库连接
    from config import TEST_DB_PATH
    session = Session(create_engine(f'sqlite:///{TEST_DB_PATH}'))

    # 测试文件路径
    # import pathlib
    # user_home = pathlib.Path.home()
    # test_file_path = user_home / "Documents" / "纯CSS实现太极动态效果.pdf"
    # if not test_file_path.exists():
    #     test_logger.error(f"测试文件不存在: {test_file_path}")
    #     raise FileNotFoundError(f"测试文件不存在: {test_file_path}")
    
    # test_logger.info(f"测试文件: {test_file_path}")
    
    # 创建解析管理器实例进行测试
    db_directory = os.path.dirname(TEST_DB_PATH)
    lancedb_mgr = LanceDBMgr(base_dir=db_directory)
    models_mgr = ModelsMgr(session)
    file_tagging_mgr = FileTaggingMgr(session, lancedb_mgr, models_mgr)
    print(file_tagging_mgr.check_file_tagging_model_availability())
    
    # 测试示例：
    # 1. 测试内容提取
    # extracted_content = file_tagging_mgr._extract_content(test_file_path)
    # test_logger.info(f"提取内容长度: {len(extracted_content) if extracted_content else 0}")
    
    # 2. 测试文件解析和标签生成
    # from screening_mgr import ScreeningManager
    # screening_mgr = ScreeningManager(session)
    # result: FileScreeningResult = screening_mgr.get_by_path(test_file_path)
    # if result:
    #     test_logger.info(f"找到粗筛结果ID: {result.id}")
    #     success = await file_tagging_mgr.parse_and_tag_file(result)
    #     file_tagging_mgr.session.commit()
    #     test_logger.info(f"解析和标签生成结果: {success}")
    # else:
    #     test_logger.warning("未找到对应的粗筛结果")
    
    test_logger.info("解析管理器功能测试完成")
