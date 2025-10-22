from config import singleton
from sqlmodel import Session, create_engine
from datetime import datetime
from typing import Dict, Any, List
import os
import logging
import warnings

# 禁用 tokenizers 并行化警告（在导入其他模块前设置）
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from tagging_mgr import TaggingMgr
from db_mgr import FileScreeningResult
from markitdown import MarkItDown
from lancedb_mgr import LanceDBMgr
from model_config_mgr import ModelConfigMgr
from models_mgr import ModelsMgr
from db_mgr import FileScreenResult, ModelCapability
from sqlmodel import select, and_, update
from sqlalchemy import Engine
import time
from bridge_events import BridgeEventSender

# 为当前模块创建日志器
logger = logging.getLogger()

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
# * 可以生成图像描述（目前仅支持pptx和图像文件） https://github.com/microsoft/markitdown#python-api
MARKITDOWN_EXTENSIONS = ['pdf', 'pptx', 'docx', 'xlsx', 'xls']
# 其他可解析的纯文本类型文件扩展名
OTHER_PARSEABLE_EXTENSIONS = ['md', 'markdown', 'txt']  # json/xml/csv也能，但意义不大
# 本业务场景所需模型能力的组合
SCENE_FILE_TAGGING: List[ModelCapability] = [ModelCapability.STRUCTURED_OUTPUT]

@singleton
class FileTaggingMgr:
    def __init__(self, engine: Engine, lancedb_mgr: LanceDBMgr, models_mgr: ModelsMgr) -> None:
        self.engine = engine
        self.lancedb_mgr = lancedb_mgr
        self.models_mgr = models_mgr
        self.model_config_mgr = ModelConfigMgr(engine)
        self.tagging_mgr = TaggingMgr(engine, self.lancedb_mgr, self.models_mgr)

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

    def parse_and_tag_file_optimized(self, screening_result_id: int) -> bool:
        """
        优化版本：分三步处理，避免长事务锁定
        1. 读取数据（短Session）
        2. 处理计算（无Session）  
        3. 更新结果（短Session）
        """
        # 第一步：读取数据，转换为纯字典
        result_data = self._read_screening_result_data(screening_result_id)
        if not result_data:
            return False
            
        # 第二步：纯计算处理（无数据库连接）
        processed_data = self._process_file_content_pure(result_data)
        if not processed_data:
            return False
            
        # 第三步：更新数据库
        return self._update_screening_result_data(screening_result_id, processed_data)
    
    def _read_screening_result_data(self, screening_result_id: int) -> Dict[str, Any]:
        """第一步：从数据库读取数据并转换为纯字典"""
        try:
            with Session(self.engine) as session:
                result = session.get(FileScreeningResult, screening_result_id)
                if not result:
                    logger.warning(f"FileScreeningResult not found: {screening_result_id}")
                    return {}
                
                if not result.file_path or not os.path.exists(result.file_path):
                    logger.warning(f"File not exists: {result.file_path}")
                    return {}
                
                # 转换为纯字典，脱离ORM绑定
                return result.model_dump()
        except Exception as e:
            logger.error(f"Error reading screening result {screening_result_id}: {e}")
            return {}
    
    def _process_file_content_pure(self, result_data: Dict[str, Any]) -> Dict[str, Any]:
        """第二步：纯计算处理，无数据库操作"""
        try:
            file_path = result_data.get('file_path')
            if not file_path:
                return {}
            
            # 提取文件内容
            content = self._extract_content(file_path)
            if not content:
                logger.info(f"No content extracted from {file_path}")
                return {
                    'status': FileScreenResult.PROCESSED.value,
                    'tagged_time': datetime.now(),
                    'content_extracted': False
                }
            
            # * Use a summary for efficiency
            summary = content[:3000]
            
            success = self.tagging_mgr.generate_and_link_tags_for_file(result_data, summary)
            if not success:
                return {
                    'status': FileScreenResult.FAILED.value,
                    'error_message': "Tag generation failed"
                }

            logger.info(f"Content extracted successfully for {file_path}, summary length: {len(summary)}")
            
            return {
                'status': FileScreenResult.PROCESSED.value,
                'tagged_time': datetime.now(),
                'content_extracted': True,
                'content_summary': summary
            }
            
        except Exception as e:
            logger.error(f"Error processing file content: {e}")
            return {
                'status': FileScreenResult.FAILED.value,
                'error_message': f"Content processing failed: {e}"
            }
    
    def _update_screening_result_data(self, screening_result_id: int, processed_data: Dict[str, Any]) -> bool:
        """第三步：更新数据库结果"""
        try:
            with Session(self.engine) as session:
                # 使用update语句，只更新必要字段，最高效
                update_fields = {}
                if 'status' in processed_data:
                    update_fields['status'] = processed_data['status']
                if 'tagged_time' in processed_data:
                    update_fields['tagged_time'] = processed_data['tagged_time']
                if 'error_message' in processed_data:
                    update_fields['error_message'] = processed_data['error_message']
                
                if update_fields:
                    stmt = update(FileScreeningResult).where(
                        FileScreeningResult.id == screening_result_id
                    ).values(**update_fields)
                    
                    session.exec(stmt)
                    session.commit()
                    
                    # 如果成功处理了内容，发送事件
                    if processed_data.get('content_extracted'):
                        self.bridge_event_sender.tags_updated()
                
                return True
                
        except Exception as e:
            logger.error(f"Error updating screening result {screening_result_id}: {e}")
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
    
    def process_pending_batch(self, task_id: int) -> Dict[str, Any]:
        """
        Processes a batch of pending file screening results.
        """        

        logger.info("[FILE_TAGGING_BATCH] Checking for a batch of pending files...")
        start_time = time.time()
        with Session(self.engine) as session:
            results = session.exec(
                select(FileScreeningResult)
                .where(and_(
                    FileScreeningResult.status == FileScreenResult.PENDING.value,
                    FileScreeningResult.task_id == task_id
                ))
            ).all()
            # 转为纯字典，避免长事务锁定
            results: List[Dict[str, Any]] = [r.model_dump() for r in results]

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
            logger.info(f"[FILE_TAGGING_BATCH] Processing file {processed_count}/{total_files}: {result.get('file_path', 'Unknown')}")

            try:
                if result.get('tagged_time') and result.get('modified_time') and result.get('tagged_time') > result.get('modified_time'):
                    logger.info(f"Skipping file, already tagged: {result.get('file_path', 'Unknown')}")
                    # 导入update语句
                    from sqlmodel import update
                    stmt = update(FileScreeningResult).where(
                        FileScreeningResult.id == result['id']
                    ).values(status=FileScreenResult.PROCESSED.value)
                    with Session(self.engine) as session:
                        session.exec(stmt)
                        session.commit()
                    success_count += 1
                    continue
                
                # 使用优化版本，避免长事务锁定
                if self.parse_and_tag_file_optimized(result['id']):
                    success_count += 1
                else:
                    failed_count += 1
                file_process_duration = time.time() - file_process_start_time
                logger.info(f"[FILE_TAGGING_BATCH] Finished file {processed_count}/{total_files}. Duration: {file_process_duration:.2f}s")
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"Error processing {result.get('file_path', 'Unknown')}: {e}")
                # 注意：这里不能调用session.rollback()，因为此时没有active session
                try:                    
                    stmt = update(FileScreeningResult).where(
                        FileScreeningResult.id == result['id']
                    ).values(
                        status=FileScreenResult.FAILED.value,
                        error_message=f"Unexpected error: {e}"
                    )
                    with Session(self.engine) as session:
                        session.exec(stmt)
                        session.commit()
                except Exception as inner_e:
                    logger.error(f"Failed to mark file as failed: {inner_e}")
                failed_count += 1

        total_duration = time.time() - start_time
        logger.info(f"[FILE_TAGGING_BATCH] Finished batch. Duration: {total_duration:.2f}s")
        logger.info(f"Processed {processed_count} files. Succeeded: {success_count}, Failed: {failed_count}")
        return {"success": True, "processed": processed_count, "success_count": success_count, "failed_count": failed_count}

    def process_single_file_task(self, screening_result_id: int) -> bool:
        """
        Processes a single high-priority file parsing task.
        使用优化版本，避免长事务锁定
        """
        logger.info(f"[PARSING_SINGLE] Starting to process high-priority file task for screening_result_id: {screening_result_id}")
        
        # 直接使用优化版本，自动处理三步分离
        return self.parse_and_tag_file_optimized(screening_result_id)


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
        test_logger = logging.getLogger()
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
    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')

    # 测试文件路径
    import pathlib
    user_home = pathlib.Path.home()
    test_file_path = user_home / "Documents" / "纯CSS实现太极动态效果.pdf"
    if not test_file_path.exists():
        test_logger.error(f"测试文件不存在: {test_file_path}")
        raise FileNotFoundError(f"测试文件不存在: {test_file_path}")
    
    test_logger.info(f"测试文件: {test_file_path}")
    
    # 创建解析管理器实例进行测试
    db_directory = os.path.dirname(TEST_DB_PATH)
    lancedb_mgr = LanceDBMgr(base_dir=db_directory)
    models_mgr = ModelsMgr(engine, base_dir=db_directory)
    file_tagging_mgr = FileTaggingMgr(engine, lancedb_mgr, models_mgr)
    print(file_tagging_mgr.check_file_tagging_model_availability())
    
    # 测试示例：
    # # 1. 测试内容提取
    # extracted_content = file_tagging_mgr._extract_content(test_file_path.as_posix())
    # test_logger.info(f"提取内容长度: {len(extracted_content) if extracted_content else 0}")
    
    # 2. 测试文件解析和标签生成
    from screening_mgr import ScreeningManager
    screening_mgr = ScreeningManager(engine)
    result: FileScreeningResult = screening_mgr.get_by_path(test_file_path.as_posix())
    if result:
        test_logger.info(f"找到粗筛结果ID: {result.id}")
        success = file_tagging_mgr.process_single_file_task(result.id)
        # file_tagging_mgr.session.commit()
        test_logger.info(f"解析和标签生成结果: {success}")
    else:
        test_logger.warning("未找到对应的粗筛结果")
    
    test_logger.info("解析管理器功能测试完成")
