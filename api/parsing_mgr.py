from sqlmodel import Session, create_engine
from datetime import datetime
from typing import List, Dict, Any
import os
import logging
from tagging_mgr import TaggingMgr
from db_mgr import FileScreeningResult, Tags
from markitdown import MarkItDown
from openai import OpenAI

logger = logging.getLogger(__name__)

# 可被markitdown解析的文件扩展名
MARKITDOWN_EXTENSIONS = ['pdf', 'pptx', 'docx', 'xlsx', 'xls']
# 所有可解析的文件扩展名
PARSEABLE_EXTENSIONS = ['md', 'markdown', 'txt', 'json'] + MARKITDOWN_EXTENSIONS

class ParsingMgr:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.tagging_mgr = TaggingMgr(session)
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
        and links them to the file.
        """
        if not screening_result or not screening_result.file_path or not os.path.exists(screening_result.file_path):
            logger.warning(f"Skipping parsing for non-existent file: {screening_result.file_path if screening_result else 'N/A'}")
            return False

        # 1. Extract content
        try:
            content = self._extract_content(screening_result.file_path)
            if not content:
                logger.info(f"No content extracted from {screening_result.file_path}. Skipping tagging.")
                self._update_tagged_time(screening_result.id)
                return True # Mark as processed even if no content
        except Exception as e:
            logger.error(f"Error extracting content from {screening_result.file_path}: {e}")
            screening_result.error_message = f"Content extraction failed: {e}"
            self.session.commit()
            return False

        # 2. Generate tags with LLM
        try:
            generated_tag_names = self._generate_tags_with_llm(screening_result, content)
            if not generated_tag_names:
                logger.info(f"LLM did not generate any tags for {screening_result.file_path}. Skipping linking.")
                self._update_tagged_time(screening_result.id)
                return True
        except Exception as e:
            logger.error(f"Error generating tags for {screening_result.file_path}: {e}")
            screening_result.error_message = f"Tag generation failed: {e}"
            self.session.commit()
            return False

        # 3. Get or create tag objects
        tags = self.tagging_mgr.get_or_create_tags(generated_tag_names, tag_type='llm')
        tag_ids = [tag.id for tag in tags]

        # 4. Link tags to the file
        success = self.tagging_mgr.link_tags_to_file(screening_result.id, tag_ids)
        if success:
            self._update_tagged_time(screening_result.id)
            logger.info(f"Successfully linked {len(tag_ids)} tags to {screening_result.file_path}")
        else:
            logger.error(f"Failed to link tags to {screening_result.file_path}")
            screening_result.error_message = "Failed to link tags."
            self.session.commit()

        return success

    def _extract_content(self, file_path: str) -> str:
        """Extracts text content from a file."""
        ext = file_path.split('.')[-1].lower()
        if ext in MARKITDOWN_EXTENSIONS:
            try:
                result = self.md_parser.convert(file_path, keep_data_uris=True)
                return result.text_content
            except Exception as e:
                logger.error(f"Error parsing Markdown file {file_path}: {e}")
                return ""
        elif ext in ['md', 'markdown', 'txt', 'json']:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        else:
            logger.warning(f"Unsupported file type for parsing: {ext}")
            return ""

    def _generate_tags_with_llm(self, screening_result: FileScreeningResult, content: str) -> List[str]:
        """Generates tags for a file using an LLM."""
        all_tags = self.tagging_mgr.get_all_tags()
        existing_tag_names = [tag.name for tag in all_tags]

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

    def _update_tagged_time(self, screening_result_id: int):
        """Updates the tagged_time for a screening result."""
        result = self.session.get(FileScreeningResult, screening_result_id)
        if result:
            result.tagged_time = datetime.now()
            self.session.commit()
    
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
        pass
    
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
    db_file = "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db"
    session = Session(create_engine(f'sqlite:///{db_file}'))

    test_file_path = "/Users/dio/Documents/意语相生公司介绍 v2025-06-26.pdf"
    
    # 测试从指定全路径的文件中提取内容
    parsing_mgr = ParsingMgr(session)
    extracted_content = parsing_mgr._extract_content(test_file_path)
    print("提取的内容:\n", extracted_content)

    # 测试从粗筛结果表中得到一条记录，使用LLM生成标签
    from screening_mgr import ScreeningManager
    screening_mgr = ScreeningManager(session)
    result: FileScreeningResult = screening_mgr.get_by_path(test_file_path)
    print(result.id)
    r = parsing_mgr.parse_and_tag_file(result)
    print(f"Parsing and tagging result: {r}")
