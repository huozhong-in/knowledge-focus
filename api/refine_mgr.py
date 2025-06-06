from typing import List, Dict, Any, Optional, Tuple, Union
from sqlmodel import Session, select, delete, update, and_, or_
from db_mgr import (
    FileScreeningResult, FileScreenResult, 
    FileCategory, FileFilterRule, Project
)
from datetime import datetime, timedelta
import logging
import json
import time
import difflib
import re
import os
import traceback
from collections import defaultdict, Counter
import hashlib

logger = logging.getLogger(__name__)

class RefineManager:
    """文件精细化管理类，提供智能文件夹生成和文件分析功能"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def process_files_for_task(self, task_id: str) -> Dict[str, Any]:
        """处理任务中的所有文件，进行精细化分析"""
        try:
            # 获取待处理的文件
            stmt = select(FileScreeningResult).where(
                and_(
                    FileScreeningResult.task_id == task_id,
                    FileScreeningResult.status == "passed"
                )
            )
            files = self.session.exec(stmt).all()
            
            if not files:
                return {"status": "no_files", "message": "没有找到待处理的文件"}
            
            processed_count = 0
            for file_record in files:
                try:
                    # 基础分析
                    analysis_result = self._basic_analysis(file_record)
                    
                    # 详细分析
                    detailed_analysis = self._analyze_file(file_record)
                    
                    # 项目识别
                    project_info = self._identify_project(file_record)
                    
                    # 保存分析结果
                    self._save_analysis_results(file_record, analysis_result, detailed_analysis, project_info)
                    
                    processed_count += 1
                    
                except Exception as e:
                    logger.error(f"处理文件 {file_record.file_path} 时出错: {str(e)}")
                    continue
            
            # 生成智能文件夹
            wise_folders = self.generate_wise_folders(task_id)
            
            return {
                "status": "success",
                "processed_files": processed_count,
                "wise_folders_count": len(wise_folders)
            }
            
        except Exception as e:
            logger.error(f"处理任务 {task_id} 时出错: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def _basic_analysis(self, file_record: FileScreeningResult) -> Dict[str, Any]:
        """对文件进行基础分析"""
        analysis = {
            "file_id": file_record.id,
            "basic_info": {
                "size_category": self._categorize_file_size(file_record.file_size),
                "extension_group": self._group_extension(file_record.extension),
                "creation_period": self._get_time_period(file_record.created_time),
                "modification_period": self._get_time_period(file_record.modified_time)
            }
        }
        return analysis
    
    def _analyze_file(self, file_record: FileScreeningResult) -> Dict[str, Any]:
        """详细分析文件内容和特征"""
        analysis = {"keywords": [], "entities": [], "topics": [], "similarity_group": None}
        
        try:
            # 基于文件类型进行不同的分析
            if file_record.extension in ['.txt', '.md', '.py', '.js', '.html', '.css']:
                analysis.update(self._analyze_text_file(file_record))
            elif file_record.extension in ['.pdf', '.doc', '.docx', '.ppt', '.pptx']:
                analysis.update(self._analyze_document_file(file_record))
            elif file_record.extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                analysis.update(self._analyze_image_file(file_record))
            elif file_record.extension in ['.mp4', '.avi', '.mov', '.mp3', '.wav']:
                analysis.update(self._analyze_media_file(file_record))
            
            # 从文件名提取信息
            filename_analysis = self._analyze_filename(file_record.file_name)
            analysis.update(filename_analysis)
            
        except Exception as e:
            logger.error(f"分析文件 {file_record.file_path} 时出错: {str(e)}")
        
        return analysis
    
    def _analyze_text_file(self, file_record: FileScreeningResult) -> Dict[str, Any]:
        """分析文本文件"""
        analysis = {"keywords": [], "entities": [], "topics": [], "language": "unknown"}
        
        try:
            # 这里可以添加实际的文件内容读取和分析
            # 由于安全考虑，这里使用文件名和路径进行分析
            content = file_record.file_path + " " + file_record.file_name
            
            # 关键词提取（简化版）
            keywords = self._extract_keywords_from_text(content)
            analysis["keywords"] = keywords
            
            # 实体提取（简化版）
            entities = self._extract_entities_from_text(content)
            analysis["entities"] = entities
            
            # 主题分析（基于文件名和路径）
            topics = self._extract_topics_from_text(content)
            analysis["topics"] = topics
            
        except Exception as e:
            logger.error(f"分析文本文件时出错: {str(e)}")
        
        return analysis
    
    def _analyze_document_file(self, file_record: FileScreeningResult) -> Dict[str, Any]:
        """分析文档文件"""
        # 文档文件分析（基于文件名和元数据）
        return self._analyze_filename(file_record.file_name)
    
    def _analyze_image_file(self, file_record: FileScreeningResult) -> Dict[str, Any]:
        """分析图像文件"""
        analysis = {"keywords": [], "entities": [], "topics": []}
        
        # 基于文件名分析图像
        filename_lower = file_record.file_name.lower()
        
        # 检查是否包含日期信息
        date_patterns = [r'\d{4}-\d{2}-\d{2}', r'\d{8}', r'\d{4}_\d{2}_\d{2}']
        for pattern in date_patterns:
            if re.search(pattern, filename_lower):
                analysis["topics"].append("dated_image")
                break
        
        # 检查是否为截图
        if any(word in filename_lower for word in ['screenshot', '截图', 'screen', 'capture']):
            analysis["topics"].append("screenshot")
        
        # 检查是否为头像或照片
        if any(word in filename_lower for word in ['avatar', 'photo', '头像', '照片', 'portrait']):
            analysis["topics"].append("portrait")
        
        return analysis
    
    def _analyze_media_file(self, file_record: FileScreeningResult) -> Dict[str, Any]:
        """分析媒体文件"""
        analysis = {"keywords": [], "entities": [], "topics": []}
        
        filename_lower = file_record.file_name.lower()
        
        # 检查是否为录音或视频
        if file_record.extension in ['.mp3', '.wav', '.flac']:
            analysis["topics"].append("audio")
        elif file_record.extension in ['.mp4', '.avi', '.mov']:
            analysis["topics"].append("video")
        
        # 检查是否包含会议录音/录像
        if any(word in filename_lower for word in ['meeting', '会议', 'conference', 'call']):
            analysis["topics"].append("meeting_record")
        
        return analysis
    
    def _analyze_filename(self, filename: str) -> Dict[str, Any]:
        """分析文件名，提取关键信息"""
        analysis = {"keywords": [], "entities": [], "topics": [], "tags": []}
        
        # 移除扩展名
        name_without_ext = os.path.splitext(filename)[0]
        
        # 提取关键词（分割文件名）
        keywords = re.findall(r'[A-Za-z\u4e00-\u9fa5]+', name_without_ext)
        analysis["keywords"] = [kw.lower() for kw in keywords if len(kw) > 1]
        
        # 提取可能的实体（大写字母开头的词）
        entities = re.findall(r'[A-Z][a-z]+', name_without_ext)
        analysis["entities"] = entities
        
        # 检查常见标签
        filename_lower = filename.lower()
        common_tags = {
            'draft': ['draft', '草稿', 'temp', '临时'],
            'final': ['final', '最终', 'finished', '完成'],
            'backup': ['backup', '备份', 'bak'],
            'version': ['v1', 'v2', 'version', '版本'],
            'important': ['important', '重要', 'urgent', '紧急'],
            'work': ['work', '工作', 'job', '任务'],
            'personal': ['personal', '个人', 'private', '私人']
        }
        
        for tag, patterns in common_tags.items():
            if any(pattern in filename_lower for pattern in patterns):
                analysis["tags"].append(tag)
        
        return analysis
    
    def _identify_project(self, file_record: FileScreeningResult) -> Dict[str, Any]:
        """识别文件所属项目"""
        project_info = {"project_id": None, "project_name": None}
        
        try:
            # 基于路径识别项目
            if not file_record.file_path:
                return project_info
                
            path_parts = file_record.file_path.split('/')
            if len(path_parts) < 3:
                return project_info
            
            # 查找现有项目
            stmt = select(Project)
            projects = self.session.exec(stmt).all()
            
            for project in projects:
                if project.path in file_record.file_path:
                    project_info["project_id"] = project.id
                    project_info["project_name"] = project.name
                    return project_info
            
            # 如果没有找到匹配的项目，尝试创建新项目（如果路径符合特定模式）
            # 这里以用户文件夹下的第一级目录作为潜在项目
            if '/Users/' in file_record.file_path:
                parts_after_users = file_record.file_path.split('/Users/')[1].split('/')
                if len(parts_after_users) >= 2:
                    user = parts_after_users[0]
                    potential_project = parts_after_users[1]
                    
                    # 检查是否是常见的系统目录
                    system_dirs = ['Downloads', 'Documents', 'Desktop', 'Library', 'Applications']
                    if potential_project not in system_dirs:
                        project_path = f"/Users/{user}/{potential_project}"
                        new_project = Project(
                            name=potential_project,
                            path=project_path,
                            discovered_at=datetime.now()
                        )
                        
                        self.session.add(new_project)
                        self.session.commit()
                        self.session.refresh(new_project)
                        
                        project_info["project_id"] = new_project.id
                        project_info["project_name"] = new_project.name
            
            return project_info
            
        except Exception as e:
            logger.error(f"识别项目时出错: {str(e)}")
            return project_info
    
    def process_pending_file(self, screening_result_id: int) -> Optional[Dict[str, Any]]:
        """处理单个待处理文件
        
        Args:
            screening_result_id: 粗筛结果ID
        
        Returns:
            处理结果字典，如果处理失败则返回None
        """
        try:
            # 获取粗筛结果
            file_record = self.session.get(FileScreeningResult, screening_result_id)
            if not file_record:
                logger.error(f"找不到粗筛结果ID: {screening_result_id}")
                return None
                
            # 检查文件状态
            if file_record.status != "pending":
                logger.info(f"文件已经处理过，状态: {file_record.status}, 跳过处理")
                # 返回一个状态字典，而不是None，这样调用者可以区分"已处理"和"处理失败"
                return {
                    "status": "already_processed",
                    "file_id": screening_result_id,
                    "file_path": file_record.file_path
                }
            
            logger.info(f"开始处理文件: {file_record.file_path}")
            
            try:
                # 基础分析
                analysis_result = self._basic_analysis(file_record)
                
                # 详细分析
                detailed_analysis = self._analyze_file(file_record)
                
                # 项目识别
                project_info = self._identify_project(file_record)
                
                # 保存分析结果
                self._save_analysis_results(file_record, analysis_result, detailed_analysis, project_info)
                
                # 更新文件状态为已处理
                file_record.status = "processed"
                self.session.add(file_record)
                self.session.commit()
                
                # 返回处理结果
                return {
                    "status": "success",
                    "file_id": screening_result_id,
                    "file_path": file_record.file_path,
                    "analysis": analysis_result,
                    "details": detailed_analysis,
                    "project": project_info
                }
            except Exception as analysis_err:
                logger.error(f"分析文件时出错: {str(analysis_err)}")
                import traceback
                logger.error(traceback.format_exc())
                
                # 更新文件状态为失败
                file_record.status = "failed"
                file_record.error_message = f"分析失败: {str(analysis_err)}"
                self.session.add(file_record)
                self.session.commit()
                
                return None
                
        except Exception as e:
            logger.error(f"处理粗筛结果 {screening_result_id} 时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _save_analysis_results(self, file_record: FileScreeningResult, 
                              basic_analysis: Dict, detailed_analysis: Dict, 
                              project_info: Dict):
        """保存分析结果到数据库"""
        try:
            # 保存项目信息
            if project_info["project_name"]:
                project = self._get_or_create_project(project_info)
                
                # 更新文件记录的项目ID
                file_record.project_id = project.id if project else None
            
            # 保存关键词信息
            for keyword in detailed_analysis.get("keywords", []):
                self._save_keyword_info(file_record.id, keyword)
            
            # 保存实体信息
            for entity in detailed_analysis.get("entities", []):
                self._save_entity_info(file_record.id, entity)
            
            # 更新文件记录的分析状态
            file_record.analysis_status = "completed"
            file_record.analysis_time = datetime.now()
            
            self.session.commit()
            
        except Exception as e:
            logger.error(f"保存分析结果时出错: {str(e)}")
            self.session.rollback()
    
    def _get_or_create_project(self, project_info: Dict) -> Optional[Project]:
        """获取或创建项目"""
        try:
            # 查找现有项目
            stmt = select(Project).where(Project.name == project_info["project_name"])
            existing_project = self.session.exec(stmt).first()
            
            if existing_project:
                return existing_project
            
            # 创建新项目
            new_project = Project(
                name=project_info["project_name"],
                path=project_info.get("project_path", ""),
                description=f"自动识别的项目: {project_info['project_name']}",
                discovered_at=datetime.now()
            )
            
            self.session.add(new_project)
            self.session.commit()
            self.session.refresh(new_project)
            
            return new_project
            
        except Exception as e:
            logger.error(f"创建项目时出错: {str(e)}")
            self.session.rollback()
            return None
    
    def _save_keyword_info(self, file_id: int, keyword: str):
        """保存关键词信息到FileRefineResult的JSON字段中"""
        try:
            # 此方法暂时简化，不单独存储关键词
            # 关键词信息将在FileRefineResult中以JSON格式存储
            logger.debug(f"关键词 '{keyword}' 将在文件精炼结果中保存")
        except Exception as e:
            logger.error(f"保存关键词信息时出错: {str(e)}")
    
    def _save_entity_info(self, file_id: int, entity: str):
        """保存实体信息到FileRefineResult的JSON字段中"""
        try:
            # 此方法暂时简化，不单独存储实体
            # 实体信息将在FileRefineResult中以JSON格式存储
            logger.debug(f"实体 '{entity}' 将在文件精炼结果中保存")
        except Exception as e:
            logger.error(f"保存实体信息时出错: {str(e)}")
    
    def generate_wise_folders(self, task_id: str) -> List[Dict[str, Any]]:
        """生成智能文件夹"""
        try:
            # 获取任务中的所有文件
            stmt = select(FileScreeningResult).where(FileScreeningResult.task_id == task_id)
            files = self.session.exec(stmt).all()
            
            if not files:
                return []
            
            wise_folders = []
            
            # 1. 按类别分组
            wise_folders.extend(self._generate_category_wise_folders(files))
            
            # 2. 按标签分组
            wise_folders.extend(self._generate_tag_wise_folders(files))
            
            # 3. 按项目分组
            wise_folders.extend(self._generate_project_wise_folders(files))
            
            # 4. 按主题分组
            wise_folders.extend(self._generate_topic_wise_folders(files))
            
            # 5. 按实体分组
            wise_folders.extend(self._generate_entity_wise_folders(files))
            
            # 6. 按相似性分组
            wise_folders.extend(self._generate_similarity_wise_folders(files))
            
            # 7. 按元数据分组
            wise_folders.extend(self._generate_metadata_wise_folders(files))
            
            # 8. 按状态分组
            wise_folders.extend(self._generate_status_wise_folders(files))
            
            # 保存智能文件夹到数据库
            self._save_wise_folders(task_id, wise_folders)
            
            return wise_folders
            
        except Exception as e:
            logger.error(f"生成智能文件夹时出错: {str(e)}")
            return []
    
    def _generate_category_wise_folders(self, files: List[FileScreeningResult]) -> List[Dict[str, Any]]:
        """按文件类别生成智能文件夹"""
        category_groups = defaultdict(list)
        
        for file in files:
            if file.category_id:
                # 获取类别信息
                category = self.session.get(FileCategory, file.category_id)
                category_name = category.name if category else "未知类别"
                category_groups[category_name].append(file.id)
        
        folders = []
        for category_name, file_ids in category_groups.items():
            if len(file_ids) >= 2:  # 至少2个文件才创建文件夹
                folders.append({
                    "name": f"类别: {category_name}",
                    "type": "category",
                    "criteria": {"category": category_name},
                    "file_count": len(file_ids),
                    "file_ids": file_ids,
                    "description": f"包含 {len(file_ids)} 个 {category_name} 文件"
                })
        
        return folders
    
    def _generate_tag_wise_folders(self, files: List[FileScreeningResult]) -> List[Dict[str, Any]]:
        """按标签生成智能文件夹"""
        tag_groups = defaultdict(list)
        
        for file in files:
            # 从文件名分析标签
            analysis = self._analyze_filename(file.file_name)
            for tag in analysis.get("tags", []):
                tag_groups[tag].append(file.id)
        
        folders = []
        for tag, file_ids in tag_groups.items():
            if len(file_ids) >= 2:
                folders.append({
                    "name": f"标签: {tag}",
                    "type": "tag",
                    "criteria": {"tag": tag},
                    "file_count": len(file_ids),
                    "file_ids": file_ids,
                    "description": f"包含 {len(file_ids)} 个带有 '{tag}' 标签的文件"
                })
        
        return folders
    
    def _generate_project_wise_folders(self, files: List[FileScreeningResult]) -> List[Dict[str, Any]]:
        """按项目生成智能文件夹"""
        project_groups = defaultdict(list)
        
        for file in files:
            # 防御性检查：确保file对象有project_id属性
            if hasattr(file, 'project_id') and file.project_id:
                project = self.session.get(Project, file.project_id)
                project_name = project.name if project else "未知项目"
                project_groups[project_name].append(file.id)
            else:
                # 如果没有project_id，尝试从文件路径推断项目
                path_parts = file.file_path.split('/')
                if len(path_parts) > 2:
                    project_name = path_parts[2]  # 取路径的第三部分作为项目名
                    project_groups[project_name].append(file.id)
        
        folders = []
        for project_name, file_ids in project_groups.items():
            if len(file_ids) >= 1:  # 项目文件夹可以只有1个文件
                folders.append({
                    "name": f"项目: {project_name}",
                    "type": "project",
                    "criteria": {"project": project_name},
                    "file_count": len(file_ids),
                    "file_ids": file_ids,
                    "description": f"项目 '{project_name}' 包含 {len(file_ids)} 个文件"
                })
        
        return folders
    
    def _generate_topic_wise_folders(self, files: List[FileScreeningResult]) -> List[Dict[str, Any]]:
        """按主题生成智能文件夹"""
        topic_groups = defaultdict(list)
        
        for file in files:
            # 从文件分析中获取主题
            analysis = self._analyze_file(file)
            for topic in analysis.get("topics", []):
                topic_groups[topic].append(file.id)
        
        folders = []
        for topic, file_ids in topic_groups.items():
            if len(file_ids) >= 2:
                folders.append({
                    "name": f"主题: {topic}",
                    "type": "topic",
                    "criteria": {"topic": topic},
                    "file_count": len(file_ids),
                    "file_ids": file_ids,
                    "description": f"主题 '{topic}' 相关的 {len(file_ids)} 个文件"
                })
        
        return folders
    
    def _generate_entity_wise_folders(self, files: List[FileScreeningResult]) -> List[Dict[str, Any]]:
        """按实体生成智能文件夹"""
        entity_groups = defaultdict(list)
        
        for file in files:
            # 从文件分析中获取实体
            analysis = self._analyze_file(file)
            for entity in analysis.get("entities", []):
                entity_groups[entity].append(file.id)
        
        folders = []
        for entity, file_ids in entity_groups.items():
            if len(file_ids) >= 2:
                folders.append({
                    "name": f"实体: {entity}",
                    "type": "entity",
                    "criteria": {"entity": entity},
                    "file_count": len(file_ids),
                    "file_ids": file_ids,
                    "description": f"与 '{entity}' 相关的 {len(file_ids)} 个文件"
                })
        
        return folders
    
    def _generate_similarity_wise_folders(self, files: List[FileScreeningResult]) -> List[Dict[str, Any]]:
        """按相似性生成智能文件夹"""
        folders = []
        processed_files = set()
        
        for i, file1 in enumerate(files):
            if file1.id in processed_files:
                continue
                
            similar_files = [file1.id]
            
            for j, file2 in enumerate(files[i+1:], i+1):
                if file2.id in processed_files:
                    continue
                
                # 计算文件名相似度
                similarity = self._calculate_filename_similarity(file1.file_name, file2.file_name)
                if similarity > 0.6:  # 相似度阈值
                    similar_files.append(file2.id)
                    processed_files.add(file2.id)
            
            if len(similar_files) >= 2:
                processed_files.add(file1.id)
                folders.append({
                    "name": f"相似文件组: {file1.file_name[:20]}...",
                    "type": "similarity",
                    "criteria": {"base_file": file1.file_name},
                    "file_count": len(similar_files),
                    "file_ids": similar_files,
                    "description": f"与 '{file1.file_name}' 相似的 {len(similar_files)} 个文件"
                })
        
        return folders
    
    def _generate_metadata_wise_folders(self, files: List[FileScreeningResult]) -> List[Dict[str, Any]]:
        """按元数据生成智能文件夹"""
        folders = []
        
        # 按时间分组
        time_groups = defaultdict(list)
        for file in files:
            if file.created_time:
                period = self._get_time_period(file.created_time)
                time_groups[period].append(file.id)
        
        for period, file_ids in time_groups.items():
            if len(file_ids) >= 3:
                folders.append({
                    "name": f"时间: {period}",
                    "type": "time",
                    "criteria": {"time_period": period},
                    "file_count": len(file_ids),
                    "file_ids": file_ids,
                    "description": f"{period} 创建的 {len(file_ids)} 个文件"
                })
        
        # 按大小分组
        size_groups = defaultdict(list)
        for file in files:
            size_category = self._categorize_file_size(file.file_size)
            size_groups[size_category].append(file.id)
        
        for size_category, file_ids in size_groups.items():
            if len(file_ids) >= 3:
                folders.append({
                    "name": f"大小: {size_category}",
                    "type": "size",
                    "criteria": {"size_category": size_category},
                    "file_count": len(file_ids),
                    "file_ids": file_ids,
                    "description": f"{size_category} 文件 {len(file_ids)} 个"
                })
        
        return folders
    
    def _generate_status_wise_folders(self, files: List[FileScreeningResult]) -> List[Dict[str, Any]]:
        """按处理状态生成智能文件夹"""
        status_groups = defaultdict(list)
        
        for file in files:
            status = file.status or "未知状态"
            status_groups[status].append(file.id)
        
        folders = []
        for status, file_ids in status_groups.items():
            if len(file_ids) >= 1:
                folders.append({
                    "name": f"状态: {status}",
                    "type": "status",
                    "criteria": {"status": status},
                    "file_count": len(file_ids),
                    "file_ids": file_ids,
                    "description": f"状态为 '{status}' 的 {len(file_ids)} 个文件"
                })
        
        return folders
    
    def _save_wise_folders(self, task_id: str, folders: List[Dict[str, Any]]):
        """保存智能文件夹到数据库
        
        使用任务的extra_data字段存储智能文件夹信息，将任务的更新时间设为当前时间
        """
        try:
            from db_mgr import Task
            from datetime import datetime
            
            # 记录生成的文件夹数
            logger.info(f"任务 {task_id} 生成了 {len(folders)} 个智能文件夹:")
            for folder in folders:
                logger.info(f"  - {folder['name']}: {folder['file_count']} 个文件")
            
            # 使用任务的extra_data字段存储智能文件夹数据
            try:
                # 获取任务
                stmt = select(Task).where(Task.id == int(task_id))
                task = self.session.exec(stmt).first()
                
                if task:
                    # 准备数据
                    wise_folders_data = {
                        "wise_folders": folders,
                        "generated_at": datetime.now().isoformat(),
                        "folder_count": len(folders)
                    }
                    
                    # 更新任务的extra_data字段
                    if not task.extra_data:
                        task.extra_data = wise_folders_data
                    else:
                        # 如果extra_data是字符串，先解析为字典
                        if isinstance(task.extra_data, str):
                            try:
                                current_data = json.loads(task.extra_data)
                            except Exception:
                                current_data = {}
                        else:
                            current_data = task.extra_data
                            
                        # 更新数据
                        current_data.update(wise_folders_data)
                        task.extra_data = current_data
                    
                    # 更新任务更新时间
                    task.updated_at = datetime.now()
                    
                    # 保存更改
                    self.session.add(task)
                    self.session.commit()
                    
                    logger.info(f"已将 {len(folders)} 个智能文件夹数据保存到任务 {task_id} 的extra_data字段")
                else:
                    logger.warning(f"找不到任务ID: {task_id}，无法保存智能文件夹数据")
            except Exception as e:
                logger.error(f"保存智能文件夹数据到任务失败: {str(e)}")
                logger.error(traceback.format_exc())
                
        except Exception as e:
            logger.error(f"保存智能文件夹时出错: {str(e)}")
            logger.error(traceback.format_exc())
    
    # 辅助方法
    def _categorize_file_size(self, size: int) -> str:
        """根据文件大小分类"""
        if size < 1024:  # < 1KB
            return "微小"
        elif size < 1024 * 1024:  # < 1MB
            return "小"
        elif size < 10 * 1024 * 1024:  # < 10MB
            return "中"
        elif size < 100 * 1024 * 1024:  # < 100MB
            return "大"
        else:
            return "超大"
    
    def _group_extension(self, extension: str) -> str:
        """根据扩展名分组"""
        if not extension:
            return "无扩展名"
        
        ext = extension.lower()
        
        if ext in ['.txt', '.md', '.doc', '.docx', '.pdf', '.rtf']:
            return "文档"
        elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg']:
            return "图片"
        elif ext in ['.mp4', '.avi', '.mov', '.wmv', '.flv']:
            return "视频"
        elif ext in ['.mp3', '.wav', '.flac', '.aac', '.ogg']:
            return "音频"
        elif ext in ['.zip', '.rar', '.7z', '.tar', '.gz']:
            return "压缩文件"
        elif ext in ['.py', '.js', '.html', '.css', '.java', '.cpp', '.c']:
            return "代码"
        else:
            return "其他"
    
    def _get_time_period(self, timestamp: datetime) -> str:
        """获取时间段标识"""
        if not timestamp:
            return "未知时间"
        
        now = datetime.now()
        delta = now - timestamp
        
        if delta.days == 0:
            return "今天"
        elif delta.days == 1:
            return "昨天"
        elif delta.days <= 7:
            return "本周"
        elif delta.days <= 30:
            return "本月"
        elif delta.days <= 90:
            return "最近三个月"
        elif delta.days <= 365:
            return "今年"
        else:
            return f"{timestamp.year}年"
    
    def _calculate_filename_similarity(self, name1: str, name2: str) -> float:
        """计算文件名相似度"""
        # 移除扩展名
        name1_clean = os.path.splitext(name1)[0].lower()
        name2_clean = os.path.splitext(name2)[0].lower()
        
        # 使用difflib计算相似度
        return difflib.SequenceMatcher(None, name1_clean, name2_clean).ratio()
    
    def _extract_keywords_from_text(self, text: str) -> List[str]:
        """从文本中提取关键词"""
        # 简化版关键词提取
        words = re.findall(r'[A-Za-z\u4e00-\u9fa5]+', text.lower())
        # 过滤常见停用词
        stop_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        keywords = [word for word in words if len(word) > 2 and word not in stop_words]
        
        # 返回出现频率最高的关键词
        word_count = Counter(keywords)
        return [word for word, count in word_count.most_common(10)]
    
    def _extract_entities_from_text(self, text: str) -> List[str]:
        """从文本中提取实体"""
        # 简化版实体提取（提取大写字母开头的词）
        entities = re.findall(r'[A-Z][a-z]+', text)
        return list(set(entities))  # 去重
    
    def _extract_topics_from_text(self, text: str) -> List[str]:
        """从文本中提取主题"""
        # 基于关键词和路径信息推断主题
        topics = []
        text_lower = text.lower()
        
        # 技术相关主题
        if any(tech in text_lower for tech in ['python', 'javascript', 'java', 'code', '代码']):
            topics.append('programming')
        
        # 文档相关主题
        if any(doc in text_lower for doc in ['report', '报告', 'document', '文档', 'readme']):
            topics.append('documentation')
        
        # 图片相关主题
        if any(img in text_lower for img in ['image', '图片', 'photo', '照片', 'picture']):
            topics.append('image')
        
        # 工作相关主题
        if any(work in text_lower for work in ['work', '工作', 'business', '商务', 'meeting', '会议']):
            topics.append('work')
        
        return topics
    
    # 查询方法实现
    def get_wise_folders_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务的智能文件夹
        
        首先尝试从任务的extra_data字段获取保存的智能文件夹数据
        如果没有找到或数据不完整，则重新生成
        """
        try:
            from db_mgr import Task
            
            # 尝试从任务的extra_data字段获取智能文件夹数据
            stmt = select(Task).where(Task.id == int(task_id))
            task = self.session.exec(stmt).first()
            
            if task and task.extra_data:
                # 从任务的extra_data字段获取智能文件夹数据
                extra_data = task.extra_data
                if isinstance(extra_data, str):
                    try:
                        extra_data = json.loads(extra_data)
                    except Exception:
                        extra_data = {}
                
                # 检查是否有智能文件夹数据
                if isinstance(extra_data, dict) and 'wise_folders' in extra_data:
                    wise_folders = extra_data.get('wise_folders', [])
                    if wise_folders and isinstance(wise_folders, list) and len(wise_folders) > 0:
                        logger.info(f"从任务 {task_id} 的extra_data字段获取到 {len(wise_folders)} 个智能文件夹")
                        return wise_folders
            
            # 如果没有找到保存的智能文件夹数据或数据不完整，重新生成
            logger.info(f"重新生成任务 {task_id} 的智能文件夹")
            return self.generate_wise_folders(task_id)
            
        except Exception as e:
            logger.error(f"获取智能文件夹时出错: {str(e)}")
            logger.error(traceback.format_exc())
            return []
    
    def get_files_in_wise_folder(self, task_id: str, folder_type: str, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取智能文件夹中的文件"""
        try:
            # 根据不同的文件夹类型和条件查询文件
            if folder_type == "category":
                return self.get_files_by_category(task_id, criteria.get("category"))
            elif folder_type == "tag":
                return self.get_files_by_tag(task_id, criteria.get("tag"))
            elif folder_type == "project":
                return self.get_files_by_project(task_id, criteria.get("project"))
            elif folder_type == "topic":
                return self.get_files_by_topic(task_id, criteria.get("topic"))
            elif folder_type == "entity":
                return self.get_files_by_entity(task_id, criteria.get("entity"))
            elif folder_type == "time":
                return self.get_files_by_time_period(task_id, criteria.get("time_period"))
            else:
                return []
                
        except Exception as e:
            logger.error(f"获取文件夹文件时出错: {str(e)}")
            return []
    
    def get_files_by_category(self, task_id: str, category_name: str) -> List[Dict[str, Any]]:
        """根据类别获取文件"""
        try:
            # 先找到类别ID
            category_stmt = select(FileCategory).where(FileCategory.name == category_name)
            category = self.session.exec(category_stmt).first()
            
            if not category:
                return []
            
            # 查询文件
            stmt = select(FileScreeningResult).where(
                and_(
                    FileScreeningResult.task_id == task_id,
                    FileScreeningResult.category_id == category.id
                )
            )
            files = self.session.exec(stmt).all()
            
            return [self._file_to_dict(file) for file in files]
            
        except Exception as e:
            logger.error(f"根据类别获取文件时出错: {str(e)}")
            return []
    
    def get_files_by_tag(self, task_id: str, tag: str) -> List[Dict[str, Any]]:
        """根据标签获取文件"""
        try:
            stmt = select(FileScreeningResult).where(FileScreeningResult.task_id == task_id)
            files = self.session.exec(stmt).all()
            
            # 过滤包含指定标签的文件
            result = []
            for file in files:
                analysis = self._analyze_filename(file.file_name)
                if tag in analysis.get("tags", []):
                    result.append(self._file_to_dict(file))
            
            return result
            
        except Exception as e:
            logger.error(f"根据标签获取文件时出错: {str(e)}")
            return []
    
    def get_files_by_project(self, task_id: str, project_name: str) -> List[Dict[str, Any]]:
        """根据项目获取文件"""
        try:
            # 先找到项目ID
            project_stmt = select(Project).where(Project.name == project_name)
            project = self.session.exec(project_stmt).first()
            
            if not project:
                return []
            
            # 查询文件
            stmt = select(FileScreeningResult).where(
                and_(
                    FileScreeningResult.task_id == task_id,
                    FileScreeningResult.project_id == project.id
                )
            )
            files = self.session.exec(stmt).all()
            
            return [self._file_to_dict(file) for file in files]
            
        except Exception as e:
            logger.error(f"根据项目获取文件时出错: {str(e)}")
            return []
    
    def get_files_by_topic(self, task_id: str, topic: str) -> List[Dict[str, Any]]:
        """根据主题获取文件"""
        try:
            stmt = select(FileScreeningResult).where(FileScreeningResult.task_id == task_id)
            files = self.session.exec(stmt).all()
            
            # 过滤包含指定主题的文件
            result = []
            for file in files:
                analysis = self._analyze_file(file)
                if topic in analysis.get("topics", []):
                    result.append(self._file_to_dict(file))
            
            return result
            
        except Exception as e:
            logger.error(f"根据主题获取文件时出错: {str(e)}")
            return []
    
    def get_files_by_entity(self, task_id: str, entity: str) -> List[Dict[str, Any]]:
        """根据实体获取文件"""
        try:
            stmt = select(FileScreeningResult).where(FileScreeningResult.task_id == task_id)
            files = self.session.exec(stmt).all()
            
            # 过滤包含指定实体的文件
            result = []
            for file in files:
                analysis = self._analyze_file(file)
                if entity in analysis.get("entities", []):
                    result.append(self._file_to_dict(file))
            
            return result
            
        except Exception as e:
            logger.error(f"根据实体获取文件时出错: {str(e)}")
            return []
    
    def get_files_by_time_period(self, task_id: str, time_period: str) -> List[Dict[str, Any]]:
        """根据时间段获取文件"""
        try:
            stmt = select(FileScreeningResult).where(FileScreeningResult.task_id == task_id)
            files = self.session.exec(stmt).all()
            
            # 过滤指定时间段的文件
            result = []
            for file in files:
                if file.created_time and self._get_time_period(file.created_time) == time_period:
                    result.append(self._file_to_dict(file))
            
            return result
            
        except Exception as e:
            logger.error(f"根据时间段获取文件时出错: {str(e)}")
            return []
    
    def get_files_by_similarity(self, task_id: str, base_filename: str, threshold: float = 0.6) -> List[Dict[str, Any]]:
        """根据相似性获取文件"""
        try:
            stmt = select(FileScreeningResult).where(FileScreeningResult.task_id == task_id)
            files = self.session.exec(stmt).all()
            
            # 找到相似的文件
            result = []
            for file in files:
                similarity = self._calculate_filename_similarity(base_filename, file.file_name)
                if similarity >= threshold:
                    file_dict = self._file_to_dict(file)
                    file_dict["similarity"] = similarity
                    result.append(file_dict)
            
            # 按相似度排序
            result.sort(key=lambda x: x["similarity"], reverse=True)
            
            return result
            
        except Exception as e:
            logger.error(f"根据相似性获取文件时出错: {str(e)}")
            return []
    
    def get_projects(self, task_id: str = None) -> List[Dict[str, Any]]:
        """获取项目列表"""
        try:
            if (task_id):
                # 获取特定任务相关的项目
                file_stmt = select(FileScreeningResult.project_id).where(
                    and_(
                        FileScreeningResult.task_id == task_id,
                        FileScreeningResult.project_id.is_not(None)
                    )
                ).distinct()
                
                project_ids = [row[0] for row in self.session.exec(file_stmt).all()]
                
                if not project_ids:
                    return []
                
                stmt = select(Project).where(Project.id.in_(project_ids))
            else:
                # 获取所有项目
                stmt = select(Project)
            
            projects = self.session.exec(stmt).all()
            
            result = []
            for project in projects:
                result.append({
                    "id": project.id,
                    "name": project.name,
                    "path": project.path,
                    "description": project.description,
                    "discovered_at": project.discovered_at
                })
            
            return result
            
        except Exception as e:
            logger.error(f"获取项目列表时出错: {str(e)}")
            return []
    
    def create_project(self, name: str, path: str, description: str = None) -> Optional[Dict[str, Any]]:
        """创建新项目"""
        try:
            # 检查项目是否已存在
            existing_stmt = select(Project).where(Project.name == name)
            existing_project = self.session.exec(existing_stmt).first()
            
            if existing_project:
                return None  # 项目已存在
            
            # 创建新项目
            new_project = Project(
                name=name,
                path=path,
                description=description or f"项目: {name}",
                discovered_at=datetime.now()
            )
            
            self.session.add(new_project)
            self.session.commit()
            self.session.refresh(new_project)
            
            return {
                "id": new_project.id,
                "name": new_project.name,
                "path": new_project.path,
                "description": new_project.description,
                "discovered_at": new_project.discovered_at
            }
            
        except Exception as e:
            logger.error(f"创建项目时出错: {str(e)}")
            self.session.rollback()
            return None
    
    def _file_to_dict(self, file: FileScreeningResult) -> Dict[str, Any]:
        """将文件记录转换为字典"""
        result = {
            "id": file.id,
            "file_path": file.file_path,
            "file_name": file.file_name,
            "file_size": file.file_size,
            "extension": file.extension,
            "status": file.status,
            "task_id": file.task_id
        }
        
        # 安全地添加可选字段
        if hasattr(file, 'file_hash') and file.file_hash:
            result["file_hash"] = file.file_hash
        
        if hasattr(file, 'created_time') and file.created_time:
            result["created_time"] = file.created_time
            
        if hasattr(file, 'modified_time') and file.modified_time:
            result["modified_time"] = file.modified_time
            
        if hasattr(file, 'category_id') and file.category_id:
            result["category_id"] = file.category_id
            
        if hasattr(file, 'project_id') and file.project_id:
            result["project_id"] = file.project_id
            
        return result