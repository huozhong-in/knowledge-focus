"""
多模态检索管理器 (MultivectorMgr)

负责使用docling解析文档，实现分层分块策略，生成父块和子块，
并调用模型进行图片描述生成和文本向量化。

核心功能：
1. 使用docling解析PDF/PPT/DOCX等文档
2. 基于docling的body/groups结构实现分层分块
3. 调用vision模型生成图片/表格描述
4. 调用embedding模型进行向量化
5. 存储到SQLite(元数据)和LanceDB(向量)
"""

from config import singleton, generate_vector_id, EMBEDDING_MODEL
import os
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import (
    # Dict, 
    # Any, 
    List, 
    Optional, 
    Tuple,
)
from sqlmodel import Session, select
from sqlalchemy import Engine
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PictureDescriptionApiOptions,
    PdfPipelineOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import (
    DoclingDocument,
    ImageRefMode,
    # PictureItem,
    # TableItem,
    # TextItem,
)
from docling.datamodel.document import ConversionResult
from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from transformers import AutoTokenizer
from db_mgr import Document, ParentChunk, ChildChunk, ModelCapability
from lancedb_mgr import LanceDBMgr
from models_mgr import ModelsMgr
from model_config_mgr import ModelConfigMgr
from bridge_events import BridgeEventSender
# 强制 PyTorch 使用 CPU
import torch
# # 🔒 全局 Metal GPU 互斥锁
# # 用于确保 Docling (子进程) 和 MLX-VLM (主进程) 不会同时使用 Metal GPU
# # 关键: 使用 multiprocessing.Lock() 而非 threading.Lock，因为 Docling 运行在子进程中
# from multiprocessing import Lock as ProcessLock
# import asyncio

logger = logging.getLogger()
# # 创建进程级锁 (必须在模块级别创建，以便子进程继承)
# _metal_gpu_lock = ProcessLock()

# def acquire_metal_lock(operation: str):
#     """获取 Metal GPU 锁 (同步版本)"""
#     logger.info(f"[METAL_LOCK] Acquiring lock for: {operation}")
#     _metal_gpu_lock.acquire()
#     logger.info(f"[METAL_LOCK] Lock acquired for: {operation}")

# def release_metal_lock(operation: str):
#     """释放 Metal GPU 锁 (同步版本)"""
#     _metal_gpu_lock.release()
#     logger.info(f"[METAL_LOCK] Lock released for: {operation}")

# # 异步版本 (用于 async/await 上下文)
# async def acquire_metal_lock_async(operation: str):
#     """获取 Metal GPU 锁 (异步版本)"""
#     logger.info(f"[METAL_LOCK] Acquiring lock for: {operation}")
#     # 在异步上下文中等待锁
#     loop = asyncio.get_event_loop()
#     await loop.run_in_executor(None, _metal_gpu_lock.acquire)
#     logger.info(f"[METAL_LOCK] Lock acquired for: {operation}")

# async def release_metal_lock_async(operation: str):
#     """释放 Metal GPU 锁 (异步版本)"""
#     _metal_gpu_lock.release()
#     logger.info(f"[METAL_LOCK] Lock released for: {operation}")


os.environ["TOKENIZERS_PARALLELISM"] = "false"

# ============================================================================
# 模块级函数：用于子进程执行（避免嵌套函数序列化问题）
# ============================================================================

# def _docling_worker_func(file_path: str, ocr_options: dict, use_proxy: bool, proxy_value: str, result_queue):
#     """
#     在子进程中运行Docling解析（模块级函数，可被multiprocessing序列化）
    
#     这个函数会在独立的进程中执行，拥有完全独立的Metal上下文，
#     不会与主进程中的MLX-VLM产生Metal GPU命令编码器冲突。
#     """
#     try:
#         # 子进程中重新导入和初始化
#         from docling.document_converter import DocumentConverter, PdfFormatOption
#         from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
#         from docling.datamodel.base_models import InputFormat
#         from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions
#         import os
#         import pickle
        
#         # 配置OCR
#         pipeline_options = PdfPipelineOptions()
#         if ocr_options.get("do_ocr", False):
#             pipeline_options.do_ocr = True
#             easyocr_options = EasyOcrOptions(
#                 lang=ocr_options.get("ocr_lang", ["ch_sim", "en"])
#             )
#             pipeline_options.ocr_options = easyocr_options
        
#         # 创建转换器
#         converter = DocumentConverter(
#             allowed_formats=[InputFormat.PDF],
#             format_options={
#                 InputFormat.PDF: PdfFormatOption(
#                     pipeline_cls=StandardPdfPipeline,
#                     pipeline_options=pipeline_options,
#                 )
#             },
#         )
        
#         # 设置代理
#         if use_proxy and proxy_value:
#             os.environ['ALL_PROXY'] = proxy_value
        
#         # 执行解析
#         result = converter.convert(source=file_path)
        
#         # 🔧 只序列化 document 的字典表示，避免 pickle 整个 result 对象
#         # result 对象包含无法 pickle 的 PDF parser 引用
#         doc_dict = result.document.export_to_dict()
#         result_queue.put(("success", pickle.dumps(doc_dict)))
        
#     except Exception as e:
#         result_queue.put(("error", str(e)))
#     finally:
#         os.environ.pop('ALL_PROXY', None)

# 🔧 完全禁用 Metal GPU 相关功能
# 当 Docling 和 MLX-VLM 在同一进程中运行时，即使 Docling 使用 CPU，
# Metal 框架的某些内部状态仍可能导致冲突
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
# os.environ["PYTORCH_MPS_HIGH_WATERMARK_RATIO"] = "0.0"  # 完全禁用 MPS 内存分配

torch.set_num_threads(1)
if torch.backends.mps.is_available():
    torch.backends.mps.is_built = lambda: False

# # 禁用 MLX 的某些 Metal 优化，避免与 PyTorch 冲突
# try:
#     import mlx.core as mx
#     # 设置 MLX 使用更保守的内存管理策略
#     mx.set_memory_limit(4 * 1024 * 1024 * 1024)  # 4GB 限制
# except Exception:
#     pass  # MLX 可能还未导入
# 不同业务场景所需模型能力的组合
SCENE_MULTIVECTOR: List[ModelCapability] = [ModelCapability.TEXT, ModelCapability.VISION]

# Docling支持的文件格式, https://docling-project.github.io/docling/examples/run_with_formats/
SUPPORTED_FORMATS = ['pdf', 'docx', 'pptx', 'txt', 'md', 'markdown']

@singleton
class MultiVectorMgr:
    """多模态分块管理器"""

    def __init__(self, engine: Engine, lancedb_mgr: LanceDBMgr, models_mgr: ModelsMgr):
        """
        初始化分块管理器
        
        Args:
            engine: SQLAlchemy数据库引擎
            lancedb_mgr: LanceDB向量数据库管理器
            models_mgr: 模型管理器（用于调用vision和embedding模型）
        """
        self.engine = engine
        self.lancedb_mgr = lancedb_mgr
        self.models_mgr = models_mgr
        self.model_config_mgr = ModelConfigMgr(engine)
        # 在用户指定vision模型之前，需要初始化才能使用
        self.converter = None
        self.use_proxy = False
        # 获取数据库目录作为基础路径
        self._init_base_paths()
        # 初始化桥接事件发送器
        self.bridge_events = BridgeEventSender(source="multivector_mgr")
        
        # 初始化chunker
        self._init_chunker()
        
        logger.info("MultivectorMgr initialized successfully")
    
    def check_multivector_model_availability(self) -> bool:
        """
        检查是否有可用的模型。
        如果没有可用模型，返回False并记录警告。
        """
        for capa in SCENE_MULTIVECTOR:
            if self.model_config_mgr.get_spec_model_config(capa) is None:
                logger.warning(f"Model for multivector is not available: {capa}")
                return False
        return True
    
    def _init_base_paths(self):
        """初始化基础路径，使用数据库目录的父目录"""
        try:
            # 尝试从LanceDB获取路径
            if hasattr(self.lancedb_mgr, 'db') and hasattr(self.lancedb_mgr.db, 'uri'):
                lancedb_path = Path(self.lancedb_mgr.db.uri)
                self.data_base_dir = lancedb_path.parent
            
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
        """初始化docling文档转换器"""

        try:
            # 获取当前视觉模型配置
            model_interface = self.model_config_mgr.get_vision_model_config()
            vision_model_id = model_interface.model_identifier
            vision_base_url = model_interface.base_url
            vision_api_key = model_interface.api_key
            self.use_proxy = model_interface.use_proxy

            # 配置PDF处理选项
            pipeline_options = PdfPipelineOptions()
            pipeline_options.generate_picture_images = True
            # pipeline_options.generate_page_images = True
            pipeline_options.images_scale = 2.0  # 图片分辨率scale
            pipeline_options.do_picture_description = True
            pipeline_options.enable_remote_services = True  # 启用远程服务用于图片描述
            params=dict(
                model=vision_model_id,
                seed=42,
                temperature=0.2,
                max_completion_tokens=250,
                api_key=vision_api_key,
            )
            pipeline_options.picture_description_options = PictureDescriptionApiOptions(
                url=f"{vision_base_url}/chat/completions",
                params=params,
                prompt="""
You are an assistant tasked with summarizing images for retrieval. 
These summaries will be embedded and used to retrieve the raw image. 
Give a concise summary of the image that is well optimized for retrieval.
""".strip(),
                timeout=180,
            )
            pipeline_options.do_ocr = False  # 关闭OCR，依赖docling内置的简单OCR
            
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
            # chunker的tokenizer与embedding模型可以不是同一个
            # HybridChunker的tokenizer主要用于chunk大小控制，不需要与embedding模型完全一致
            # 使用通用tokenizer进行近似估算更稳定可靠，这里我们使用内置的中英文友好tokenizer作为chunk大小估算器
            model_path = self.model_config_mgr.get_embeddings_model_path()
            if model_path == "":
                # 使用lancedb_mgr的base_dir作为缓存目录，它与SQLite数据库在同一父目录
                cache_directory = self.lancedb_mgr.base_dir
                model_path = self.models_mgr.download_huggingface_model(EMBEDDING_MODEL, cache_directory)
                self.model_config_mgr.set_embeddings_model_path(model_path)  
            tokenizer = HuggingFaceTokenizer(
                tokenizer=AutoTokenizer.from_pretrained(model_path),
                max_tokens=512,  # 保守的chunk大小，确保embedding API调用稳定
            )
            
            # 创建HybridChunker实例
            self.chunker = HybridChunker(
                tokenizer=tokenizer,
                merge_peers=True,  # 合并相邻的同类chunk
            )
            
            logger.info(f"Chunker initialized with max_tokens={tokenizer.get_max_tokens()}")
            
        except Exception as e:
            logger.error(f"Failed to initialize chunker: {e}")
            raise
    
    def process_document(self, file_path: str, task_id: str = None) -> bool:
        """
        处理单个文档的完整流程
        
        Args:
            file_path: 文档文件的绝对路径
            task_id: 任务ID，用于事件追踪
            
        Returns:
            bool: 处理是否成功
        """
        
        # 判断文件格式是否支持
        file_ext = Path(file_path).suffix.split('.')[-1].lower()
        if file_ext not in SUPPORTED_FORMATS:
            logger.warning(f"[MULTIVECTOR] Unsupported file type: {file_ext}")
            if task_id:
                self.bridge_events.multivector_failed(
                    file_path, task_id, 
                    f"不支持的文件类型: {file_ext}，支持的类型: {SUPPORTED_FORMATS}", 
                    "unsupported_format"
                )
            return False

        try:
            logger.info(f"[MULTIVECTOR] Starting document processing: {file_path}")
            
            # 发送进度事件            
            self.bridge_events.multivector_progress(file_path, task_id or "", 0, 100, 
                                                   "parsing", "开始解析文档...")
            
            # 1. 验证文件
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            # 2. 计算文件hash
            file_hash = self._calculate_file_hash(file_path)
            
            # 3. 检查是否已处理过且文件未变更
            existing_doc = self._get_existing_document(file_path, file_hash)
            if existing_doc:
                logger.info(f"[MULTIVECTOR] Document already processed and unchanged: {file_path}")
                if task_id:
                    # 获取已有chunk统计
                    with Session(self.engine) as session:
                        parent_stmt = select(ParentChunk).where(ParentChunk.document_id == existing_doc.id)
                        parent_count = len(session.exec(parent_stmt).all())
                        
                        child_stmt = select(ChildChunk).join(ParentChunk).where(ParentChunk.document_id == existing_doc.id)
                        child_count = len(session.exec(child_stmt).all())
                        
                        self.bridge_events.multivector_completed(file_path, task_id, parent_count, child_count)
                return True
            
            # 4. 使用docling解析文档
            self.bridge_events.multivector_progress(file_path, task_id or "", 20, 100, 
                                                   "parsing", "正在解析文档结构...")
            docling_result = self._parse_with_docling(file_path)
            
            # 5. 保存docling解析结果
            docling_json_path = self._save_docling_result(file_path, docling_result)
            
            # 6. 创建/更新Document记录
            self.bridge_events.multivector_progress(file_path, task_id or "", 40, 100, 
                                                   "chunking", "创建文档记录...")
            document = self._create_or_update_document(file_path, file_hash, docling_json_path)
            
            # 7. 生成父块和子块
            self.bridge_events.multivector_progress(file_path, task_id or "", 60, 100, 
                                                   "chunking", "生成内容块...")
            parent_chunks, child_chunks = self._generate_chunks(document.id, docling_result.document)
            
            # 8. 存储到数据库
            self.bridge_events.multivector_progress(file_path, task_id or "", 80, 100, 
                                                   "chunking", "存储到数据库...")
            self._store_chunks(parent_chunks, child_chunks)
            
            # 8.5. 为图片chunks创建图文关系子块（关键设计）
            self.bridge_events.multivector_progress(file_path, task_id or "", 85, 100, 
                                                   "chunking", "创建图文关系子块...")
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
            self.bridge_events.multivector_progress(file_path, task_id or "", 90, 100, 
                                                   "vectorizing", "向量化和存储...")
            self._vectorize_and_store(parent_chunks, child_chunks)
            
            # 10. 更新文档状态
            document.status = "done"
            document.processed_at = datetime.now()
            with Session(self.engine) as session:
                session.add(document)
                session.commit()
            
            # 发送完成事件
            if task_id:
                self.bridge_events.multivector_completed(file_path, task_id, 
                                                        len(parent_chunks), len(child_chunks))
            else:
                self.bridge_events.multivector_progress(file_path, "", 100, 100, 
                                                       "completed", "文档处理完成")
            
            logger.info(f"[MULTIVECTOR] Document processing completed: {file_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"[MULTIVECTOR] Document processing failed for {file_path}: {e}", exc_info=True)
            
            # 发送失败事件
            error_msg = f"文档处理失败: {str(e)}"
            help_link = "https://kf.huozhong.in/"
            if task_id:
                self.bridge_events.multivector_failed(file_path, task_id, error_msg, help_link, type(e).__name__)
            else:
                self.bridge_events.error_occurred("chunking_error", error_msg, {
                    "file_path": file_path,
                    "error_type": type(e).__name__
                })
            
            # 更新文档状态为错误
            try:
                document = self._get_or_create_document_record(file_path, "", "")
                document.status = "error"
                with Session(self.engine) as session:
                    session.add(document)
                    session.commit()
            except Exception as e:
                logger.error(f"Failed to update document status: {e}")
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
            stmt = select(Document).where(
                Document.file_path == file_path,
                Document.file_hash == file_hash,
                Document.status == "done"
            )
            with Session(self.engine) as session:
                return session.exec(stmt).first()
        except Exception as e:
            logger.error(f"Failed to check existing document: {e}")
            return None
    
    def _parse_with_docling(self, file_path: str) -> ConversionResult:
        self._init_docling_converter()
        return self.converter.convert(source=file_path)
    # def _parse_with_docling(self, file_path: str) -> ConversionResult:
    #     """使用docling解析文档（在子进程中运行以避免Metal GPU冲突）"""
        
    #     # 🚀 使用子进程运行Docling，完全隔离Metal上下文
    #     # 🔒 使用全局锁确保与 MLX-VLM 互斥
    #     from multiprocessing import Process, Queue
    #     import pickle
        
    #     # 🔒 获取 Metal GPU 锁
    #     acquire_metal_lock("Docling PDF parsing")
        
    #     try:
    #         logger.info(f"[MULTIVECTOR] Parsing document with docling in subprocess: {file_path}")
            
    #         # 准备OCR配置
    #         ocr_options = {
    #             # "do_ocr": self.do_ocr,
    #             # "ocr_lang": self.ocr_lang
    #         }
            
    #         # 获取代理配置
    #         proxy_value = ""
    #         if self.use_proxy:
    #             proxy = self.model_config_mgr.get_proxy_value()
    #             if proxy and proxy.value:
    #                 proxy_value = proxy.value
            
    #         # 创建结果队列
    #         result_queue = Queue()
            
    #         # 创建并启动子进程（使用模块级函数）
    #         process = Process(
    #             target=_docling_worker_func,
    #             args=(file_path, ocr_options, self.use_proxy, proxy_value, result_queue)
    #         )
    #         process.daemon = False  # 确保子进程独立运行
    #         process.start()
    #         logger.info(f"[MULTIVECTOR] Docling worker process started (PID: {process.pid})")
            
    #         # 等待结果（设置60秒超时）
    #         try:
    #             process.join(timeout=60)
    #         except Exception as e:
    #             logger.error(f"Error waiting for Docling subprocess: {e}")
    #             if process.is_alive():
    #                 process.terminate()
    #                 process.join(timeout=5)
    #                 if process.is_alive():
    #                     process.kill()  # 强制杀死
    #             raise RuntimeError(f"Docling subprocess join failed: {e}")
            
    #         if process.is_alive():
    #             # 超时，强制终止
    #             logger.warning("Docling parsing timed out, terminating subprocess")
    #             process.terminate()
    #             process.join(timeout=5)
    #             if process.is_alive():
    #                 process.kill()
    #             raise TimeoutError("Docling parsing timed out after 60 seconds")
            
    #         # 检查进程退出码
    #         logger.info(f"[MULTIVECTOR] Docling worker exited with code: {process.exitcode}")
    #         if process.exitcode != 0:
    #             # 子进程异常退出，但不要让它影响主进程
    #             error_msg = f"Docling worker process failed with exit code {process.exitcode}"
    #             if process.exitcode == 134:
    #                 error_msg += " (SIGABRT - possible Metal GPU conflict or assertion failure)"
    #             elif process.exitcode < 0:
    #                 error_msg += f" (killed by signal {-process.exitcode})"
    #             logger.error(error_msg)
    #             raise RuntimeError(error_msg)
            
    #         # 获取结果
    #         if result_queue.empty():
    #             logger.error("Docling worker did not return any result in queue")
    #             raise RuntimeError("Docling worker did not return any result")
            
    #         try:
    #             status, data = result_queue.get(timeout=5)
    #             logger.info(f"[MULTIVECTOR] Got result from worker, status: {status}")
    #         except Exception as e:
    #             logger.error(f"Failed to get result from queue: {e}")
    #             raise RuntimeError(f"Failed to get result from Docling worker: {e}")
            
    #         if status == "error":
    #             logger.error(f"Docling worker returned error: {data}")
    #             raise RuntimeError(f"Docling parsing failed: {data}")
            
    #         # 反序列化结果（现在是 document dict，而不是完整的 ConversionResult）
    #         logger.info("[MULTIVECTOR] Deserializing Docling result from subprocess")
    #         import pickle
    #         from docling_core.types.doc import DoclingDocument
            
    #         try:
    #             doc_dict = pickle.loads(data)
    #             logger.info(f"[MULTIVECTOR] Successfully unpickled document dict, keys: {list(doc_dict.keys()) if isinstance(doc_dict, dict) else 'not a dict'}")
    #         except Exception as e:
    #             logger.error(f"Failed to unpickle document data: {e}")
    #             raise RuntimeError(f"Failed to deserialize Docling result: {e}")
            
    #         # 从字典重建 DoclingDocument
    #         try:
    #             document = DoclingDocument.model_validate(doc_dict)
    #             logger.info(f"[MULTIVECTOR] Successfully validated DoclingDocument, pages: {len(document.pages)}")
    #         except Exception as e:
    #             logger.error(f"Failed to validate DoclingDocument from dict: {e}")
    #             raise RuntimeError(f"Failed to rebuild DoclingDocument: {e}")
            
    #         if not document:
    #             raise ValueError("Docling parsing returned empty document")
            
    #         # 🔧 创建一个简化的 ConversionResult 对象
    #         # 只包含必要的 document 字段
    #         class SimpleConversionResult:
    #             def __init__(self, document):
    #                 self.document = document
            
    #         result = SimpleConversionResult(document)
            
    #         logger.info(f"[MULTIVECTOR] Docling parsing completed. Document has {len(document.pages)} pages")
    #         return result
            
    #     except Exception as e:
    #         logger.error(f"Docling parsing failed for {file_path}: {e}")
    #         raise
    #     finally:
    #         # 🔓 释放 Metal GPU 锁
    #         release_metal_lock("Docling PDF parsing")
    
    def _save_docling_result(self, file_path: str, result: ConversionResult) -> str:
        """保存docling解析结果到JSON文件"""
        try:
            # 使用数据库目录的docling_cache子目录
            output_dir = self.docling_cache_dir
            
            # 生成JSON文件名（直接使用原文件名，不拼接时间戳）
            file_stem = Path(file_path).stem
            json_filename = f"{file_stem}.json"
            json_path = output_dir / json_filename
            
            # 保存JSON和图片文件
            result.document.save_as_json(
                filename=json_path,
                indent=2,
                image_mode=ImageRefMode.REFERENCED,  # 自动保存图片到artifacts_dir
                artifacts_dir=output_dir
            )
            
            logger.info(f"[MULTIVECTOR] Docling result saved to: {json_path}")
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
            with Session(self.engine) as session:
                stmt = select(Document).where(Document.file_path == file_path)
                document = session.exec(stmt).first()
                
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
                
                session.add(document)
                session.commit()
                session.refresh(document)
                
                logger.info(f"[MULTIVECTOR] Document record created/updated: ID={document.id}")
                return document
            
        except Exception as e:
            logger.error(f"Failed to create/update document record: {e}")
            raise
    
    def _get_or_create_document_record(self, file_path: str, file_hash: str, docling_json_path: str) -> Document:
        """获取或创建文档记录（辅助方法）"""
        try:
            return self._create_or_update_document(file_path, file_hash, docling_json_path)
        except Exception as e:
            logger.error(f"Failed to get or create document record: {e}")
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
        logger.info(f"[MULTIVECTOR] Generating chunks using HybridChunker for document ID: {document_id}")
        
        all_parent_chunks = []
        all_child_chunks = []
        
        try:
            # 使用HybridChunker生成chunks
            chunk_iter = self.chunker.chunk(dl_doc=docling_doc)
            chunks = list(chunk_iter)
            
            logger.info(f"[MULTIVECTOR] HybridChunker generated {len(chunks)} chunks")
            
            # 为每个chunk创建父块和对应的子块
            for i, chunk in enumerate(chunks):
                try:
                    # 获取原始chunk文本 - 用于父块（保持数据纯净性）
                    raw_content = chunk.text
                    
                    # 获取上下文丰富的内容 - 仅用于子块摘要生成
                    contextualized_content = self.chunker.contextualize(chunk=chunk)
                    
                    # 确定chunk类型
                    chunk_type = self._determine_chunk_type(chunk)
                    
                    logger.debug(f"[MULTIVECTOR] Chunk {i}: type={chunk_type}, raw_length={len(raw_content)}, contextualized_length={len(contextualized_content)}")
                    
                    # 如果是图片类型且包含混合内容，需要进行分割处理
                    if chunk_type == "image" and self._contains_mixed_content(raw_content):
                        logger.debug(f"[MULTIVECTOR] Chunk {i} contains mixed content, splitting...")
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
            
            logger.info(f"[MULTIVECTOR] Successfully generated {len(all_parent_chunks)} parent chunks and {len(all_child_chunks)} child chunks")
            
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
                    logger.debug("[CHUNK_TYPE] Determined type: table")
                    return "table"
                elif any('PICTURE' in item_type.upper() or 'IMAGE' in item_type.upper() for item_type in item_types):
                    logger.debug("[CHUNK_TYPE] Determined type: image")
                    return "image"
                else:
                    logger.debug("[CHUNK_TYPE] Determined type: text (default)")
                    return "text"
            else:
                logger.debug("[CHUNK_TYPE] No doc_items found, defaulting to text")
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
            
            logger.debug(f"[MULTIVECTOR] Split chunk {chunk_index} into {len(result_chunks)} sub-chunks")
            
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
        # 准备metadata，对于图片类型需要额外保存文件路径
        metadata = {
            "chunk_index": chunk_index,
            "original_text_length": len(raw_content),
            "contextualized_length": len(contextualized_content),
            "doc_items_refs": [item.self_ref for item in chunk.meta.doc_items] if hasattr(chunk.meta, 'doc_items') else [],
            "chunk_id": chunk.meta.chunk_id if hasattr(chunk.meta, 'chunk_id') else None,
            "source": "hybrid_chunker_split" if isinstance(chunk_index, str) else "hybrid_chunker"
        }
        
        # 对于图片类型，将文件路径保存到metadata中
        if chunk_type == "image":
            # 尝试从chunk的doc_items中提取图片文件路径
            image_file_path = self._extract_image_file_path(chunk)
            if image_file_path:
                metadata["image_file_path"] = image_file_path
                logger.debug(f"[MULTIVECTOR] Image chunk {chunk_index}: saved file path to metadata: {image_file_path}")
            else:
                logger.warning(f"[MULTIVECTOR] Image chunk {chunk_index}: could not extract file path")
        
        # 创建父块 - content统一存储"内容"（文本内容或图片描述）
        parent_chunk = ParentChunk(
            document_id=document_id,
            chunk_type=chunk_type,
            content=raw_content,  # 统一存储内容：文本内容或图片描述
            metadata_json=json.dumps(metadata)
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
    
    def _extract_image_file_path(self, chunk) -> str | None:
        """
        从chunk的doc_items中提取图片文件路径
        使用doc_items_refs中的图片索引来匹配docling生成的图片文件
        
        Args:
            chunk: HybridChunker生成的chunk对象
            
        Returns:
            str | None: 图片文件的绝对路径，如果未找到则返回None
        """
        try:
            if not hasattr(chunk.meta, 'doc_items') or not chunk.meta.doc_items:
                return None
            
            # 从doc_items中提取pictures引用索引
            picture_refs = []
            for item in chunk.meta.doc_items:
                if hasattr(item, 'self_ref') and item.self_ref:
                    ref_str = str(item.self_ref)
                    if "/pictures/" in ref_str:
                        # 例如: "#/pictures/1" -> 提取 "1"
                        try:
                            picture_index = ref_str.split("/pictures/")[-1]
                            picture_refs.append(picture_index)
                        except Exception as e:
                            logger.warning(f"Error extracting picture index from ref: {e}")
                            continue
            
            # 根据图片索引查找对应的文件
            for picture_index in picture_refs:
                try:
                    # docling生成的文件名格式: image_{6位数字索引}_{hash}.png
                    # 例如: image_000001_hash.png 对应 pictures/1
                    padded_index = str(picture_index).zfill(6)
                    pattern = f"image_{padded_index}_*.png"
                    
                    # 在docling_cache_dir中查找匹配的文件
                    matching_files = list(self.docling_cache_dir.glob(pattern))
                    
                    if matching_files:
                        # 返回第一个匹配的文件
                        image_file = matching_files[0]
                        logger.debug(f"Found image file for index {picture_index}: {image_file.name}")
                        return str(image_file)
                    else:
                        logger.debug(f"No image file found for pattern: {pattern}")
                        
                except Exception as e:
                    logger.warning(f"Error processing picture index {picture_index}: {e}")
                    continue
            
            # 备用方案：尝试原来的方法
            for item in chunk.meta.doc_items:
                if hasattr(item, 'label') and 'PICTURE' in str(item.label).upper():
                    # 检查是否有file attribute
                    if hasattr(item, 'file') and item.file:
                        # 构建完整的文件路径
                        if hasattr(item.file, 'filename') and item.file.filename:
                            # 图片文件保存在docling_cache_dir中
                            image_filename = item.file.filename
                            full_path = self.docling_cache_dir / image_filename
                            if full_path.exists():
                                return str(full_path)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract image file path from chunk: {e}")
            return None
    
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
            
            # 🔧 在调用 LLM 前清理 PyTorch Metal 状态
            # 确保 Docling 完全释放了 Metal 资源
            try:
                import torch
                import gc
                if torch.backends.mps.is_available():
                    # 清理 PyTorch MPS 缓存
                    torch.mps.empty_cache()
                # 强制垃圾回收
                gc.collect()
            except Exception:
                pass  # 忽略清理错误
            
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
            summary = self.models_mgr.get_chat_completion(messages)
            
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
                    # 获取图像描述内容 - 现在直接从content字段获取
                    image_description = image_chunk.content
                    
                    if not image_description or len(image_description.strip()) < 10:
                        logger.warning(f"Image chunk {chunk_idx}: description too short or empty")
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
            summary = self.models_mgr.get_chat_completion(messages)
            
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
        if len(parent_chunks) != len(child_chunks):
            raise ValueError(f"Parent chunks count ({len(parent_chunks)}) does not match child chunks count ({len(child_chunks)})")
        
        # 1. 先存储父块
        if parent_chunks:
            with Session(self.engine) as session:
                session.add_all(parent_chunks)
                session.commit()
                # 刷新以获取生成的ID
                for chunk in parent_chunks:
                    session.refresh(chunk)
            
            logger.info(f"[MULTIVECTOR] Stored {len(parent_chunks)} parent chunks")
        
        # 2. 设置子块的parent_chunk_id并存储
        if child_chunks:
            for i, child_chunk in enumerate(child_chunks):
                child_chunk.parent_chunk_id = parent_chunks[i].id
            with Session(self.engine) as session:
                session.add_all(child_chunks)
                session.commit()
                
                # 刷新以获取生成的ID
                for chunk in child_chunks:
                    session.refresh(chunk)
            
            logger.info(f"[MULTIVECTOR] Stored {len(child_chunks)} child chunks")
    
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
                logger.info(f"[MULTIVECTOR] Vectorized and stored {len(vector_records)} child chunk vectors")
            
            logger.info(f"[MULTIVECTOR] Vector storage completed - {len(parent_chunks)} parent chunks stored in SQLite only, {len(child_chunks)} child chunks vectorized in LanceDB")
            
        except Exception as e:
            logger.error(f"Failed to vectorize and store: {e}")
            raise


# 为了测试和调试使用
def test_multivector_file():
    """测试分块管理器的基本功能"""
    # 1. 初始化各个组件
    logger.info("🔧 初始化组件...")
    # SQLite数据库
    from config import TEST_DB_PATH
    from sqlmodel import create_engine
    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
    # LanceDB
    db_directory = Path(TEST_DB_PATH).parent
    lancedb_mgr = LanceDBMgr(base_dir=db_directory)
    # 模型管理器
    models_mgr = ModelsMgr(engine, base_dir=db_directory)
    # 事件发送器
    _bridge_events = BridgeEventSender()
    # 分块管理器
    try:
        multivector_mgr = MultiVectorMgr(engine, lancedb_mgr, models_mgr)
        logging.info('✅ MultivectorMgr初始化成功')
        logging.info('✅ Tokenizer解耦架构已启用')
        logging.info(f'✅ Chunker最大tokens: {multivector_mgr.chunker.tokenizer.get_max_tokens()}')
    except Exception as e:
        logger.info(f"❌ Docling转换器创建失败: {e}")
        import traceback
        traceback.print_exc()
    logger.info("✅ 组件初始化完成")

    # 2. 找一个测试文档
    # file_path = "/Users/dio/Downloads/Context Engineering for AI Agents_ Lessons from Building Manus.pdf"
    file_path = "/Users/dio/Downloads/AI代理的上下文工程：构建Manus的经验教训.pdf"
    file_path = "/Users/dio/Downloads/纳瓦尔宝典：财富与幸福指南.pdf"
    file_path = "/Users/dio/Downloads/死神永生.pdf"
    file_path = "/Users/dio/Downloads/9-《高效能人士的七个习惯》(中文版)..pdf"
    file_path = "/Users/dio/Downloads/寻找Alpha：量化交易策略.pdf"
    
    # # 3. 从process_document()中拆分出的方法进行独立测试
    # logger.info("🧪 测试基本方法...")
    # file_hash = multivector_mgr._calculate_file_hash(file_path)
    # logger.info(f"✅ 文件哈希计算完成: {file_hash}")
    # existing_doc = multivector_mgr._get_existing_document(file_path, file_hash)
    # if existing_doc:
    #     logger.info(f"✅ 已存在文档记录: {existing_doc.id}, 状态: {existing_doc.status}")
    # else:
    #     logger.info("✅ 未找到现有文档记录")
    # docling_result = multivector_mgr._parse_with_docling(file_path)
    # logger.info(f"✅ Docling解析完成: {len(docling_result.document.pages)}页")
    # docling_json_path = multivector_mgr._save_docling_result(file_path, docling_result)
    # logger.info(f"✅ Docling结果保存完成: {docling_json_path}")
    # document = multivector_mgr._create_or_update_document(file_path, file_hash, docling_json_path)
    # logger.info(f"✅ 文档记录创建/更新完成, ID: {document.id}")
    # parent_chunks, child_chunks = multivector_mgr._generate_chunks(document.id, docling_result.document)
    # logger.info(f"✅ 生成内容块完成: {len(parent_chunks)}父块, {len(child_chunks)}子块")
    # multivector_mgr._store_chunks(parent_chunks, child_chunks)        
    # multivector_mgr._vectorize_and_store(parent_chunks, child_chunks)
    # document.status = "done"
    # document.processed_at = datetime.now()
    # multivector_mgr.session.add(document)
    # multivector_mgr.session.commit()

    # 4. 最后集成测试文档处理
    try:
        # 处理文档
        result = multivector_mgr.process_document(str(file_path))
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
    # # 10秒倒计时
    # import time
    # for i in range(10, 0, -1):
    #     print(f"倒计时: {i}秒")
    #     time.sleep(1)
    
    test_multivector_file()
