from typing import List, Dict, Any, Optional, Tuple, Union
from sqlmodel import Session, select, delete, update, func, desc, asc
from db_mgr import (
    FileScreeningResult, 
    FileScreenResult,
    FileRefineResult, 
    FileRefineStatus,
    FileAnalysisType,
    Project
)
from screening_mgr import ScreeningManager
import logging
from datetime import datetime, timedelta
import re
import os
import json
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class RefineManager:
    """文件精炼管理类，提供文件内容深度分析、关联发现功能"""

    def __init__(self, session: Session):
        self.session = session
        self.screening_mgr = ScreeningManager(session)

    def process_pending_file(self, screening_id: int) -> Optional[FileRefineResult]:
        """处理单个待处理的粗筛结果文件
        
        Args:
            screening_id: 粗筛结果ID
            
        Returns:
            处理成功返回精炼结果对象，失败返回None
        """
        try:
            # 获取粗筛结果
            screening_result = self.screening_mgr.get_by_id(screening_id)
            if not screening_result:
                logger.warning(f"处理失败: 找不到ID为 {screening_id} 的粗筛结果")
                return None
            
            # 检查文件是否存在
            if not os.path.exists(screening_result.file_path):
                logger.warning(f"处理失败: 文件路径不存在 {screening_result.file_path}")
                self.screening_mgr.update_status(screening_id, FileScreenResult.FAILED, "文件路径不存在")
                return None
            
            # 创建精炼结果记录
            refine_result = self._create_refine_record(screening_result)
            if not refine_result:
                return None
            
            # 设置状态为处理中
            refine_result.status = FileRefineStatus.PROCESSING.value
            self.session.add(refine_result)
            self.session.commit()
            
            # 进行基础分析
            start_time = time.time()
            if screening_result.file_size < (50 * 1024 * 1024):  # 小于50MB的文件才进行内容分析
                refine_result = self._analyze_file(refine_result, screening_result)
            else:
                # 大文件只做基础分析
                refine_result = self._basic_analysis(refine_result, screening_result)
            
            # 识别关联文件
            refine_result = self._identify_related_files(refine_result, screening_result)
            
            # 识别项目
            refine_result = self._identify_project(refine_result, screening_result)
            
            # 计算处理耗时
            refine_result.processing_time = time.time() - start_time
            
            # 更新状态为已完成
            refine_result.status = FileRefineStatus.COMPLETE.value
            self.session.add(refine_result)
            self.session.commit()
            
            # 更新粗筛结果状态
            self.screening_mgr.update_status(screening_id, FileScreenResult.PROCESSED)
            
            logger.info(f"文件精炼处理完成: {screening_result.file_path}")
            return refine_result
            
        except Exception as e:
            logger.error(f"处理文件精炼失败: {str(e)}")
            # 尝试更新粗筛结果状态
            try:
                self.screening_mgr.update_status(screening_id, FileScreenResult.FAILED, str(e))
            except Exception:
                pass
            return None
    
    def _create_refine_record(self, screening_result: FileScreeningResult) -> Optional[FileRefineResult]:
        """创建精炼记录
        
        Args:
            screening_result: 粗筛结果对象
            
        Returns:
            创建的精炼记录，失败返回None
        """
        try:
            # 检查是否已存在
            existing = self.get_by_screening_id(screening_result.id)
            if existing:
                # 已存在则更新状态
                if existing.status in [FileRefineStatus.COMPLETE.value, FileRefineStatus.PROCESSING.value]:
                    logger.info(f"精炼记录已存在且状态为 {existing.status}，跳过创建")
                    return existing
                
                # 重置状态
                existing.status = FileRefineStatus.PENDING.value
                existing.updated_at = datetime.now()
                self.session.add(existing)
                self.session.commit()
                return existing
            
            # 创建新记录
            refine_result = FileRefineResult(
                screening_id=screening_result.id,
                task_id=screening_result.task_id,
                file_path=screening_result.file_path,
                status=FileRefineStatus.PENDING.value,
                analysis_type=FileAnalysisType.BASIC.value
            )
            
            self.session.add(refine_result)
            self.session.commit()
            self.session.refresh(refine_result)
            
            logger.info(f"创建精炼记录: 文件 {screening_result.file_path}")
            return refine_result
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"创建精炼记录失败: {str(e)}")
            return None
    
    def _basic_analysis(self, refine_result: FileRefineResult, screening_result: FileScreeningResult) -> FileRefineResult:
        """对文件进行基本分析
        
        Args:
            refine_result: 精炼结果对象
            screening_result: 粗筛结果对象
            
        Returns:
            更新后的精炼结果对象
        """
        try:
            # 解析文件路径
            path = Path(screening_result.file_path)
            parent = path.parent.name
            
            # 基本分析
            refine_result.analysis_type = FileAnalysisType.BASIC.value
            
            # 提取基本元数据
            current_extra_metadata = screening_result.extra_metadata or {}
            current_extra_metadata.update({
                "parent_folder": parent,
                "is_hidden": path.name.startswith('.'),
                "last_analyzed": datetime.now().isoformat(),
            })
            
            # 更新额外元数据
            refine_result.extra_metadata = current_extra_metadata
            
            # 提取关键词
            if screening_result.file_name:
                # 简单分词，提取可能的关键词
                words = re.findall(r'[a-zA-Z\u4e00-\u9fa5]+', screening_result.file_name)
                if words:
                    refine_result.key_phrases = [w for w in words if len(w) > 1][:5]  # 只取前5个关键词
            
            return refine_result
            
        except Exception as e:
            logger.error(f"基本分析失败: {str(e)}")
            refine_result.error_message = f"基本分析失败: {str(e)}"
            return refine_result
    
    def _analyze_file(self, refine_result: FileRefineResult, screening_result: FileScreeningResult) -> FileRefineResult:
        """对文件进行深度分析
        
        Args:
            refine_result: 精炼结果对象
            screening_result: 粗筛结果对象
            
        Returns:
            更新后的精炼结果对象
        """
        try:
            # 先进行基本分析
            refine_result = self._basic_analysis(refine_result, screening_result)
            
            # 根据文件类型进行不同的分析
            extension = screening_result.extension.lower() if screening_result.extension else ""
            
            # 文本文件分析
            if extension in ["txt", "md", "markdown", "py", "js", "ts", "html", "htm", "css", "json", "xml", "csv", "log"]:
                refine_result = self._analyze_text_file(refine_result, screening_result)
            # 文档文件分析
            elif extension in ["doc", "docx", "pdf", "ppt", "pptx", "xls", "xlsx", "odt", "pages"]:
                refine_result = self._analyze_document_file(refine_result, screening_result)
            # 图片文件分析
            elif extension in ["jpg", "jpeg", "png", "gif", "bmp", "webp", "heic", "svg"]:
                refine_result = self._analyze_image_file(refine_result, screening_result)
            # 音视频文件分析
            elif extension in ["mp3", "wav", "mp4", "mov", "avi", "mkv"]:
                refine_result = self._analyze_media_file(refine_result, screening_result)
            else:
                # 其他文件只做基础分析
                pass
            
            # 标记分析类型为内容分析
            refine_result.analysis_type = FileAnalysisType.CONTENT.value
            
            return refine_result
            
        except Exception as e:
            logger.error(f"文件分析失败: {str(e)}")
            refine_result.error_message = f"文件分析失败: {str(e)}"
            return refine_result
    
    def _analyze_text_file(self, refine_result: FileRefineResult, screening_result: FileScreeningResult) -> FileRefineResult:
        """分析文本文件
        
        Args:
            refine_result: 精炼结果对象
            screening_result: 粗筛结果对象
            
        Returns:
            更新后的精炼结果对象
        """
        try:
            # 读取文件
            with open(screening_result.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(10000)  # 只读取前10000个字符用于分析
            
            # 简单摘要
            summary = content[:200] + "..." if len(content) > 200 else content
            refine_result.content_summary = summary
            
            # 简单语言检测
            if re.search(r'[\u4e00-\u9fa5]', content):
                refine_result.language = "zh-cn"
            elif re.search(r'[a-zA-Z]', content):
                refine_result.language = "en"
            else:
                refine_result.language = "unknown"
            
            # 提取部分文本
            refine_result.extracted_text = content[:1000] if len(content) > 1000 else content
            
            # 简单关键词提取 - 提取最频繁出现的词
            words = re.findall(r'[a-zA-Z\u4e00-\u9fa5]+', content)
            word_freq = {}
            for word in words:
                if len(word) > 1:  # 只考虑长度大于1的词
                    word_freq[word] = word_freq.get(word, 0) + 1
            
            # 按频率排序并提取前10个词
            key_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
            if key_words:
                refine_result.key_phrases = [word for word, _ in key_words]
            
            return refine_result
            
        except Exception as e:
            logger.error(f"文本文件分析失败: {str(e)}")
            refine_result.error_message = f"文本文件分析失败: {str(e)}"
            return refine_result
    
    def _analyze_document_file(self, refine_result: FileRefineResult, screening_result: FileScreeningResult) -> FileRefineResult:
        """分析文档文件
        
        Args:
            refine_result: 精炼结果对象
            screening_result: 粗筛结果对象
            
        Returns:
            更新后的精炼结果对象
        """
        # 文档分析需要额外的库支持
        # 此处仅做简单处理
        try:
            refine_result.content_summary = f"文档文件: {screening_result.file_name}"
            
            # 提取文档元数据
            current_extra_metadata = refine_result.extra_metadata or {}
            current_extra_metadata["document_type"] = screening_result.extension.upper() if screening_result.extension else "未知"
            refine_result.extra_metadata = current_extra_metadata
            
            return refine_result
            
        except Exception as e:
            logger.error(f"文档文件分析失败: {str(e)}")
            refine_result.error_message = f"文档文件分析失败: {str(e)}"
            return refine_result
    
    def _analyze_image_file(self, refine_result: FileRefineResult, screening_result: FileScreeningResult) -> FileRefineResult:
        """分析图片文件
        
        Args:
            refine_result: 精炼结果对象
            screening_result: 粗筛结果对象
            
        Returns:
            更新后的精炼结果对象
        """
        # 图片分析需要额外的库支持
        # 此处仅做简单处理
        try:
            refine_result.content_summary = f"图片文件: {screening_result.file_name}"
            
            # 提取图片元数据
            current_extra_metadata = refine_result.extra_metadata or {}
            current_extra_metadata["image_type"] = screening_result.extension.upper() if screening_result.extension else "未知"
            refine_result.extra_metadata = current_extra_metadata
            
            return refine_result
            
        except Exception as e:
            logger.error(f"图片文件分析失败: {str(e)}")
            refine_result.error_message = f"图片文件分析失败: {str(e)}"
            return refine_result
    
    def _analyze_media_file(self, refine_result: FileRefineResult, screening_result: FileScreeningResult) -> FileRefineResult:
        """分析音视频文件
        
        Args:
            refine_result: 精炼结果对象
            screening_result: 粗筛结果对象
            
        Returns:
            更新后的精炼结果对象
        """
        # 音视频分析需要额外的库支持
        # 此处仅做简单处理
        try:
            refine_result.content_summary = f"多媒体文件: {screening_result.file_name}"
            
            # 提取媒体元数据
            current_extra_metadata = refine_result.extra_metadata or {}
            current_extra_metadata["media_type"] = screening_result.extension.upper() if screening_result.extension else "未知"
            refine_result.extra_metadata = current_extra_metadata
            
            return refine_result
            
        except Exception as e:
            logger.error(f"媒体文件分析失败: {str(e)}")
            refine_result.error_message = f"媒体文件分析失败: {str(e)}"
            return refine_result
    
    def _identify_related_files(self, refine_result: FileRefineResult, screening_result: FileScreeningResult) -> FileRefineResult:
        """识别关联文件
        
        Args:
            refine_result: 精炼结果对象
            screening_result: 粗筛结果对象
            
        Returns:
            更新后的精炼结果对象
        """
        try:
            # 获取文件所在文件夹
            file_dir = os.path.dirname(screening_result.file_path)
            
            # 查找同文件夹下的相似文件(名称相似)
            base_name = os.path.splitext(screening_result.file_name)[0]
            
            # 查询数据库中同一文件夹下的其他文件
            similar_files_query = select(FileScreeningResult).where(
                FileScreeningResult.file_path.like(f"{file_dir}/%"),
                FileScreeningResult.id != screening_result.id
            ).limit(10)
            
            similar_files = self.session.exec(similar_files_query).all()
            
            # 计算文件名相似度并记录
            related_files = []
            for file in similar_files:
                # 简单相似度计算
                similarity = self._calculate_filename_similarity(base_name, os.path.splitext(file.file_name)[0])
                if similarity > 0.3:  # 相似度阈值
                    related_files.append({
                        "id": file.id,
                        "file_path": file.file_path,
                        "file_name": file.file_name,
                        "similarity": similarity,
                        "similarity_type": "name"
                    })
            
            # 排序并只保留前5个
            related_files = sorted(related_files, key=lambda x: x["similarity"], reverse=True)[:5]
            
            # 更新关联文件
            refine_result.similar_files = related_files
            refine_result.related_files = [f["id"] for f in related_files]
            
            return refine_result
            
        except Exception as e:
            logger.error(f"识别关联文件失败: {str(e)}")
            return refine_result
    
    def _identify_project(self, refine_result: FileRefineResult, screening_result: FileScreeningResult) -> FileRefineResult:
        """识别文件所属项目
        
        Args:
            refine_result: 精炼结果对象
            screening_result: 粗筛结果对象
            
        Returns:
            更新后的精炼结果对象
        """
        try:
            # 获取文件路径
            file_path = screening_result.file_path
            path_parts = os.path.normpath(file_path).split(os.sep)
            
            # 检查已有项目
            for i in range(len(path_parts) - 1, 0, -1):
                potential_project_path = os.sep.join(path_parts[:i])
                
                # 查询数据库中是否有匹配的项目
                project_query = select(Project).where(Project.path == potential_project_path)
                project = self.session.exec(project_query).first()
                
                if project:
                    refine_result.project_id = project.id
                    logger.info(f"识别文件 {file_path} 属于项目: {project.name}")
                    return refine_result
            
            # TODO: 如果没有找到项目，可以根据文件路径特征尝试识别新项目
            
            return refine_result
            
        except Exception as e:
            logger.error(f"识别项目失败: {str(e)}")
            return refine_result
    
    def _calculate_filename_similarity(self, name1: str, name2: str) -> float:
        """计算文件名相似度
        
        Args:
            name1: 第一个文件名
            name2: 第二个文件名
            
        Returns:
            相似度分数(0-1)
        """
        # 简单相似度算法
        if name1 == name2:
            return 1.0
        
        # 检查一个是否是另一个的子串
        if name1 in name2 or name2 in name1:
            return 0.8
        
        # 计算Jaccard相似度
        set1 = set(name1)
        set2 = set(name2)
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        return intersection / union if union > 0 else 0
    
    def get_by_id(self, refine_id: int) -> Optional[FileRefineResult]:
        """根据ID获取精炼结果"""
        return self.session.get(FileRefineResult, refine_id)
    
    def get_by_screening_id(self, screening_id: int) -> Optional[FileRefineResult]:
        """根据粗筛ID获取精炼结果"""
        statement = select(FileRefineResult).where(FileRefineResult.screening_id == screening_id)
        return self.session.exec(statement).first()
    
    def get_by_path(self, file_path: str) -> Optional[FileRefineResult]:
        """根据文件路径获取精炼结果"""
        statement = select(FileRefineResult).where(FileRefineResult.file_path == file_path)
        return self.session.exec(statement).first()
    
    def get_by_project_id(self, project_id: int, limit: int = 100) -> List[FileRefineResult]:
        """获取某个项目下的所有精炼结果"""
        statement = select(FileRefineResult)\
            .where(FileRefineResult.project_id == project_id)\
            .order_by(desc(FileRefineResult.updated_at))\
            .limit(limit)
        return self.session.exec(statement).all()
    
    def delete_refine_result(self, refine_id: int) -> bool:
        """删除精炼结果
        
        Args:
            refine_id: 记录ID
            
        Returns:
            删除成功返回True，失败返回False
        """
        try:
            result = self.get_by_id(refine_id)
            if not result:
                logger.warning(f"删除精炼结果失败: ID {refine_id} 不存在")
                return False
            
            self.session.delete(result)
            self.session.commit()
            
            logger.info(f"删除精炼结果成功: ID {refine_id}")
            return True
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"删除精炼结果失败: {str(e)}")
            return False
    
    def create_project(self, name: str, path: str, project_type: Optional[str] = None) -> Optional[Project]:
        """创建新项目
        
        Args:
            name: 项目名称
            path: 项目路径
            project_type: 项目类型（可选）
            
        Returns:
            创建成功返回项目对象，失败返回None
        """
        try:
            # 检查路径是否存在
            if not os.path.exists(path) or not os.path.isdir(path):
                logger.warning(f"创建项目失败: 路径不存在或不是文件夹 {path}")
                return None
            
            # 检查是否已存在同路径项目
            existing_project_query = select(Project).where(Project.path == path)
            existing_project = self.session.exec(existing_project_query).first()
            
            if existing_project:
                logger.info(f"项目路径已存在: {path}")
                return existing_project
            
            # 创建新项目
            project = Project(
                name=name,
                path=path,
                project_type=project_type,
                discovered_at=datetime.now()
            )
            
            self.session.add(project)
            self.session.commit()
            self.session.refresh(project)
            
            logger.info(f"创建项目成功: {name} 路径: {path}")
            return project
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"创建项目失败: {str(e)}")
            return None
    
    def get_projects(self, limit: int = 50) -> List[Project]:
        """获取项目列表
        
        Args:
            limit: 最多返回条数
            
        Returns:
            项目列表
        """
        try:
            query = select(Project).order_by(desc(Project.updated_at)).limit(limit)
            return self.session.exec(query).all()
            
        except Exception as e:
            logger.error(f"获取项目列表失败: {str(e)}")
            return []