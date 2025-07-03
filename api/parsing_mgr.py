from sqlmodel import Session, create_engine
from datetime import datetime
from typing import List, Dict, Any
import os
import logging
import warnings
from tagging_mgr import TaggingMgr
from db_mgr import FileScreeningResult, Tags
from markitdown import MarkItDown
from openai import OpenAI

logger = logging.getLogger(__name__)

def configure_parsing_warnings():
    """
    配置解析相关的警告过滤器。
    在应用启动时调用此函数可以抑制markitdown和pdfminer的警告。
    """
    # 过滤掉pdfminer的字体警告
    warnings.filterwarnings("ignore", category=UserWarning, module="pdfminer")
    warnings.filterwarnings("ignore", category=Warning, module="pdfminer")
    warnings.filterwarnings("ignore", category=UserWarning, module="markitdown")
    
    # 设置日志级别
    logging.getLogger('pdfminer').setLevel(logging.ERROR)
    logging.getLogger('markitdown').setLevel(logging.ERROR)
    
    logger.info("Parsing warnings configuration applied")

# 可被markitdown解析的文件扩展名
MARKITDOWN_EXTENSIONS = ['pdf', 'pptx', 'docx', 'xlsx', 'xls']
# 所有可解析的文件扩展名
PARSEABLE_EXTENSIONS = ['md', 'markdown', 'txt', 'json'] + MARKITDOWN_EXTENSIONS

class ParsingMgr:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.tagging_mgr = TaggingMgr(session)
        
        # 配置日志记录器，抑制markitdown和pdfminer的警告
        logging.getLogger('pdfminer').setLevel(logging.ERROR)
        logging.getLogger('markitdown').setLevel(logging.ERROR)
        
        self.md_parser = MarkItDown(enable_plugins=False)
        # Configure OpenAI client to connect to a local LLM service like Ollama/LMStudio
        self.llm_client = OpenAI(
            base_url="http://localhost:1234/v1/",
            api_key="sk-xxx",
        )
        self._use_model = "google/gemma-3-4b" # A fast and capable model for this task

    def parse_and_tag_file(self, screening_result: FileScreeningResult) -> bool:
        """
        Parses the content of a file, generates tags using an LLM, 
        and links them to the file. Does NOT commit the session.
        """
        if not screening_result or not screening_result.file_path or not os.path.exists(screening_result.file_path):
            logger.warning(f"Skipping parsing for non-existent file: {screening_result.file_path if screening_result else 'N/A'}")
            return False

        # 1. Extract content
        try:
            content = self._extract_content(screening_result.file_path)
            if content == '':
                # logger.info(f"No content extracted from {screening_result.file_path}. Skipping tagging.")
                # self._update_tagged_time(screening_result)
                return True # Mark as processed even if no content
        except Exception as e:
            logger.error(f"Error extracting content from {screening_result.file_path}: {e}")
            screening_result.error_message = f"Content extraction failed: {e}"
            # No commit here
            return False

        # 2. Generate tags with LLM
        try:
            generated_tag_names = self._generate_tags_with_llm(screening_result, content)
            if not generated_tag_names:
                logger.info(f"LLM did not generate any tags for {screening_result.file_path}. Skipping linking.")
                self._update_tagged_time(screening_result)
                return True
        except Exception as e:
            logger.error(f"Error generating tags for {screening_result.file_path}: {e}")
            screening_result.error_message = f"Tag generation failed: {e}"
            # No commit here
            return False

        # 3. Get or create tag objects
        tags = self.tagging_mgr.get_or_create_tags(generated_tag_names, tag_type='llm')
        tag_ids = [tag.id for tag in tags]

        # 4. Link tags to the file
        success = self.tagging_mgr.link_tags_to_file(screening_result, tag_ids)
        if success:
            self._update_tagged_time(screening_result)
            logger.info(f"Successfully linked {len(tag_ids)} tags to {screening_result.file_path}")
        else:
            logger.error(f"Failed to link tags to {screening_result.file_path}")
            screening_result.error_message = "Failed to link tags."
            # No commit here

        return success

    def _extract_content(self, file_path: str) -> str:
        """Extracts text content from a file."""
        ext = file_path.split('.')[-1].lower()
        if ext in MARKITDOWN_EXTENSIONS:
            try:
                # 临时禁用特定日志记录器
                pdfminer_logger = logging.getLogger('pdfminer')
                original_level = pdfminer_logger.level
                pdfminer_logger.setLevel(logging.ERROR)  # 仅显示ERROR及以上级别
                
                result = self.md_parser.convert(file_path, keep_data_uris=True)
                
                # 恢复原始日志级别
                pdfminer_logger.setLevel(original_level)
                return result.text_content
            except Exception as e:
                logger.error(f"Error parsing file {file_path}: {e}")
                return ""
        elif ext in ['md', 'markdown', 'txt', 'json']:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        else:
            # logger.warning(f"Unsupported file type for parsing: {ext}")
            return ""

    def _generate_tags_with_llm(self, screening_result: FileScreeningResult, content: str) -> List[str]:
        """Generates tags for a file using an LLM."""
        existing_tag_names = self.tagging_mgr.get_all_tag_names_from_cache()

        # Truncate content to fit within the LLM's context window
        max_content_length = 4000 # A safe limit for many models
        truncated_content = content[:max_content_length]

        prompt = self._build_prompt(screening_result, truncated_content, existing_tag_names)

        try:
            response = self.llm_client.chat.completions.create(
                model=self._use_model,
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing file content and metadata to generate relevant tags. Respond with a comma-separated list of tags and nothing else."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=100,
            )
            # Assuming the model returns a comma-separated string of tags
            print(response)
            tags_string = response.choices[0].message.content.strip()
            if tags_string:
                return [tag.strip() for tag in tags_string.split(',') if tag.strip()]
            return []
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            raise

    def _build_prompt(self, screening_result: FileScreeningResult, content_snippet: str, existing_tags: List[str]) -> str:
        """
        Builds a detailed prompt for the LLM to generate tags.
        """
        prompt = f"""
        Analyze the following file information and generate 3-5 relevant tags.
        Choose from the existing tags if they are a good fit, otherwise create new, specific tags.
        Do not use generic tags like 'document' or 'file'.

        **File Information:**
        - **File Name:** {screening_result.file_name}
        - **File Path:** {screening_result.file_path}
        - **File Size:** {screening_result.file_size} bytes
        - **Modified Time:** {screening_result.modified_time}
        - **Initial Labels (from rules):** {screening_result.labels}

        **Existing Tags Library (for reference):**
        {', '.join(existing_tags)}

        **Content Snippet:**
        ---
        {content_snippet}
        ---

        Based on all the information above, what are the best tags for this file?
        Respond with a comma-separated list of tags. For example: project-alpha, quarterly-report, marketing, 2025
        """
        return prompt

    def _update_tagged_time(self, screening_result: FileScreeningResult):
        """Updates the tagged_time for a screening result object. Does not commit."""
        if screening_result:
            screening_result.tagged_time = datetime.now()
            self.session.add(screening_result)
    
    def create_rough_parse_task(self, file_path: str) -> int:
        """
        Creates a rough parse task for a file.
        This is a placeholder for future implementation.
        """
        # In a real application, you would create a task in the database
        # and return its ID. Here we just log the action.
        logger.info(f"Creating rough parse task for file: {file_path}")
        
        # For now, we return a dummy task ID
        return 1
    
    def process_all_pending_parsing_results(self) -> Dict[str, Any]:
        """
        Processes all pending file screening results to parse and tag them.
        """
        from db_mgr import FileScreenResult
        from sqlmodel import select
        import time

        results = self.session.exec(
            select(FileScreeningResult).where(FileScreeningResult.status == FileScreenResult.PENDING.value)
        ).all()

        if not results:
            logger.info("No pending parsing results to process.")
            return {"success": True, "processed": 0, "success_count": 0, "failed_count": 0}

        processed_count = 0
        success_count = 0
        failed_count = 0

        for result in results:
            processed_count += 1
            try:
                if self.parse_and_tag_file(result):
                    result.status = FileScreenResult.PROCESSED.value
                    success_count += 1
                else:
                    result.status = FileScreenResult.FAILED.value
                    failed_count += 1
                
                # 提交单条记录的变更
                self.session.commit()
                # 添加微小延时，平滑系统负载
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"An unexpected error occurred while processing {result.file_path}: {e}")
                self.session.rollback()
                # 标记为失败并继续处理下一个
                try:
                    result.status = FileScreenResult.FAILED.value
                    result.error_message = f"Unexpected error: {e}"
                    self.session.add(result)
                    self.session.commit()
                except Exception as inner_e:
                    logger.error(f"Failed to mark file as failed after error: {inner_e}")
                    self.session.rollback()
                
                failed_count += 1

        logger.info(f"Processed {processed_count} files. Succeeded: {success_count}, Failed: {failed_count}")
        return {"success": True, "processed": processed_count, "success_count": success_count, "failed_count": failed_count}
    
    def create_sophisticated_parse_task(self, file_path: str) -> int:
        """
        Creates a sophisticated parse task for a file.
        This is a placeholder for future implementation.
        """
        # In a real application, you would create a task in the database
        # and return its ID. Here we just log the action.
        logger.info(f"Creating sophisticated parse task for file: {file_path}")
        
        # For now, we return a dummy task ID
        return 2

# 测试用代码
if __name__ == "__main__":
    # 配置根日志记录器
    logging.basicConfig(level=logging.INFO)
    
    # 特别设置pdfminer库的日志级别为ERROR，抑制WARNING消息
    logging.getLogger('pdfminer').setLevel(logging.ERROR)
    logging.getLogger('markitdown').setLevel(logging.ERROR)
    
    # 配置自定义日志记录器
    handler = logging.FileHandler('p1.log', mode='w')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    db_file = "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db"
    session = Session(create_engine(f'sqlite:///{db_file}'))

    test_file_path = "/Users/dio/Documents/纯CSS实现太极动态效果.pdf"
    
    # 测试从指定全路径的文件中提取内容
    parsing_mgr = ParsingMgr(session)
    # extracted_content = parsing_mgr._extract_content(test_file_path)
    # print("提取的内容:\n", extracted_content)

    # 测试从粗筛结果表中得到一条记录，使用LLM生成标签
    # from screening_mgr import ScreeningManager
    # screening_mgr = ScreeningManager(session)
    # result: FileScreeningResult = screening_mgr.get_by_path(test_file_path)
    # print(result.id)
    # r = parsing_mgr.parse_and_tag_file(result)
    # parsing_mgr.session.commit()  # 提交更改
    # print(f"Parsing and tagging result: {r}")

    print(parsing_mgr.process_files_for_task(17))
