"""
多模态分块管理器 (ChunkingMgr)

负责使用docling解析文档，实现分层分块策略，生成父块和子块，
并调用模型进行图片描述生成和文本向量化。

核心功能：
1. 使用docling解析PDF/PPT/DOCX等文档
2. 基于docling的body/groups结构实现分层分块
3. 调用vision模型生成图片/表格描述
4. 调用embedding模型进行向量化
5. 存储到SQLite(元数据)和LanceDB(向量)
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from uuid import uuid4

# 生成短ID的工具函数（替代nanoid）
def generate_vector_id() -> str:
    """生成用于vector_id的短ID"""
    return str(uuid4()).replace('-', '')[:16]

from sqlmodel import Session
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PictureDescriptionApiOptions,
    PdfPipelineOptions,
    RapidOcrOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import (
    DoclingDocument,
    ImageRefMode,
    PictureItem,
    TableItem,
    TextItem,
)
from docling.datamodel.document import ConversionResult
from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from transformers import AutoTokenizer

from db_mgr import Document, ParentChunk, ChildChunk
from lancedb_mgr import LanceDBMgr
from models_mgr import ModelsMgr
from model_config_mgr import ModelConfigMgr
from bridge_events import BridgeEventSender

logger = logging.getLogger(__name__)

class ChunkingMgr:
    """多模态分块管理器"""
    
    def __init__(self, session: Session, lancedb_mgr: LanceDBMgr, models_mgr: ModelsMgr):
        """
        初始化分块管理器
        
        Args:
            session: SQLModel数据库会话
            lancedb_mgr: LanceDB向量数据库管理器
            models_mgr: 模型管理器（用于调用vision和embedding模型）
        """
        self.session = session
        self.lancedb_mgr = lancedb_mgr
        self.models_mgr = models_mgr
        self.model_config_mgr = ModelConfigMgr(session)
        
        # 获取数据库目录作为基础路径
        self._init_base_paths()
        
        # 初始化桥接事件发送器
        self.bridge_events = BridgeEventSender(source="chunking-manager")
        
        # 获取当前视觉模型配置
        self.vision_api_endpoint, self.vision_model_id = self.model_config_mgr.get_vision_model_config()
        
        # 获取embedding维度配置
        from config import EMBEDDING_DIMENSIONS
        self.embedding_dimensions = EMBEDDING_DIMENSIONS

        # 初始化docling转换器
        self._init_docling_converter()
        
        # 初始化chunker
        self._init_chunker()
        
        logger.info("ChunkingMgr initialized successfully")
    
    def _init_base_paths(self):
        """初始化基础路径，使用数据库目录的父目录"""
        try:
            # 尝试从LanceDB获取路径
            if hasattr(self.lancedb_mgr, 'db') and hasattr(self.lancedb_mgr.db, 'uri'):
                lancedb_path = Path(self.lancedb_mgr.db.uri)
                self.data_base_dir = lancedb_path.parent
            else:
                # 从SQLite连接获取路径
                sqlite_url = str(self.session.bind.url)
                if sqlite_url.startswith('sqlite:///'):
                    sqlite_path = Path(sqlite_url.replace('sqlite:///', ''))
                    self.data_base_dir = sqlite_path.parent
                else:
                    # 备用方案：使用当前目录
                    self.data_base_dir = Path.cwd()
            
            # 创建docling缓存目录
            self.docling_cache_dir = self.data_base_dir / "docling_cache"
            self.docling_cache_dir.mkdir(exist_ok=True)
            
            logger.info(f"Data base directory: {self.data_base_dir}")
            logger.info(f"Docling cache directory: {self.docling_cache_dir}")
            
        except Exception as e:
            logger.error(f"Failed to initialize base paths: {e}")
            # 备用方案
            self.data_base_dir = Path.cwd()
            self.docling_cache_dir = self.data_base_dir / "docling_cache"
            self.docling_cache_dir.mkdir(exist_ok=True)
    
    def _init_docling_converter(self):
        """初始化docling文档转换器，参考test_docling_01.py的配置"""
        try:
            # 配置PDF处理选项
            pipeline_options = PdfPipelineOptions()
            pipeline_options.generate_picture_images = True
            # pipeline_options.generate_page_images = True
            pipeline_options.images_scale = 2.0  # 图片分辨率scale
            pipeline_options.do_picture_description = True
            pipeline_options.enable_remote_services = True  # 启用远程服务用于图片描述
            
            # 配置图片描述API选项 - 使用本地vision模型
            pipeline_options.picture_description_options = PictureDescriptionApiOptions(
                url=f"{self.vision_api_endpoint}/chat/completions",
                params=dict(
                    model=self.vision_model_id,
                    seed=42,
                    temperature=0.2,
                    max_completion_tokens=250,
                ),
                prompt="""
You are an assistant tasked with summarizing images for retrieval. 
These summaries will be embedded and used to retrieve the raw image. 
Give a concise summary of the image that is well optimized for retrieval.
""".strip(),
                timeout=180,
            )
            
            # 配置OCR选项 - 使用RapidOCR
            # print("Downloading RapidOCR models")
            # download_path = snapshot_download(repo_id="SWHL/RapidOCR") # from HuggingFace
            # # Setup RapidOcrOptions for english detection
            # det_model_path = os.path.join(download_path, "PP-OCRv4", "en_PP-OCRv3_det_infer.onnx")
            # rec_model_path = os.path.join(download_path, "PP-OCRv4", "ch_PP-OCRv4_rec_server_infer.onnx")
            # cls_model_path = os.path.join(download_path, "PP-OCRv3", "ch_ppocr_mobile_v2.0_cls_train.onnx")
            # ocr_options = RapidOcrOptions(
            #     det_model_path=det_model_path,
            #     rec_model_path=rec_model_path,
            #     cls_model_path=cls_model_path,
            # )
            # pipeline_options.do_ocr = True
            # pipeline_options.ocr_options = ocr_options
            
            # 创建文档转换器
            self.converter = DocumentConverter(format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                )
            })
            
            logger.info("Docling converter initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize docling converter: {e}")
            raise
    
    def _init_chunker(self):
        """初始化Docling原生chunker，基于最佳实践配置"""
        try:
            # 关键设计决策：chunker的tokenizer与embedding模型解耦
            # 
            # 原因：
            # 1. HybridChunker的tokenizer主要用于chunk大小控制，不需要与embedding模型完全一致
            # 2. 我们通过API调用embedding服务（ollama/lm_studio），无法直接使用其tokenizer
            # 3. 使用通用tokenizer进行近似估算更稳定可靠
            
            # 使用通用的中英文友好tokenizer作为chunk大小估算器
            try:
                # 优先尝试使用一个通用的多语言tokenizer
                tokenizer = HuggingFaceTokenizer(
                    tokenizer=AutoTokenizer.from_pretrained("microsoft/multilingual-MiniLM-L12-H384"),
                    max_tokens=512,  # 保守的chunk大小，确保embedding API调用稳定
                )
                logger.info("Using multilingual tokenizer for chunking")
            except Exception as e:
                logger.warning(f"Failed to load multilingual tokenizer: {e}")
                try:
                    # 备用方案：使用BERT tokenizer
                    tokenizer = HuggingFaceTokenizer(
                        tokenizer=AutoTokenizer.from_pretrained("bert-base-uncased"),
                        max_tokens=512,
                    )
                    logger.info("Using BERT tokenizer as fallback for chunking")
                except Exception as e2:
                    logger.error(f"Failed to load any tokenizer: {e2}")
                    raise Exception(f"Cannot initialize any tokenizer. Primary error: {e}, Fallback error: {e2}")
            
            # 创建HybridChunker实例
            self.chunker = HybridChunker(
                tokenizer=tokenizer,
                merge_peers=True,  # 合并相邻的同类chunk
            )
            
            logger.info(f"Chunker initialized with max_tokens={tokenizer.get_max_tokens()}")
            logger.info("Note: Chunker tokenizer is decoupled from embedding model - embeddings generated via API")
            
        except Exception as e:
            logger.error(f"Failed to initialize chunker: {e}")
            raise
    
    def process_document(self, file_path: str) -> bool:
        """
        处理单个文档的完整流程
        
        Args:
            file_path: 文档文件的绝对路径
            
        Returns:
            bool: 处理是否成功
        """
        try:
            logger.info(f"[CHUNKING] Starting document processing: {file_path}")
            self.bridge_events.progress_update("multivector", 0, 100, "开始解析文档...")
            
            # 1. 验证文件
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            # 2. 计算文件hash
            file_hash = self._calculate_file_hash(file_path)
            
            # 3. 检查是否已处理过且文件未变更
            existing_doc = self._get_existing_document(file_path, file_hash)
            if existing_doc:
                logger.info(f"[CHUNKING] Document already processed and unchanged: {file_path}")
                self.bridge_events.progress_update("multivector", 100, 100, "文档已处理，无需重复处理")
                return True
            
            # 4. 使用docling解析文档
            self.bridge_events.progress_update("multivector", 20, 100, "正在解析文档结构...")
            docling_result = self._parse_with_docling(file_path)
            
            # 5. 保存docling解析结果
            docling_json_path = self._save_docling_result(file_path, docling_result)
            
            # 6. 创建/更新Document记录
            self.bridge_events.progress_update("multivector", 40, 100, "创建文档记录...")
            document = self._create_or_update_document(file_path, file_hash, docling_json_path)
            
            # 7. 生成父块和子块
            self.bridge_events.progress_update("multivector", 60, 100, "生成内容块...")
            parent_chunks, child_chunks = self._generate_chunks(document.id, docling_result.document)
            
            # 8. 存储到数据库
            self.bridge_events.progress_update("multivector", 80, 100, "存储到数据库...")
            self._store_chunks(parent_chunks, child_chunks)
            
            # 8.5. 为图片chunks创建图文关系子块（关键设计）
            self.bridge_events.progress_update("multivector", 85, 100, "创建图文关系子块...")
            all_parent_chunks, all_child_chunks = self._create_image_context_chunks(parent_chunks, child_chunks, document.id)
            
            # 如果创建了额外的上下文块，更新chunk列表
            if len(all_parent_chunks) > len(parent_chunks):
                additional_parent_chunks = all_parent_chunks[len(parent_chunks):]
                additional_child_chunks = all_child_chunks[len(child_chunks):]
                
                # 存储额外的上下文块
                self._store_chunks(additional_parent_chunks, additional_child_chunks)
                logger.info(f"Stored {len(additional_parent_chunks)} additional image context chunks")
                
                # 更新用于向量化的chunk列表
                parent_chunks = all_parent_chunks
                child_chunks = all_child_chunks
            
            # 9. 向量化和存储
            self.bridge_events.progress_update("multivector", 90, 100, "向量化和存储...")
            self._vectorize_and_store(parent_chunks, child_chunks)
            
            # 10. 更新文档状态
            document.status = "done"
            document.processed_at = datetime.now()
            self.session.add(document)
            self.session.commit()
            
            self.bridge_events.progress_update("multivector", 100, 100, "文档处理完成")
            logger.info(f"[CHUNKING] Document processing completed: {file_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"[CHUNKING] Document processing failed for {file_path}: {e}", exc_info=True)
            self.bridge_events.error_occurred("chunking_error", f"文档处理失败: {str(e)}", {
                "file_path": file_path,
                "error_type": type(e).__name__
            })
            
            # 更新文档状态为错误
            try:
                document = self._get_or_create_document_record(file_path, "", "")
                document.status = "error"
                self.session.add(document)
                self.session.commit()
            except:
                pass  # 忽略状态更新错误
            
            return False
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件hash值"""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                # 对于大文件，只读取部分内容计算hash
                chunk_size = 8192
                while chunk := f.read(chunk_size):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate hash for {file_path}: {e}")
            return ""
    
    def _get_existing_document(self, file_path: str, file_hash: str) -> Optional[Document]:
        """检查是否存在相同hash的文档记录"""
        try:
            from sqlmodel import select
            stmt = select(Document).where(
                Document.file_path == file_path,
                Document.file_hash == file_hash,
                Document.status == "done"
            )
            return self.session.exec(stmt).first()
        except Exception as e:
            logger.error(f"Failed to check existing document: {e}")
            return None
    
    def _parse_with_docling(self, file_path: str) -> ConversionResult:
        """使用docling解析文档"""
        try:
            logger.info(f"[CHUNKING] Parsing document with docling: {file_path}")
            result = self.converter.convert(source=file_path)
            
            if not result or not result.document:
                raise ValueError("Docling parsing returned empty result")
            
            logger.info(f"[CHUNKING] Docling parsing completed. Document has {len(result.document.pages)} pages")
            return result
            
        except Exception as e:
            logger.error(f"Docling parsing failed for {file_path}: {e}")
            raise
    
    def _save_docling_result(self, file_path: str, result: ConversionResult) -> str:
        """保存docling解析结果到JSON文件"""
        try:
            # 使用数据库目录的docling_cache子目录
            output_dir = self.docling_cache_dir
            
            # 生成JSON文件名（直接使用原文件名，不拼接时间戳）
            file_stem = Path(file_path).stem
            json_filename = f"{file_stem}.json"
            json_path = output_dir / json_filename
            
            # 保存JSON
            result.document.save_as_json(
                filename=json_path,
                indent=2,
                image_mode=ImageRefMode.PLACEHOLDER,
                artifacts_dir=output_dir
            )
            
            logger.info(f"[CHUNKING] Docling result saved to: {json_path}")
            return str(json_path)
            
        except Exception as e:
            logger.error(f"Failed to save docling result: {e}")
            # 返回空字符串表示保存失败，但不影响主流程
            return ""
    
    def _create_or_update_document(self, file_path: str, file_hash: str, docling_json_path: str) -> Document:
        """创建或更新Document记录"""
        try:
            from sqlmodel import select
            
            # 尝试获取现有记录
            stmt = select(Document).where(Document.file_path == file_path)
            document = self.session.exec(stmt).first()
            
            if document:
                # 更新现有记录
                document.file_hash = file_hash
                document.docling_json_path = docling_json_path
                document.status = "processing"
                document.processed_at = datetime.now()
            else:
                # 创建新记录
                document = Document(
                    file_path=file_path,
                    file_hash=file_hash,
                    docling_json_path=docling_json_path,
                    status="processing",
                    processed_at=datetime.now()
                )
            
            self.session.add(document)
            self.session.commit()
            self.session.refresh(document)
            
            logger.info(f"[CHUNKING] Document record created/updated: ID={document.id}")
            return document
            
        except Exception as e:
            logger.error(f"Failed to create/update document record: {e}")
            raise
    
    def _get_or_create_document_record(self, file_path: str, file_hash: str, docling_json_path: str) -> Document:
        """获取或创建文档记录（辅助方法）"""
        try:
            return self._create_or_update_document(file_path, file_hash, docling_json_path)
        except:
            # 如果创建失败，返回一个临时对象
            return Document(
                file_path=file_path,
                file_hash=file_hash,
                docling_json_path=docling_json_path,
                status="error"
            )
    
    def _generate_chunks(self, document_id: int, docling_doc: DoclingDocument) -> Tuple[List[ParentChunk], List[ChildChunk]]:
        """
        使用Docling HybridChunker进行智能分块
        
        设计思路：
        1. 使用Docling的HybridChunker进行语义感知的分块
        2. chunker的tokenizer仅用于chunk大小控制，与embedding模型解耦
        3. 实际embedding生成通过API调用完成，支持Qwen3-Embedding-0.6B等模型
        4. 采用父子块架构，父块用于检索，子块保留细节
        
        Args:
            document_id: 文档ID
            docling_doc: Docling解析的文档对象
            
        Returns:
            (parent_chunks, child_chunks): 父块和子块的元组
        """
        logger.info(f"[CHUNKING] Generating chunks using HybridChunker for document ID: {document_id}")
        
        all_parent_chunks = []
        all_child_chunks = []
        
        try:
            # 使用HybridChunker生成chunks
            chunk_iter = self.chunker.chunk(dl_doc=docling_doc)
            chunks = list(chunk_iter)
            
            logger.info(f"[CHUNKING] HybridChunker generated {len(chunks)} chunks")
            
            # 为每个chunk创建父块和对应的子块
            for i, chunk in enumerate(chunks):
                try:
                    # 获取原始chunk文本 - 用于父块（保持数据纯净性）
                    raw_content = chunk.text
                    
                    # 获取上下文丰富的内容 - 仅用于子块摘要生成
                    contextualized_content = self.chunker.contextualize(chunk=chunk)
                    
                    # 确定chunk类型
                    chunk_type = self._determine_chunk_type(chunk)
                    
                    logger.debug(f"[CHUNKING] Chunk {i}: type={chunk_type}, raw_length={len(raw_content)}, contextualized_length={len(contextualized_content)}")
                    
                    # 如果是图片类型且包含混合内容，需要进行分割处理
                    if chunk_type == "image" and self._contains_mixed_content(raw_content):
                        logger.debug(f"[CHUNKING] Chunk {i} contains mixed content, splitting...")
                        # 分割混合内容为纯图片描述和纯文本部分
                        sub_chunks = self._split_mixed_chunk(chunk, document_id, i)
                        all_parent_chunks.extend([sc[0] for sc in sub_chunks])
                        all_child_chunks.extend([sc[1] for sc in sub_chunks])
                    else:
                        # 正常处理单一类型的chunk
                        parent_chunk, child_chunk = self._create_chunk_pair(
                            chunk, document_id, i, chunk_type, raw_content, contextualized_content
                        )
                        all_parent_chunks.append(parent_chunk)
                        all_child_chunks.append(child_chunk)
                    
                except Exception as e:
                    logger.error(f"Failed to process chunk {i}: {e}")
                    continue
            
            logger.info(f"[CHUNKING] Successfully generated {len(all_parent_chunks)} parent chunks and {len(all_child_chunks)} child chunks")
            
        except Exception as e:
            logger.error(f"Failed to generate chunks using HybridChunker: {e}")
            raise
        
        return all_parent_chunks, all_child_chunks
    
    def _determine_chunk_type(self, chunk) -> str:
        """
        根据chunk的内容和元数据确定类型
        
        注意：我们避免使用"mixed"类型，以保持数据纯净性
        如果chunk包含多种类型，我们会在_generate_chunks中进行拆分处理
        
        Args:
            chunk: HybridChunker生成的chunk对象
            
        Returns:
            chunk类型字符串: "text", "image", "table"
        """
        try:
            # 添加详细的调试信息
            logger.debug(f"[CHUNK_TYPE] Processing chunk with text length: {len(chunk.text)}")
            logger.debug(f"[CHUNK_TYPE] Chunk has meta: {hasattr(chunk, 'meta')}")
            
            if hasattr(chunk.meta, 'doc_items') and chunk.meta.doc_items:
                logger.debug(f"[CHUNK_TYPE] Found {len(chunk.meta.doc_items)} doc_items")
                
                # 检查doc_items中的类型
                item_types = set()
                for i, item in enumerate(chunk.meta.doc_items):
                    item_label = None
                    if hasattr(item, 'label'):
                        item_label = str(item.label)
                        item_types.add(item_label)
                    logger.debug(f"[CHUNK_TYPE] Item {i}: type={type(item).__name__}, label={item_label}")
                
                logger.debug(f"[CHUNK_TYPE] All item types found: {item_types}")
                
                # 优先级：表格 > 图片 > 文本
                # 这样可以确保主要内容类型不被忽略
                if any('TABLE' in item_type.upper() for item_type in item_types):
                    logger.debug(f"[CHUNK_TYPE] Determined type: table")
                    return "table"
                elif any('PICTURE' in item_type.upper() or 'IMAGE' in item_type.upper() for item_type in item_types):
                    logger.debug(f"[CHUNK_TYPE] Determined type: image")
                    return "image"
                else:
                    logger.debug(f"[CHUNK_TYPE] Determined type: text (default)")
                    return "text"
            else:
                logger.debug(f"[CHUNK_TYPE] No doc_items found, defaulting to text")
                # 如果没有元数据，根据内容长度和特征判断
                return "text"
        except Exception as e:
            logger.warning(f"Failed to determine chunk type: {e}")
            return "text"
    
    def _contains_mixed_content(self, content: str) -> bool:
        """
        检测内容是否包含图片描述和文本的混合内容
        
        Args:
            content: 要检测的内容
            
        Returns:
            bool: 是否包含混合内容
        """
        # 检测是否包含图片描述的特征
        # 图片描述通常以特定的句式开头，并且包含图片相关的词汇
        content_lower = content.lower()
        
        # 图片描述的常见开头和特征词
        image_indicators = [
            "the image illustrates",
            "the image shows",
            "the image displays",
            "the diagram shows",
            "the figure illustrates",
            "the chart displays",
            "this image depicts",
            "the visualization shows"
        ]
        
        # 检查是否包含图片描述特征
        has_image_description = any(indicator in content_lower for indicator in image_indicators)
        
        # 检查是否还包含其他文本内容（通常图片描述后会有换行和其他文本）
        lines = content.strip().split('\n')
        has_multiple_sections = len(lines) > 3  # 图片描述通常是1-2行，如果超过3行可能包含其他内容
        
        # 简单的中文内容检测（如果包含大量中文，可能是原文）
        chinese_chars = len([c for c in content if '\u4e00' <= c <= '\u9fff'])
        has_chinese_content = chinese_chars > 50  # 如果中文字符超过50个，可能包含原文
        
        return has_image_description and (has_multiple_sections or has_chinese_content)
    
    def _split_mixed_chunk(self, chunk, document_id: int, chunk_index: int) -> List[Tuple[ParentChunk, ChildChunk]]:
        """
        分割包含混合内容的chunk为多个纯净的chunks
        
        Args:
            chunk: 原始chunk对象
            document_id: 文档ID
            chunk_index: chunk索引
            
        Returns:
            List[Tuple[ParentChunk, ChildChunk]]: 分割后的chunk对列表
        """
        result_chunks = []
        content = chunk.text.strip()
        
        try:
            # 简单的分割策略：通过段落分隔
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
            
            if len(paragraphs) < 2:
                # 如果没有明显的段落分隔，尝试按句子分割
                paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
            
            current_section = []
            current_type = None
            
            for para in paragraphs:
                para_lower = para.lower()
                
                # 判断这个段落是图片描述还是普通文本
                is_image_desc = any(indicator in para_lower for indicator in [
                    "the image", "the diagram", "the figure", "the chart", 
                    "image illustrates", "image shows", "image displays"
                ])
                
                para_type = "image" if is_image_desc else "text"
                
                if current_type is None:
                    current_type = para_type
                    current_section.append(para)
                elif current_type == para_type:
                    current_section.append(para)
                else:
                    # 类型变化，保存当前section并开始新的section
                    if current_section:
                        section_content = '\n\n'.join(current_section)
                        parent_chunk, child_chunk = self._create_chunk_pair(
                            chunk, document_id, f"{chunk_index}_{current_type}", 
                            current_type, section_content, section_content
                        )
                        result_chunks.append((parent_chunk, child_chunk))
                    
                    # 开始新section
                    current_type = para_type
                    current_section = [para]
            
            # 处理最后一个section
            if current_section:
                section_content = '\n\n'.join(current_section)
                parent_chunk, child_chunk = self._create_chunk_pair(
                    chunk, document_id, f"{chunk_index}_{current_type}", 
                    current_type, section_content, section_content
                )
                result_chunks.append((parent_chunk, child_chunk))
            
            logger.debug(f"[CHUNKING] Split chunk {chunk_index} into {len(result_chunks)} sub-chunks")
            
        except Exception as e:
            logger.error(f"Failed to split mixed chunk {chunk_index}: {e}")
            # 如果分割失败，返回原始chunk作为text类型
            parent_chunk, child_chunk = self._create_chunk_pair(
                chunk, document_id, chunk_index, "text", content, content
            )
            result_chunks = [(parent_chunk, child_chunk)]
        
        return result_chunks
    
    def _create_chunk_pair(self, chunk, document_id: int, chunk_index, chunk_type: str, 
                          raw_content: str, contextualized_content: str) -> Tuple[ParentChunk, ChildChunk]:
        """
        创建一对父块和子块
        
        Args:
            chunk: 原始chunk对象
            document_id: 文档ID
            chunk_index: chunk索引
            chunk_type: chunk类型
            raw_content: 原始内容
            contextualized_content: 上下文化内容
            
        Returns:
            Tuple[ParentChunk, ChildChunk]: 父块和子块的元组
        """
        # 创建父块 - 存储原始纯净内容
        parent_chunk = ParentChunk(
            document_id=document_id,
            chunk_type=chunk_type,
            content=raw_content,  # 使用原始内容，保持数据纯净性
            metadata_json=json.dumps({
                "chunk_index": chunk_index,
                "original_text_length": len(raw_content),
                "contextualized_length": len(contextualized_content),
                "doc_items_refs": [item.self_ref for item in chunk.meta.doc_items] if hasattr(chunk.meta, 'doc_items') else [],
                "chunk_id": chunk.meta.chunk_id if hasattr(chunk.meta, 'chunk_id') else None,
                "source": "hybrid_chunker_split" if isinstance(chunk_index, str) else "hybrid_chunker"
            })
        )
        
        # 生成检索友好的子块内容
        retrieval_content = self._generate_retrieval_summary(contextualized_content, chunk_type)
        
        # 创建子块
        child_chunk = ChildChunk(
            parent_chunk_id=0,  # 在存储时会设置正确的ID
            retrieval_content=retrieval_content,
            vector_id=generate_vector_id()
        )
        
        return parent_chunk, child_chunk
    
    def _generate_retrieval_summary(self, content: str, chunk_type: str) -> str:
        """
        使用LLM为chunk内容生成检索友好的摘要
        
        Args:
            content: 完整的chunk内容
            chunk_type: chunk类型
            
        Returns:
            检索优化的摘要文本
        """
        try:
            # 如果内容太短，直接返回原内容
            if len(content.strip()) < 50:
                return content.strip()
            
            # 根据chunk类型选择合适的提示词
            if chunk_type == "table":
                prompt_prefix = """You are an assistant tasked with summarizing tables for retrieval. 
These summaries will be embedded and used to retrieve the raw table elements. 
Give a concise summary of the table that is well optimized for retrieval.

IMPORTANT: Output ONLY the summary content, without any prefixes like "Here's a summary:", "Summary:", or formatting markers."""
            elif chunk_type == "image":
                prompt_prefix = """You are an assistant tasked with summarizing image content for retrieval. 
These summaries will be embedded and used to retrieve the raw image elements. 
Give a concise summary of the image content that is well optimized for retrieval.

IMPORTANT: Output ONLY the summary content, without any prefixes like "Here's a summary:", "Summary:", or formatting markers."""
            else:
                prompt_prefix = """You are an assistant tasked with summarizing text for retrieval. 
These summaries will be embedded and used to retrieve the raw text elements. 
Give a concise summary of the text that is well optimized for retrieval.

IMPORTANT: Output ONLY the summary content, without any prefixes like "Here's a summary:", "Summary:", or formatting markers."""
            
            # 构建完整提示
            messages = [
                {"role": "system", "content": prompt_prefix},
                {"role": "user", "content": f"Content to summarize:\n\n{content}"}
            ]
            
            # 调用LLM生成摘要
            summary = self.models_mgr.get_chat_completion(messages, role_type="base")
            
            if summary and summary.strip():
                # 后处理：清理常见的格式化前缀
                cleaned_summary = self._clean_summary_prefixes(summary.strip())
                return cleaned_summary
            else:
                # 如果LLM生成失败，使用简单的文本截取
                return content[:500] + "..." if len(content) > 500 else content
                
        except Exception as e:
            logger.error(f"Failed to generate retrieval summary: {e}")
            # 降级处理：直接截取内容
            return content[:500] + "..." if len(content) > 500 else content
    
    def _clean_summary_prefixes(self, summary: str) -> str:
        """
        清理LLM生成摘要中的常见格式化前缀
        
        Args:
            summary: 原始摘要文本
            
        Returns:
            清理后的摘要文本
        """
        # 常见的需要清理的前缀模式
        prefixes_to_remove = [
            "Here's a retrieval-optimized summary:",
            "Here's a retrieval-optimized summary of the text:",
            "Here's a retrieval-optimized summary of the image:",
            "Here's a retrieval-optimized summary of the table:",
            "Here's a concise summary:",
            "**Summary:**",
            "Summary:",
            "**Image Summary:**",
            "Image Summary:",
            "**Table Summary:**",
            "Table Summary:",
            "The image",
            "The table",
            "This text"
        ]
        
        cleaned = summary.strip()
        
        # 移除开头的格式化前缀
        for prefix in prefixes_to_remove:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix):].strip()
                break
        
        # 移除开头的冒号、破折号等
        while cleaned and cleaned[0] in [':', '-', '*', ' ']:
            cleaned = cleaned[1:].strip()
        
        return cleaned if cleaned else summary  # 如果清理后为空，返回原始内容
    
    def _create_image_context_chunks(self, parent_chunks: List[ParentChunk], child_chunks: List[ChildChunk], 
                                   document_id: int) -> Tuple[List[ParentChunk], List[ChildChunk]]:
        """
        为图像块创建额外的上下文块（图片描述 + 周围原始文本的摘要）
        这个功能实现了MULTIVECTOR.md中的关键设计：加强图像与文本的关联检索
        
        Args:
            parent_chunks: 现有的父块列表
            child_chunks: 现有的子块列表
            document_id: 文档ID
            
        Returns:
            Tuple[List[ParentChunk], List[ChildChunk]]: 更新后的父块和子块列表
        """
        try:
            additional_parent_chunks = []
            additional_child_chunks = []
            
            # 找到所有图像块
            image_chunks = [(i, chunk) for i, chunk in enumerate(parent_chunks) if chunk.chunk_type == "image"]
            
            if not image_chunks:
                return parent_chunks, child_chunks
            
            logger.info(f"Found {len(image_chunks)} image chunks, creating context chunks...")
            
            for chunk_idx, image_chunk in image_chunks:
                try:
                    # 获取图像描述内容
                    image_description = image_chunk.content
                    if not image_description or len(image_description.strip()) < 10:
                        continue
                    
                    # 获取周围的文本块内容进行摘要
                    surrounding_texts = self._get_surrounding_text_chunks(parent_chunks, chunk_idx)
                    if not surrounding_texts:
                        continue
                    
                    # 生成周围文本的摘要
                    context_summary = self._generate_context_summary(surrounding_texts)
                    if not context_summary:
                        continue
                    
                    # 创建组合内容：图片描述 + 周围文本摘要
                    combined_content = f"图像内容：{image_description}\n\n相关文本背景：{context_summary}"
                    
                    # 创建额外的父块（图像上下文块）
                    context_parent = ParentChunk(
                        document_id=document_id,
                        chunk_type="image_context",
                        content=combined_content,
                        metadata_json=json.dumps({
                            "related_image_chunk_index": chunk_idx,
                            "context_type": "image_with_text_summary",
                            "source": "multivector_image_context",
                            "surrounding_chunks_count": len(surrounding_texts)
                        })
                    )
                    
                    # 生成检索友好的子块内容
                    retrieval_content = self._generate_retrieval_summary(combined_content, "image_context")
                    
                    # 创建对应的子块
                    context_child = ChildChunk(
                        parent_chunk_id=0,  # 在存储时会设置正确的ID
                        retrieval_content=retrieval_content,
                        vector_id=generate_vector_id()
                    )
                    
                    additional_parent_chunks.append(context_parent)
                    additional_child_chunks.append(context_child)
                    
                    logger.debug(f"Created image context chunk for image chunk {chunk_idx}")
                    
                except Exception as e:
                    logger.error(f"Failed to create context chunk for image chunk {chunk_idx}: {e}")
                    continue
            
            # 合并所有块
            all_parent_chunks = parent_chunks + additional_parent_chunks
            all_child_chunks = child_chunks + additional_child_chunks
            
            logger.info(f"Created {len(additional_parent_chunks)} additional image context chunks")
            return all_parent_chunks, all_child_chunks
            
        except Exception as e:
            logger.error(f"Failed to create image context chunks: {e}")
            return parent_chunks, child_chunks
    
    def _get_surrounding_text_chunks(self, parent_chunks: List[ParentChunk], image_chunk_idx: int, 
                                   context_window: int = 2) -> List[str]:
        """
        获取图像块周围的文本块内容
        
        Args:
            parent_chunks: 所有父块列表
            image_chunk_idx: 图像块的索引
            context_window: 前后文本块的数量
            
        Returns:
            List[str]: 周围文本块的内容列表
        """
        surrounding_texts = []
        
        # 获取前面的文本块
        start_idx = max(0, image_chunk_idx - context_window)
        for i in range(start_idx, image_chunk_idx):
            chunk = parent_chunks[i]
            if chunk.chunk_type == "text" and chunk.content:
                surrounding_texts.append(chunk.content)
        
        # 获取后面的文本块
        end_idx = min(len(parent_chunks), image_chunk_idx + context_window + 1)
        for i in range(image_chunk_idx + 1, end_idx):
            chunk = parent_chunks[i]
            if chunk.chunk_type == "text" and chunk.content:
                surrounding_texts.append(chunk.content)
        
        return surrounding_texts
    
    def _generate_context_summary(self, text_chunks: List[str]) -> str:
        """
        为周围的文本块生成摘要
        
        Args:
            text_chunks: 文本块内容列表
            
        Returns:
            str: 生成的摘要
        """
        if not text_chunks:
            return ""
        
        try:
            # 合并文本内容
            combined_text = "\n\n".join(text_chunks)
            
            # 如果文本太短，直接返回
            if len(combined_text.strip()) < 50:
                return combined_text.strip()
            
            # 构建摘要提示
            prompt = """你需要为以下文本内容生成一个简洁的摘要，这个摘要将与图像描述组合，用于增强图像与文本的关联检索。

请生成一个突出主要观点和关键信息的摘要，帮助理解图像在文档中的上下文背景。

重要：只输出摘要内容，不要包含"摘要："、"总结："等前缀。

文本内容：
"""
            
            messages = [
                {"role": "system", "content": "你是一个专业的文本摘要助手，擅长生成简洁准确的摘要。"},
                {"role": "user", "content": f"{prompt}\n\n{combined_text}"}
            ]
            
            # 调用LLM生成摘要
            summary = self.models_mgr.get_chat_completion(messages, role_type="base")
            
            if summary and summary.strip():
                # 清理格式化前缀
                cleaned_summary = self._clean_summary_prefixes(summary.strip())
                return cleaned_summary
            else:
                # 如果LLM生成失败，使用简单截取
                return combined_text[:300] + "..." if len(combined_text) > 300 else combined_text
                
        except Exception as e:
            logger.error(f"Failed to generate context summary: {e}")
            # 降级处理：截取前面部分内容
            combined_text = "\n\n".join(text_chunks)
            return combined_text[:300] + "..." if len(combined_text) > 300 else combined_text
    
    def _store_chunks(self, parent_chunks: List[ParentChunk], child_chunks: List[ChildChunk]):
        """存储父块和子块到SQLite"""
        try:
            if len(parent_chunks) != len(child_chunks):
                raise ValueError(f"Parent chunks count ({len(parent_chunks)}) does not match child chunks count ({len(child_chunks)})")
            
            # 1. 先存储父块
            if parent_chunks:
                self.session.add_all(parent_chunks)
                self.session.commit()
                
                # 刷新以获取生成的ID
                for chunk in parent_chunks:
                    self.session.refresh(chunk)
                
                logger.info(f"[CHUNKING] Stored {len(parent_chunks)} parent chunks")
            
            # 2. 设置子块的parent_chunk_id并存储
            if child_chunks:
                for i, child_chunk in enumerate(child_chunks):
                    child_chunk.parent_chunk_id = parent_chunks[i].id
                
                self.session.add_all(child_chunks)
                self.session.commit()
                
                # 刷新以获取生成的ID
                for chunk in child_chunks:
                    self.session.refresh(chunk)
                
                logger.info(f"[CHUNKING] Stored {len(child_chunks)} child chunks")
            
        except Exception as e:
            logger.error(f"Failed to store chunks: {e}")
            self.session.rollback()
            raise
    
    def _vectorize_and_store(self, parent_chunks: List[ParentChunk], child_chunks: List[ChildChunk]):
        """向量化子块并存储到LanceDB（父块不需要向量化）"""
        try:
            # 确保vectors表已初始化
            self.lancedb_mgr.init_vectors_table()
            
            vector_records = []
            
            # 只处理子块向量化（父块不需要向量化，它们是用于答案合成的原始内容）
            for i, child_chunk in enumerate(child_chunks):
                try:
                    # 调用embedding模型进行向量化
                    embedding = self.models_mgr.get_embedding(child_chunk.retrieval_content)
                    
                    if not embedding:
                        logger.warning(f"Failed to get embedding for child chunk ID: {child_chunk.id}")
                        continue
                    
                    # 从对应的父块获取document_id
                    parent_chunk = parent_chunks[i] if i < len(parent_chunks) else None
                    document_id = parent_chunk.document_id if parent_chunk else 0
                    
                    # 创建子块向量记录
                    vector_record = {
                        "vector_id": child_chunk.vector_id,
                        "vector": embedding,
                        "parent_chunk_id": child_chunk.parent_chunk_id,
                        "document_id": document_id,
                        "retrieval_content": child_chunk.retrieval_content[:500]  # 存储前500字符用于检索显示
                    }
                    vector_records.append(vector_record)
                    
                except Exception as e:
                    logger.error(f"Failed to vectorize child chunk ID {child_chunk.id}: {e}")
                    continue
            
            # 批量存储到LanceDB
            if vector_records:
                self.lancedb_mgr.add_vectors(vector_records)
                logger.info(f"[CHUNKING] Vectorized and stored {len(vector_records)} child chunk vectors")
            
            logger.info(f"[CHUNKING] Vector storage completed - {len(parent_chunks)} parent chunks stored in SQLite only, {len(child_chunks)} child chunks vectorized in LanceDB")
            
        except Exception as e:
            logger.error(f"Failed to vectorize and store: {e}")
            raise


# 为了测试和调试使用
def test_chunking_mgr():
    """测试分块管理器的基本功能"""
    # 1. 初始化各个组件
    logger.info("🔧 初始化组件...")
    # SQLite数据库
    from config import TEST_DB_PATH
    from sqlmodel import create_engine
    session = Session(create_engine(f'sqlite:///{TEST_DB_PATH}'))
    # LanceDB
    db_directory = Path(TEST_DB_PATH).parent
    lancedb_mgr = LanceDBMgr(base_dir=db_directory)
    # 模型管理器
    models_mgr = ModelsMgr(session)
    # 事件发送器
    bridge_events = BridgeEventSender()
    # 分块管理器
    try:
        chunking_mgr = ChunkingMgr(session, lancedb_mgr, models_mgr)
        logging.info('✅ ChunkingManager初始化成功')
        logging.info(f'✅ Tokenizer解耦架构已启用')
        logging.info(f'✅ 配置的embedding维度: {chunking_mgr.embedding_dimensions}')
        logging.info(f'✅ Chunker最大tokens: {chunking_mgr.chunker.tokenizer.get_max_tokens()}')
    except Exception as e:
        logger.info(f"❌ Docling转换器创建失败: {e}")
        import traceback
        traceback.print_exc()
    logger.info("✅ 组件初始化完成")

    # 2. 找一个测试文档
    file_path = "/Users/dio/Downloads/AI代理的上下文工程：构建Manus的经验教训.pdf"
    
    # # 3. 从process_document()中拆分出的方法进行独立测试
    # logger.info("🧪 测试基本方法...")
    # file_hash = chunking_mgr._calculate_file_hash(file_path)
    # logger.info(f"✅ 文件哈希计算完成: {file_hash}")
    # existing_doc = chunking_mgr._get_existing_document(file_path, file_hash)
    # if existing_doc:
    #     logger.info(f"✅ 已存在文档记录: {existing_doc.id}, 状态: {existing_doc.status}")
    # else:
    #     logger.info("✅ 未找到现有文档记录")
    # docling_result = chunking_mgr._parse_with_docling(file_path)
    # logger.info(f"✅ Docling解析完成: {len(docling_result.document.pages)}页")
    # docling_json_path = chunking_mgr._save_docling_result(file_path, docling_result)
    # logger.info(f"✅ Docling结果保存完成: {docling_json_path}")
    # document = chunking_mgr._create_or_update_document(file_path, file_hash, docling_json_path)
    # logger.info(f"✅ 文档记录创建/更新完成, ID: {document.id}")
    # parent_chunks, child_chunks = chunking_mgr._generate_chunks(document.id, docling_result.document)
    # logger.info(f"✅ 生成内容块完成: {len(parent_chunks)}父块, {len(child_chunks)}子块")
    # chunking_mgr._store_chunks(parent_chunks, child_chunks)        
    # chunking_mgr._vectorize_and_store(parent_chunks, child_chunks)
    # document.status = "done"
    # document.processed_at = datetime.now()
    # chunking_mgr.session.add(document)
    # chunking_mgr.session.commit()

    # 4. 最后集成测试文档处理
    try:
        # 处理文档
        result = chunking_mgr.process_document(str(file_path))
        logger.info(f"✅ 文档处理完成: {result}")
    
    except Exception as e:
        logger.info(f"❌ 文档处理失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 设置测试日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    test_chunking_mgr()
