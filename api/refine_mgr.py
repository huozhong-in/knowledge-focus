from typing import List, Dict, Any, Optional, Tuple, Union
from sqlmodel import Session, select, delete, update, and_, or_
from sqlalchemy.orm import joinedload
from sqlalchemy import text, func
from db_mgr import (
    FileScreeningResult, FileScreenResult, 
    FileCategory, FileFilterRule, Project,
    FileRefineResult, FileRefineStatus, FileAnalysisType, ProjectRecognitionRule,
    Task, TaskType
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
import pathlib

logger = logging.getLogger(__name__)

class RefineManager:
    """文件信息精炼类，提供智慧文件夹生成功能"""
    
    def __init__(self, session: Session):
        self.session = session

    def process_screening_result(self, screening_id: int) -> Optional[FileRefineResult]:
        """处理单个粗筛结果，生成或更新精炼结果。"""
        logger.info(f"开始处理粗筛结果 ID: {screening_id}")
        start_time = time.time()

        screening_result: Optional[FileScreeningResult] = self.session.get(FileScreeningResult, screening_id)
        if not screening_result:
            logger.warning(f"未找到 ID 为 {screening_id} 的粗筛结果")
            return None

        # 检查是否已存在精炼结果，如果存在则更新，否则创建新的
        refine_result = self.session.exec(
            select(FileRefineResult).where(FileRefineResult.screening_id == screening_id)
        ).first()

        # 获取或创建task_id
        task_id = None
        if screening_result.task_id:
            task_id = screening_result.task_id
        else:
            # 如果粗筛结果没有task_id，查找或创建一个默认的精炼任务
            default_task = self.session.exec(
                select(Task).where(Task.task_type == TaskType.REFINE.value).order_by(Task.created_at.desc())
            ).first()
            
            if not default_task:
                # 创建一个新的精炼任务
                default_task = Task(
                    task_name="默认精炼任务",
                    task_type=TaskType.REFINE.value,
                    status="completed",  # 设置为已完成状态
                    result="success",
                    extra_data={"auto_created": True}
                )
                self.session.add(default_task)
                try:
                    self.session.commit()
                    self.session.refresh(default_task)
                    logger.info(f"创建了新的默认精炼任务 ID: {default_task.id}")
                except Exception as e:
                    logger.error(f"创建默认精炼任务失败: {e}")
                    self.session.rollback()
            
            task_id = default_task.id if default_task else None

        if not refine_result:
            refine_result = FileRefineResult(
                screening_id=screening_id,
                file_path=screening_result.file_path,
                status=FileRefineStatus.PENDING.value, # 初始状态
                analysis_type=FileAnalysisType.BASIC.value, # 初始分析类型
                task_id=task_id  # 使用获取或创建的task_id
            )
            self.session.add(refine_result)
            # 先提交一次获取ID，如果后续失败可以回滚或标记错误
            try:
                self.session.commit()
                self.session.refresh(refine_result)
            except Exception as e:
                logger.error(f"为 screening_id {screening_id} 创建初始 FileRefineResult 失败: {e}")
                self.session.rollback()
                return None
        elif not refine_result.task_id and task_id:
            # 如果已存在的精炼结果没有task_id，但我们现在有了一个，更新它
            refine_result.task_id = task_id
        
        # 更新状态为处理中
        refine_result.status = FileRefineStatus.PROCESSING.value
        refine_result.updated_at = datetime.now()
        try:
            self.session.commit()
            self.session.refresh(refine_result)
        except Exception as e:
            logger.error(f"更新 FileRefineResult {refine_result.id} 状态为 PROCESSING 失败: {e}")
            self.session.rollback()
            # 即使状态更新失败，也尝试继续处理，但记录错误
            refine_result.error_message = f"状态更新失败: {e}"

        try:
            # 1. 基本元数据提取和特征工程 (基于文件名和粗筛元数据)
            refine_result.extra_metadata = self._extract_basic_metadata(screening_result)
            refine_result.features = self._derive_features_from_metadata(screening_result, refine_result.extra_metadata)

            # 2. 项目识别 (基于规则)
            project = self._identify_project(screening_result.file_path)
            if project:
                refine_result.project_id = project.id
                refine_result.analysis_type = FileAnalysisType.PROJECT.value # 如果识别出项目，更新分析类型
            
            # 3. 关联文件分析 (基于元数据，例如同一目录下特定类型文件)
            refine_result.related_files = self._find_related_files_metadata_based(screening_result, project)

            # 4. 相似文件分析 (基于文件名、大小、修改时间等简单元数据)
            refine_result.similar_files = self._find_similar_files_metadata_based(screening_result)

            refine_result.status = FileRefineStatus.COMPLETE.value
            refine_result.error_message = None # 清除之前的错误信息

        except Exception as e:
            logger.error(f"处理 screening_id {screening_id} 时发生错误: {e}")
            logger.error(traceback.format_exc())
            refine_result.status = FileRefineStatus.FAILED.value
            refine_result.error_message = str(e)
        
        refine_result.processing_time = time.time() - start_time
        refine_result.updated_at = datetime.now()

        try:
            self.session.commit()
            self.session.refresh(refine_result)
            logger.info(f"成功处理并保存精炼结果 ID: {refine_result.id} (粗筛 ID: {screening_id})")
        except Exception as e:
            logger.error(f"保存精炼结果 ID: {refine_result.id} 失败: {e}")
            self.session.rollback()
            # 即使最后保存失败，也返回已部分处理的 refine_result 对象，但状态可能是 FAILED

        return refine_result

    def process_all_pending_screening_results(self) -> Dict[str, Any]:
        """处理所有待处理的粗筛结果，返回处理统计信息。
        
        Returns:
            Dict[str, Any]: 处理结果统计，包含以下字段:
                - success (bool): 整体处理是否成功
                - processed (int): 已处理的粗筛结果数量
                - success_count (int): 成功处理的数量
                - failed_count (int): 处理失败的数量
                - error (str, optional): 如果处理失败，则包含错误信息
        """
        logger.info("开始批量处理待处理粗筛结果")
        start_time = time.time()
        
        # 查询所有待处理的粗筛结果
        try:
            # 查询尚未有对应精炼结果的粗筛结果
            # 这里可以根据需要调整查询条件，例如只处理特定状态或类别的粗筛结果
            subquery = select(FileRefineResult.screening_id)
            screening_results = self.session.exec(
                select(FileScreeningResult)
                .where(~FileScreeningResult.id.in_(subquery))
                .order_by(FileScreeningResult.created_at)
                .limit(500)  # 限制每批处理的数量，避免处理时间过长
            ).all()
            
            if not screening_results:
                logger.info("没有找到需要处理的粗筛结果")
                return {
                    "success": True,
                    "processed": 0,
                    "success_count": 0,
                    "failed_count": 0
                }
                
            total = len(screening_results)
            success_count = 0
            failed_count = 0
            
            logger.info(f"找到 {total} 个待处理的粗筛结果")
            
            # 批量处理
            for idx, screening_result in enumerate(screening_results):
                try:
                    # 处理单个粗筛结果
                    refine_result = self.process_screening_result(screening_result.id)
                    if refine_result and refine_result.status == FileRefineStatus.COMPLETE.value:
                        success_count += 1
                    else:
                        failed_count += 1
                    
                    # 每处理20个提交一次，减少数据库压力
                    if (idx + 1) % 20 == 0:
                        self.session.commit()
                        elapsed = time.time() - start_time
                        logger.info(f"已处理 {idx + 1}/{total} 条记录，成功：{success_count}，失败：{failed_count}，耗时：{elapsed:.2f}秒")
                        
                except Exception as e:
                    failed_count += 1
                    logger.error(f"处理粗筛结果 ID: {screening_result.id} 时出错: {e}")
                    logger.error(traceback.format_exc())
            
            # 最后提交一次
            self.session.commit()
            
            elapsed_time = time.time() - start_time
            logger.info(f"批量处理完成，总计 {total} 条记录，成功：{success_count}，失败：{failed_count}，总耗时：{elapsed_time:.2f}秒")
            
            return {
                "success": True,
                "processed": total,
                "success_count": success_count,
                "failed_count": failed_count,
                "elapsed_time": elapsed_time
            }
        
        except Exception as e:
            logger.error(f"批量处理粗筛结果时发生错误: {e}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "processed": 0,
                "success_count": 0,
                "failed_count": 0,
                "error": str(e)
            }

    def update_missing_task_ids(self) -> Dict[str, Any]:
        """为没有task_id的FileRefineResult记录设置task_id。
        
        Returns:
            Dict[str, Any]: 处理结果统计
        """
        logger.info("开始更新缺失的task_id")
        start_time = time.time()
        
        try:
            # 查找所有没有task_id的FileRefineResult记录
            results = self.session.exec(
                select(FileRefineResult)
                .where(FileRefineResult.task_id == None)
            ).all()
            
            if not results:
                logger.info("没有找到缺失task_id的记录")
                return {
                    "success": True,
                    "processed": 0,
                    "updated": 0
                }
            
            # 获取或创建一个默认的精炼任务
            default_task = self.session.exec(
                select(Task).where(Task.task_type == TaskType.REFINE.value).order_by(Task.created_at.desc())
            ).first()
            
            if not default_task:
                # 创建一个新的精炼任务
                default_task = Task(
                    task_name="默认精炼任务",
                    task_type=TaskType.REFINE.value,
                    status="completed",  # 设置为已完成状态
                    result="success",
                    extra_data={"auto_created": True, "for_missing_task_ids": True}
                )
                self.session.add(default_task)
                try:
                    self.session.commit()
                    self.session.refresh(default_task)
                    logger.info(f"创建了新的默认精炼任务 ID: {default_task.id}")
                except Exception as e:
                    logger.error(f"创建默认精炼任务失败: {e}")
                    self.session.rollback()
                    return {
                        "success": False,
                        "error": f"创建默认精炼任务失败: {e}"
                    }
            
            # 更新所有缺失task_id的记录
            updated_count = 0
            for idx, result in enumerate(results):
                result.task_id = default_task.id
                updated_count += 1
                
                # 每更新100条提交一次，减少数据库压力
                if (idx + 1) % 100 == 0:
                    self.session.commit()
                    logger.info(f"已更新 {idx + 1}/{len(results)} 条记录")
            
            # 最后提交一次
            self.session.commit()
            
            elapsed_time = time.time() - start_time
            logger.info(f"更新完成，总计 {len(results)} 条记录，耗时：{elapsed_time:.2f}秒")
            
            return {
                "success": True,
                "processed": len(results),
                "updated": updated_count,
                "task_id": default_task.id,
                "elapsed_time": elapsed_time
            }
            
        except Exception as e:
            logger.error(f"更新缺失task_id时发生错误: {e}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "processed": 0,
                "updated": 0,
                "error": str(e)
            }

    def _extract_basic_metadata(self, screening_result: FileScreeningResult) -> Dict[str, Any]:
        """从粗筛结果中提取或转换基本元数据。"""
        metadata = {
            "file_name": screening_result.file_name,
            "extension": screening_result.extension,
            "file_size_kb": screening_result.file_size / 1024 if screening_result.file_size else 0,
            "created_time_iso": screening_result.created_time.isoformat() if screening_result.created_time else None,
            "modified_time_iso": screening_result.modified_time.isoformat() if screening_result.modified_time else None,
            "accessed_time_iso": screening_result.accessed_time.isoformat() if screening_result.accessed_time else None,
            "tags_from_screening": screening_result.tags or [],
            "category_from_screening": screening_result.category_id 
        }
        # 可以根据需要添加更多从 screening_result 直接获取或简单转换的元数据
        return metadata

    def _derive_features_from_metadata(self, screening_result: FileScreeningResult, basic_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """根据文件名和元数据派生特征。"""
        features = {}
        file_name_lower = screening_result.file_name.lower()

        # 示例：是否为备份文件
        if any(kw in file_name_lower for kw in ["backup", "bak", "_old", "_v_old"]):
            features["is_backup"] = True
        
        # 示例：是否为版本化文件 (简单正则)
        if re.search(r"_v\d+", file_name_lower) or re.search(r"-v\d+", file_name_lower):
            features["is_versioned"] = True

        # 示例：是否为临时文件
        if file_name_lower.startswith(("~", "tmp_", ".~")) or file_name_lower.endswith((".tmp", ".temp")):
            features["is_temporary"] = True
        
        # 示例：从文件名提取日期 (YYYYMMDD, YYYY-MM-DD)
        date_match = re.search(r"(\d{4}[-_]?\d{2}[-_]?\d{2})", screening_result.file_name)
        if date_match:
            features["date_in_filename"] = date_match.group(1).replace("-", "").replace("_", "")

        # 更多特征可以根据 refine_define.md 中的定义添加
        # 例如：按文件名模式/标签 (Filename Pattern / Tag)
        # 这部分逻辑可能需要访问 FileFilterRule 表
        # file_filter_rules = self.session.exec(select(FileFilterRule).where(FileFilterRule.rule_type == 'filename', FileFilterRule.action == 'tag')).all()
        # for rule in file_filter_rules:
        #     if re.search(rule.pattern, screening_result.file_name, re.IGNORECASE if rule.is_case_sensitive is False else 0):
        #         if 'derived_tags' not in features:
        #             features['derived_tags'] = []
        #         features['derived_tags'].append(rule.tag_name) # 假设 FileFilterRule 有 tag_name 字段

        return features

    def _identify_project(self, file_path: str) -> Optional[Project]:
        """根据文件路径和项目识别规则识别项目。"""
        # 获取所有激活的项目识别规则，按优先级排序
        rules = self.session.exec(
            select(ProjectRecognitionRule)
            .where(ProjectRecognitionRule.enabled == True)  # 使用 enabled 字段而不是 is_active
            .order_by(ProjectRecognitionRule.priority.desc())
        ).all()

        path_parts = pathlib.Path(file_path).parts

        for rule in rules:
            try:
                if rule.rule_type == "file_exists_in_parent_folder":
                    # 检查父目录中是否存在特定文件/文件夹
                    # 例如：.git 文件夹表示 Git 项目, pyproject.toml 表示 Python Poetry 项目
                    # rule.pattern 会是 ".git" 或 "pyproject.toml"
                    for i in range(len(path_parts) -1, 0, -1): # 从当前文件所在目录的父目录开始向上查找
                        current_check_path = pathlib.Path(*path_parts[:i])
                        target_path = current_check_path / rule.pattern
                        if target_path.exists():
                            project_name = self._generate_project_name(rule, current_check_path, file_path)
                            return self._get_or_create_project(project_name, rule.description, str(current_check_path))
                
                elif rule.rule_type == "path_regex":
                    # 使用正则表达式匹配路径
                    match = re.search(rule.pattern, file_path)
                    if match:
                        project_root_path = pathlib.Path(file_path).parent
                        project_name = self._generate_project_name(rule, project_root_path, file_path, match_groups=match.groupdict())
                        return self._get_or_create_project(project_name, rule.description, str(project_root_path))
                
                elif rule.rule_type == "folder_name_matches":
                    # 检查路径中的文件夹名称是否匹配
                    for part in reversed(path_parts[:-1]): # 检查所有父文件夹名
                        if re.fullmatch(rule.pattern, part):
                            project_root_path = pathlib.Path(*path_parts[:path_parts.index(part)+1])
                            project_name = self._generate_project_name(rule, project_root_path, file_path)
                            return self._get_or_create_project(project_name, rule.description, str(project_root_path))

            except Exception as e:
                logger.error(f"项目识别规则 '{rule.name}' (ID: {rule.id}) 执行失败: {e}")
                continue # 继续尝试下一个规则
        return None

    def _generate_project_name(self, rule: ProjectRecognitionRule, project_root_path: pathlib.Path, file_path: str, match_groups: Optional[Dict[str, str]] = None) -> str:
        """根据规则和路径信息生成项目名称。"""
        # 获取项目名称的规则：使用 indicators 中的项目名称模板或规则名称 + 目录名
        template = None
        if rule.indicators and isinstance(rule.indicators, dict) and 'name_template' in rule.indicators:
            template = rule.indicators.get('name_template')
        
        if template:
            # 尝试填充模板
            try:
                # 基础可用的占位符
                template_vars = {
                    "folder_name": project_root_path.name,
                    "parent_folder_name": project_root_path.parent.name if project_root_path.parent else "",
                    "rule_name": rule.name,
                    # 可以添加更多基于 project_root_path 或 file_path 的变量
                }
                if match_groups:
                    template_vars.update(match_groups) # 合并正则捕获组
                return template.format(**template_vars)
            except KeyError as e:
                logger.warning(f"生成项目名称时模板 '{template}' 缺少键: {e}. 将使用规则名称+文件夹名.")
                return f"{rule.name}: {project_root_path.name}"
            except Exception as e:
                logger.error(f"使用模板 '{template}' 生成项目名称失败: {e}. 将使用规则名称+文件夹名.")
                return f"{rule.name}: {project_root_path.name}"
        else:
            # 如果没有模板，使用规则名称 + 项目根目录的名称
            return f"{rule.name}: {project_root_path.name}"

    def _get_or_create_project(self, name: str, description: Optional[str] = None, path: Optional[str] = None) -> Project:
        """获取或创建项目。"""
        project = self.session.exec(select(Project).where(Project.name == name)).first()
        if not project:
            project = Project(
                name=name, 
                description=description, 
                path=path or "",  # 添加路径字段，如果未提供则使用空字符串
                # 不再使用 tags 字段，因为 Project 类中没有定义
            )
            self.session.add(project)
            try:
                self.session.commit()
                self.session.refresh(project)
                logger.info(f"创建了新项目: {name}")
            except Exception as e: # 处理可能的唯一约束冲突等
                self.session.rollback()
                logger.error(f"创建项目 '{name}' 失败: {e}. 尝试重新获取.")
                project = self.session.exec(select(Project).where(Project.name == name)).first()
                if not project:
                    logger.error(f"在回滚和重试后仍然无法获取或创建项目 '{name}'.")
                    # 这种情况下可能需要抛出异常或返回一个特定的错误指示
                    raise # 或者返回一个哨兵值/None，让调用者处理
        return project

    def _find_related_files_metadata_based(self, screening_result: FileScreeningResult, project: Optional[Project]) -> Optional[List[int]]:
        """根据元数据找出相关联的文件。
        
        通过文件名模式、所在目录、文件类型等元数据关联文件，不需要读取文件内容。
        
        Args:
            screening_result: 源文件的粗筛结果
            project: 源文件所属项目（如果已识别）
            
        Returns:
            关联的 FileRefineResult ID 列表，如果没有找到则返回 None 或空列表
        """
        logger.debug(f"为 {screening_result.file_path} 查找元数据关联文件 (项目: {project.name if project else '无'})")
        
        try:
            related_files = []
            file_path = screening_result.file_path
            file_name = screening_result.file_name
            extension = screening_result.extension
            
            # 1. 查找同一目录下的文件
            if file_path:
                dir_path = os.path.dirname(file_path)
                dir_files = self.session.exec(
                    select(FileRefineResult)
                    .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
                    .where(
                        FileScreeningResult.file_path.like(f"{dir_path}/%"), 
                        FileScreeningResult.id != screening_result.id
                    )
                    .limit(50)  # 限制结果数量
                ).all()
                
                # 添加目录中的其他文件
                for file in dir_files:
                    if file.id not in related_files:
                        related_files.append(file.id)
            
            # 2. 通过文件名模式匹配查找关联文件
            # 例如: report.docx 可能与 report.pdf, report_v2.docx 相关
            if file_name:
                # 移除扩展名
                name_without_ext = file_name
                if extension and file_name.endswith(extension):
                    name_without_ext = file_name[:-len(extension)]
                
                # 查找文件名相似的文件（基于前缀）
                similar_name_files = self.session.exec(
                    select(FileRefineResult)
                    .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
                    .where(
                        FileScreeningResult.file_name.like(f"{name_without_ext}%"),
                        FileScreeningResult.id != screening_result.id
                    )
                    .limit(20)
                ).all()
                
                for file in similar_name_files:
                    if file.id not in related_files:
                        related_files.append(file.id)
                        
                # 通过版本号模式匹配
                # 例如: report_v1.docx 可能与 report_v2.docx 相关
                version_match = re.search(r"_v(\d+)", name_without_ext)
                if version_match:
                    base_name = name_without_ext.replace(version_match.group(0), "")
                    version_files = self.session.exec(
                        select(FileRefineResult)
                        .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
                        .where(
                            FileScreeningResult.file_name.like(f"{base_name}_v%"),
                            FileScreeningResult.id != screening_result.id
                        )
                        .limit(10)
                    ).all()
                    
                    for file in version_files:
                        if file.id not in related_files:
                            related_files.append(file.id)
            
            # 3. 如果文件属于某个项目，添加同一项目中的关键文件
            if project:
                # 查找同一项目中的文件，限制类型和数量
                project_files = self.session.exec(
                    select(FileRefineResult)
                    .where(
                        FileRefineResult.project_id == project.id,
                        FileRefineResult.id != screening_result.id
                    )
                    .limit(30)
                ).all()
                
                for file in project_files:
                    if file.id not in related_files:
                        related_files.append(file.id)
            
            return related_files if related_files else None
            
        except Exception as e:
            logger.error(f"查找关联文件时发生错误: {e}")
            logger.error(traceback.format_exc())
            return None

    def _find_similar_files_metadata_based(self, screening_result: FileScreeningResult) -> Optional[List[Dict[str, Any]]]:
        """基于元数据查找相似文件。
        
        使用文件名、大小、修改时间等元数据来评估相似性，不需要读取文件内容。
        
        Args:
            screening_result: 源文件的粗筛结果
            
        Returns:
            相似文件列表，每个元素包含 FileRefineResult ID 和相似度得分
            e.g., [{"refine_id": 123, "similarity": 0.85, "reason": "文件名相似"}]
        """
        logger.debug(f"为 {screening_result.file_path} 查找元数据相似文件")
        
        try:
            similar_files = []
            
            # 获取文件基本信息
            file_name = screening_result.file_name
            file_size = screening_result.file_size
            extension = screening_result.extension
            modified_time = screening_result.modified_time
            
            # 1. 基于文件名相似度查找（使用内置的字符串相似度）
            if file_name:
                # 查找所有已精炼的相同扩展名文件（限制数量防止性能问题）
                candidates = self.session.exec(
                    select(FileRefineResult, FileScreeningResult)
                    .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
                    .where(
                        FileScreeningResult.extension == extension if extension else True,
                        FileScreeningResult.id != screening_result.id
                    )
                    .limit(100)  # 限制候选数量
                ).all()
                
                for refine_result, screen_result in candidates:
                    # 计算文件名相似度
                    name_similarity = difflib.SequenceMatcher(None, file_name, screen_result.file_name).ratio()
                    
                    # 计算大小相似度 (如果大小相差超过20%，就认为相似度降低)
                    size_similarity = 1.0
                    if file_size and screen_result.file_size:
                        size_ratio = min(file_size, screen_result.file_size) / max(file_size, screen_result.file_size)
                        size_similarity = size_ratio if size_ratio > 0.8 else 0.5
                    
                    # 计算修改时间接近度
                    time_similarity = 1.0
                    if modified_time and screen_result.modified_time:
                        # 如果修改时间在一天内，给予较高的相似度
                        time_diff = abs((modified_time - screen_result.modified_time).total_seconds())
                        time_similarity = 1.0 if time_diff < 86400 else 0.7  # 86400秒 = 1天
                    
                    # 加权计算总相似度（名称权重更高）
                    total_similarity = (name_similarity * 0.6) + (size_similarity * 0.3) + (time_similarity * 0.1)
                    
                    # 仅保留相似度较高的结果
                    if total_similarity >= 0.65:
                        reason = "文件名相似"
                        if name_similarity > 0.8 and size_similarity > 0.9:
                            reason = "可能是相同文件的副本"
                        elif name_similarity > 0.8 and time_similarity > 0.9:
                            reason = "可能是同一文件的不同版本"
                        
                        similar_files.append({
                            "refine_id": refine_result.id,
                            "similarity": round(total_similarity, 2),
                            "reason": reason,
                            "file_path": screen_result.file_path
                        })
            
            # 按相似度从高到低排序
            similar_files.sort(key=lambda x: x["similarity"], reverse=True)
            
            # 限制返回结果的数量
            return similar_files[:20] if similar_files else None
            
        except Exception as e:
            logger.error(f"查找相似文件时发生错误: {e}")
            logger.error(traceback.format_exc())
            return None

    def get_wise_folder_data(self, wise_folder_type: str, criteria: Dict[str, Any]) -> List[FileRefineResult]:
        """根据智慧文件夹类型和条件获取精炼结果。"""
        # 此方法将用于API层，根据 refine_define.md 中的定义查询 FileRefineResult 表
        # 例如: wise_folder_type="project", criteria={"project_id": 1}
        # wise_folder_type="file_category", criteria={"category_name": "document"}
        # wise_folder_type="filename_pattern", criteria={"tag": "草稿文件"}
        # ...等等
        # 这个方法需要更详细的实现，根据传入的类型和条件构建SQLModel查询
        logger.info(f"获取智慧文件夹数据: 类型='{wise_folder_type}', 条件={criteria}")
        
        query = select(FileRefineResult)

        if wise_folder_type == "project":
            project_id = criteria.get("project_id")
            if project_id:
                query = query.where(FileRefineResult.project_id == project_id)
            else:
                project_name = criteria.get("project_name")
                if project_name:
                    # 需要先通过 project_name 查到 project_id
                    project_obj = self.session.exec(select(Project).where(Project.name == project_name)).first()
                    if project_obj:
                        query = query.where(FileRefineResult.project_id == project_obj.id)
                    else:
                        return [] # 未找到项目
                else:
                    return [] # 无效的项目查询条件
        
        elif wise_folder_type == "file_category":
            # 假设 FileRefineResult.extra_metadata 中存储了 category_id 或 category_name
            # 或者需要 join FileScreeningResult 再 join FileCategory
            category_name = criteria.get("category_name")
            if category_name:
                # This might require a join if category_name is not directly in FileRefineResult
                # For now, assuming 'category_from_screening' (which is an ID) is in extra_metadata
                # And we need to map category_name to category_id first.
                category_obj = self.session.exec(select(FileCategory).where(FileCategory.name == category_name)).first()
                if category_obj:
                    # Assuming extra_metadata stores 'category_from_screening' as the ID
                    # This is a JSON field, so querying might be complex or slow.
                    # A better approach would be to have a direct category_id field in FileRefineResult if this is a common query.
                    # For demonstration, let's assume we can filter by a feature or metadata field.
                    # query = query.where(FileRefineResult.extra_metadata["category_from_screening"].astext == str(category_obj.id)) # Example for JSON
                    # A more robust way if category_id was directly on FileRefineResult or via a join:
                    query = query.join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)\
                               .where(FileScreeningResult.category_id == category_obj.id)
                else:
                    return [] # Category not found

        elif wise_folder_type == "filename_pattern_tag": # Based on refine_define.md
            tag = criteria.get("tag")
            if tag:
                # This implies that the 'tag' from FileFilterRule (applied during screening)
                # is stored in FileScreeningResult.tags, and potentially copied to FileRefineResult.features or extra_metadata
                # Example: features['derived_tags'] contains the tag
                # This requires JSON array contains operation
                # query = query.where(FileRefineResult.features['derived_tags'].contains([tag])) # SQLAlchemy specific for JSON
                # Or if tags are in screening_result.tags
                query = query.join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)\
                               .where(FileScreeningResult.tags.contains([tag])) # Assuming tags is a JSON array
            else:
                return []

        # Add more conditions based on refine_define.md
        # e.g., 按文件元数据 (modified_time, created_time, file_size, extension)
        elif wise_folder_type == "file_metadata":
            if "extension" in criteria:
                # Assuming screening_result.extension is copied to refine_result.extra_metadata['extension']
                ext = criteria["extension"]
                # query = query.where(FileRefineResult.extra_metadata['extension'].astext == ext)
                # Or join with screening result
                query = query.join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)\
                               .where(FileScreeningResult.extension == ext)
            if "min_size_kb" in criteria:
                min_size = criteria["min_size_kb"] * 1024
                query = query.join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)\
                               .where(FileScreeningResult.file_size >= min_size)
            if "max_size_kb" in criteria:
                max_size = criteria["max_size_kb"] * 1024
                query = query.join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)\
                               .where(FileScreeningResult.file_size <= max_size)
            if "modified_after" in criteria: # Expects datetime object or ISO string
                mod_after = criteria["modified_after"]
                if isinstance(mod_after, str):
                    mod_after = datetime.fromisoformat(mod_after)
                query = query.join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)\
                               .where(FileScreeningResult.modified_time >= mod_after)
            # Add created_time, etc.

        elif wise_folder_type == "processing_status":
            status_val = criteria.get("status")
            if status_val and hasattr(FileRefineStatus, status_val.upper()):
                query = query.where(FileRefineResult.status == FileRefineStatus[status_val.upper()].value)
            else:
                return []
        
        # ... other wise folder types

        results = self.session.exec(query.order_by(FileRefineResult.file_path)).all()
        return results

    def get_wise_folders_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        """获取智慧文件夹列表，按任务聚合。
        
        Args:
            task_id: 相关任务ID，如果为"all"则返回所有智慧文件夹
            
        Returns:
            智慧文件夹列表，每个文件夹包含类型、名称、文件数量等信息
        """
        task_condition = True  # 默认不限制task_id
        
        if task_id != "all":
            try:
                task_id = int(task_id)
                task_condition = FileRefineResult.task_id == task_id
            except (ValueError, TypeError):
                logger.error(f"无效的任务ID: {task_id}，将返回所有智慧文件夹")
                # 如果无法转换为整数，我们将返回所有智慧文件夹
            
        wise_folders = []
        
        # 1. 按项目获取文件夹
        projects = self.session.exec(
            select(Project)
            .join(FileRefineResult, FileRefineResult.project_id == Project.id)
            .where(task_condition)
            .distinct()
        ).all()
        
        for project in projects:
            # 计算该项目中文件数量
            file_count = len(self.session.exec(
                select(FileRefineResult)
                .where(FileRefineResult.project_id == project.id, task_condition)
            ).all())
            
            if file_count > 0:
                wise_folders.append({
                    "type": "project",
                    "id": project.id,
                    "name": project.name,
                    "description": project.description or f"项目: {project.name}",
                    "file_count": file_count,
                    "criteria": {"project_id": project.id}
                })
        
        # 2. 按文件分类获取文件夹
        categories = self.session.exec(
            select(FileCategory)
            .join(FileScreeningResult, FileScreeningResult.category_id == FileCategory.id)
            .join(FileRefineResult, FileRefineResult.screening_id == FileScreeningResult.id)
            .where(task_condition)
            .distinct()
        ).all()
        
        for category in categories:
            # 计算该分类中文件数量
            file_count = len(self.session.exec(
                select(FileRefineResult)
                .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
                .where(FileScreeningResult.category_id == category.id, task_condition)
            ).all())
            
            if file_count > 0:
                wise_folders.append({
                    "type": "category",
                    "id": category.id,
                    "name": category.name,
                    "description": category.description or f"文件分类: {category.name}",
                    "file_count": file_count,
                    "criteria": {"category_id": category.id}
                })
        
        # 3. 按文件标签获取文件夹
        if task_id == "all":
            # 如果是获取所有智慧文件夹，使用不带task_id条件的SQL
            tags_query = """
            WITH file_tags AS (
                SELECT fr.id, json_each.value as tag
                FROM t_file_refine_results fr
                JOIN t_file_screening_results fs ON fr.screening_id = fs.id
                JOIN json_each(fs.tags) ON TRUE
            )
            SELECT tag, COUNT(id) as file_count
            FROM file_tags
            GROUP BY tag
            HAVING COUNT(id) > 0
            """
            result = self.session.exec(text(tags_query)).all()
        else:
            # 使用带task_id条件的原始SQL
            tags_query = """
            WITH file_tags AS (
                SELECT fr.id, json_each.value as tag
                FROM t_file_refine_results fr
                JOIN t_file_screening_results fs ON fr.screening_id = fs.id
                JOIN json_each(fs.tags) ON TRUE
                WHERE fr.task_id = :task_id
            )
            SELECT tag, COUNT(id) as file_count
            FROM file_tags
            GROUP BY tag
            HAVING COUNT(id) > 0
            """
            result = self.session.exec(text(tags_query), params={"task_id": task_id}).all()
        
        for row in result:
            tag = row[0]
            file_count = row[1]
            
            wise_folders.append({
                "type": "tag",
                "id": None,
                "name": tag,
                "description": f"标签: {tag}",
                "file_count": file_count,
                "criteria": {"tag": tag}
            })
        
        # 4. 按时间段获取文件夹
        # 今天修改的文件
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_files_count = len(self.session.exec(
            select(FileRefineResult)
            .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
            .where(
                FileScreeningResult.modified_time >= today,
                task_condition
            )
        ).all())
        
        if today_files_count > 0:
            wise_folders.append({
                "type": "time",
                "id": None,
                "name": "今天修改的文件",
                "description": "今天修改过的所有文件",
                "file_count": today_files_count,
                "criteria": {"time_period": "today"}
            })
        
        # 本周修改的文件
        week_start = today - timedelta(days=today.weekday())
        week_files_count = len(self.session.exec(
            select(FileRefineResult)
            .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
            .where(
                FileScreeningResult.modified_time >= week_start,
                task_condition
            )
        ).all())
        
        if week_files_count > today_files_count:  # 只有当比"今天"多时才添加
            wise_folders.append({
                "type": "time",
                "id": None,
                "name": "本周修改的文件",
                "description": "本周修改过的所有文件",
                "file_count": week_files_count,
                "criteria": {"time_period": "this_week"}
            })
        
        # 按文件大小分组
        large_files_count = len(self.session.exec(
            select(FileRefineResult)
            .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
            .where(
                FileScreeningResult.file_size >= 10 * 1024 * 1024,  # 10MB
                task_condition
            )
        ).all())
        
        if large_files_count > 0:
            wise_folders.append({
                "type": "file_size",
                "id": None,
                "name": "大文件 (>10MB)",
                "description": "大于10MB的文件",
                "file_count": large_files_count,
                "criteria": {"min_size_mb": 10}
            })
        
        # 排序文件夹：项目 > 分类 > 标签 > 时间 > 大小
        type_order = {"project": 1, "category": 2, "tag": 3, "time": 4, "file_size": 5}
        wise_folders.sort(key=lambda f: (type_order.get(f["type"], 99), -f["file_count"]))
        
        return wise_folders
        
    def get_files_by_project(self, task_id: str, project_id: Any) -> List[Dict[str, Any]]:
        """获取项目中的文件列表
        
        Args:
            task_id: 任务ID
            project_id: 项目ID
            
        Returns:
            文件列表
        """
        try:
            task_id = int(task_id)
            project_id = int(project_id)
        except (ValueError, TypeError):
            logger.error(f"无效的任务ID: {task_id} 或项目ID: {project_id}")
            return []
            
        # 查询项目中的文件
        refine_results = self.session.exec(
            select(FileRefineResult, FileScreeningResult)
            .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
            .where(
                FileRefineResult.project_id == project_id,
                FileRefineResult.task_id == task_id
            )
            .order_by(FileScreeningResult.file_name)
        ).all()
        
        files = []
        for refine_result, screen_result in refine_results:
            files.append({
                "id": refine_result.id,
                "file_path": screen_result.file_path,
                "file_name": screen_result.file_name,
                "extension": screen_result.extension,
                "file_size": screen_result.file_size,
                "modified_time": screen_result.modified_time.isoformat() if screen_result.modified_time else None,
                "category_id": screen_result.category_id,
                "tags": screen_result.tags or []
            })
            
        return files
        
    def get_files_by_category(self, task_id: str, category_id: Any) -> List[Dict[str, Any]]:
        """获取分类中的文件列表
        
        Args:
            task_id: 任务ID
            category_id: 分类ID
            
        Returns:
            文件列表
        """
        try:
            task_id = int(task_id)
            category_id = int(category_id)
        except (ValueError, TypeError):
            logger.error(f"无效的任务ID: {task_id} 或分类ID: {category_id}")
            return []
            
        # 查询分类中的文件
        refine_results = self.session.exec(
            select(FileRefineResult, FileScreeningResult)
            .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
            .where(
                FileScreeningResult.category_id == category_id,
                FileRefineResult.task_id == task_id
            )
            .order_by(FileScreeningResult.file_name)
        ).all()
        
        files = []
        for refine_result, screen_result in refine_results:
            files.append({
                "id": refine_result.id,
                "file_path": screen_result.file_path,
                "file_name": screen_result.file_name,
                "extension": screen_result.extension,
                "file_size": screen_result.file_size,
                "modified_time": screen_result.modified_time.isoformat() if screen_result.modified_time else None,
                "category_id": screen_result.category_id,
                "tags": screen_result.tags or []
            })
            
        return files
        
    def get_files_by_tag(self, task_id: str, tag: str) -> List[Dict[str, Any]]:
        """获取带有特定标签的文件列表
        
        Args:
            task_id: 任务ID
            tag: 标签名
            
        Returns:
            文件列表
        """
        try:
            task_id = int(task_id)
        except (ValueError, TypeError):
            logger.error(f"无效的任务ID: {task_id}")
            return []
            
        if not tag:
            logger.error("标签名不能为空")
            return []
            
        # SQLite JSON 查询，检查标签是否包含在 tags 数组中
        # 需要使用 json_each 函数和 JOIN 来实现数组包含查询
        query = """
        SELECT fr.id, fs.file_path, fs.file_name, fs.extension, 
               fs.file_size, fs.modified_time, fs.category_id, fs.tags
        FROM t_file_refine_results fr
        JOIN t_file_screening_results fs ON fr.screening_id = fs.id
        JOIN json_each(fs.tags) ON json_each.value = :tag
        WHERE fr.task_id = :task_id
        ORDER BY fs.file_name
        """
        
        result = self.session.execute(text(query), {"task_id": task_id, "tag": tag})
        
        files = []
        for row in result:
            # 处理modified_time可能是字符串的情况
            modified_time = row.modified_time
            if modified_time:
                if isinstance(modified_time, str):
                    # 如果已经是字符串，直接使用
                    modified_time_str = modified_time
                else:
                    # 否则调用isoformat()
                    modified_time_str = modified_time.isoformat()
            else:
                modified_time_str = None
                
            files.append({
                "id": row.id,
                "file_path": row.file_path,
                "file_name": row.file_name,
                "extension": row.extension,
                "file_size": row.file_size,
                "modified_time": modified_time_str,
                "category_id": row.category_id,
                "tags": json.loads(row.tags) if row.tags else []
            })
            
        return files

    def get_files_by_time_period(self, task_id: str, time_period: str) -> List[Dict[str, Any]]:
        """获取特定时间段内修改的文件列表
        
        Args:
            task_id: 任务ID
            time_period: 时间段 ("today", "this_week", "this_month", "this_year")
            
        Returns:
            文件列表
        """
        try:
            task_id = int(task_id)
        except (ValueError, TypeError):
            logger.error(f"无效的任务ID: {task_id}")
            return []
            
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 设置时间段起始时间
        if time_period == "today":
            start_time = today
        elif time_period == "this_week":
            start_time = today - timedelta(days=today.weekday())
        elif time_period == "this_month":
            start_time = today.replace(day=1)
        elif time_period == "this_year":
            start_time = today.replace(month=1, day=1)
        else:
            logger.error(f"不支持的时间段: {time_period}")
            return []
        
        # 查询时间段内修改的文件
        refine_results = self.session.exec(
            select(FileRefineResult, FileScreeningResult)
            .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
            .where(
                FileScreeningResult.modified_time >= start_time,
                FileRefineResult.task_id == task_id
            )
            .order_by(FileScreeningResult.modified_time.desc())
        ).all()
        
        files = []
        for refine_result, screen_result in refine_results:
            files.append({
                "id": refine_result.id,
                "file_path": screen_result.file_path,
                "file_name": screen_result.file_name,
                "extension": screen_result.extension,
                "file_size": screen_result.file_size,
                "modified_time": screen_result.modified_time.isoformat() if screen_result.modified_time else None,
                "category_id": screen_result.category_id,
                "tags": screen_result.tags or []
            })
            
        return files

    def get_files_by_entity(self, task_id: str, entity: str) -> List[Dict[str, Any]]:
        """获取包含特定命名实体的文件列表
        
        此方法目前是一个存根，因为命名实体识别需要内容分析
        
        Args:
            task_id: 任务ID
            entity: 实体名称
            
        Returns:
            文件列表
        """
        logger.warning("命名实体识别功能尚未实现，此方法将返回空列表")
        return []
        
    def get_files_by_topic(self, task_id: str, topic: str) -> List[Dict[str, Any]]:
        """获取与特定主题相关的文件列表
        
        此方法目前是一个存根，因为主题识别需要内容分析
        
        Args:
            task_id: 任务ID
            topic: 主题名称
            
        Returns:
            文件列表
        """
        logger.warning("主题识别功能尚未实现，此方法将返回空列表")
        return []

    def get_all_wise_folder_categories(self) -> List[Dict[str, Any]]:
        """获取所有智慧文件夹分类。
        
        Returns:
            分类列表，每个分类包含类型、名称、文件夹数量等信息
        """
        categories = [
            {
                "type": "project",
                "name": "项目",
                "icon": "database",
                "description": "按项目组织的文件"
            },
            {
                "type": "category",
                "name": "文件类型",
                "icon": "file",
                "description": "按文件类型组织的文件"
            },
            {
                "type": "tag",
                "name": "标签",
                "icon": "tag",
                "description": "按标签组织的文件"
            },
            {
                "type": "time",
                "name": "时间",
                "icon": "calendar",
                "description": "按时间组织的文件"
            },
            {
                "type": "other",
                "name": "其他",
                "icon": "folder",
                "description": "其他组织方式"
            }
        ]
        
        # 统计每个分类下的文件夹数量
        for category in categories:
            if category["type"] == "project":
                # 统计项目数量
                count = self.session.exec(
                    select(func.count(Project.id.distinct()))
                    .select_from(Project)
                    .join(FileRefineResult, FileRefineResult.project_id == Project.id)
                ).first()
                # 直接使用count，它已经是一个整数
                category["folder_count"] = count
            elif category["type"] == "category":
                # 统计文件分类数量
                count = self.session.exec(
                    select(func.count(FileCategory.id.distinct()))
                    .select_from(FileCategory)
                    .join(FileScreeningResult, FileScreeningResult.category_id == FileCategory.id)
                    .join(FileRefineResult, FileRefineResult.screening_id == FileScreeningResult.id)
                ).first()
                # 直接使用count，它已经是一个整数
                category["folder_count"] = count
            elif category["type"] == "tag":
                # 统计标签数量
                tags_query = """
                WITH file_tags AS (
                    SELECT fr.id, json_each.value as tag
                    FROM t_file_refine_results fr
                    JOIN t_file_screening_results fs ON fr.screening_id = fs.id
                    JOIN json_each(fs.tags) ON TRUE
                )
                SELECT COUNT(DISTINCT tag) as tag_count
                FROM file_tags
                """
                result = self.session.exec(text(tags_query)).first()
                category["folder_count"] = result[0] if result else 0
            elif category["type"] == "time":
                # 时间分类是固定的几个
                category["folder_count"] = 3  # 今天、本周、本月
            elif category["type"] == "other":
                # 其他分类（如文件大小等）
                category["folder_count"] = 1  # 大文件
        
        return categories

    def get_folders_by_category(self, category_type: str) -> List[Dict[str, Any]]:
        """根据分类类型获取智慧文件夹列表。
        
        Args:
            category_type: 分类类型，如 project, category, tag, time, other
            
        Returns:
            智慧文件夹列表，每个文件夹包含类型、名称、文件数量等信息
        """
        folders = []
        
        if category_type == "project":
            # 获取所有项目
            projects = self.session.exec(
                select(Project)
                .join(FileRefineResult, FileRefineResult.project_id == Project.id)
                .distinct()
            ).all()
            
            for project in projects:
                # 计算该项目中文件数量
                file_count = self.session.exec(
                    select(func.count())
                    .select_from(FileRefineResult)
                    .where(FileRefineResult.project_id == project.id)
                ).first()
                
                if file_count > 0:
                    folders.append({
                        "id": f"project_{project.id}",
                        "type": "project",
                        "name": project.name,
                        "description": project.description or f"项目: {project.name}",
                        "file_count": file_count,
                        "criteria": {"project_id": project.id}
                    })
        
        elif category_type == "category":
            # 获取所有文件分类
            categories = self.session.exec(
                select(FileCategory)
                .join(FileScreeningResult, FileScreeningResult.category_id == FileCategory.id)
                .join(FileRefineResult, FileRefineResult.screening_id == FileScreeningResult.id)
                .distinct()
            ).all()
            
            for category in categories:
                # 计算该分类中文件数量
                file_count = self.session.exec(
                    select(func.count())
                    .select_from(FileRefineResult)
                    .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
                    .where(FileScreeningResult.category_id == category.id)
                ).first()
                
                if file_count > 0:
                    folders.append({
                        "id": f"category_{category.id}",
                        "type": "category",
                        "name": category.name,
                        "description": category.description or f"文件分类: {category.name}",
                        "file_count": file_count,
                        "criteria": {"category_id": category.id}
                    })
        
        elif category_type == "tag":
            # 获取所有标签
            tags_query = """
            WITH file_tags AS (
                SELECT fr.id, json_each.value as tag
                FROM t_file_refine_results fr
                JOIN t_file_screening_results fs ON fr.screening_id = fs.id
                JOIN json_each(fs.tags) ON TRUE
            )
            SELECT tag, COUNT(id) as file_count
            FROM file_tags
            GROUP BY tag
            HAVING COUNT(id) > 0
            """
            
            result = self.session.exec(text(tags_query)).all()
            for row in result:
                tag = row[0]
                file_count = row[1]
                
                folders.append({
                    "id": f"tag_{tag}",
                    "type": "tag",
                    "name": tag,
                    "description": f"标签: {tag}",
                    "file_count": file_count,
                    "criteria": {"tag": tag}
                })
        
        elif category_type == "time":
            # 时间分类是固定的几个
            # 今天修改的文件
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_files_count = self.session.exec(
                select(func.count())
                .select_from(FileRefineResult)
                .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
                .where(FileScreeningResult.modified_time >= today)
            ).first()
            
            if today_files_count > 0:
                folders.append({
                    "id": "time_today",
                    "type": "time",
                    "name": "今天修改的文件",
                    "description": "今天修改过的所有文件",
                    "file_count": today_files_count,
                    "criteria": {"time_period": "today"}
                })
            
            # 本周修改的文件
            week_start = today - timedelta(days=today.weekday())
            week_files_count = self.session.exec(
                select(func.count())
                .select_from(FileRefineResult)
                .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
                .where(FileScreeningResult.modified_time >= week_start)
            ).first()
            
            if week_files_count > today_files_count:  # 只有当比"今天"多时才添加
                folders.append({
                    "id": "time_this_week",
                    "type": "time",
                    "name": "本周修改的文件",
                    "description": "本周修改过的所有文件",
                    "file_count": week_files_count,
                    "criteria": {"time_period": "this_week"}
                })
            
            # 本月修改的文件
            month_start = today.replace(day=1)
            month_files_count = self.session.exec(
                select(func.count())
                .select_from(FileRefineResult)
                .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
                .where(FileScreeningResult.modified_time >= month_start)
            ).first()
            
            if month_files_count > week_files_count:  # 只有当比"本周"多时才添加
                folders.append({
                    "id": "time_this_month",
                    "type": "time",
                    "name": "本月修改的文件",
                    "description": "本月修改过的所有文件",
                    "file_count": month_files_count,
                    "criteria": {"time_period": "this_month"}
                })
        
        elif category_type == "other":
            # 其他分类（如文件大小等）
            # 大文件
            large_files_count = self.session.exec(
                select(func.count())
                .select_from(FileRefineResult)
                .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
                .where(FileScreeningResult.file_size >= 10 * 1024 * 1024)  # 10MB
            ).first()
            
            if large_files_count > 0:
                folders.append({
                    "id": "size_large",
                    "type": "file_size",
                    "name": "大文件 (>10MB)",
                    "description": "大于10MB的文件",
                    "file_count": large_files_count,
                    "criteria": {"min_size_mb": 10}
                })
        
        return folders

    def get_files_by_folder(self, folder_type: str, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取智慧文件夹中的文件列表。
        
        Args:
            folder_type: 文件夹类型，如 project, category, tag, time
            criteria: 查询条件
            
        Returns:
            文件列表
        """
        files = []
        
        # 辅助函数处理modified_time
        def format_modified_time(modified_time):
            if modified_time:
                if isinstance(modified_time, str):
                    return modified_time
                else:
                    return modified_time.isoformat()
            return None
        
        if folder_type == "project":
            project_id = criteria.get("project_id")
            if project_id:
                # 查询项目中的文件
                results = self.session.exec(
                    select(FileRefineResult, FileScreeningResult)
                    .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
                    .where(FileRefineResult.project_id == project_id)
                    .order_by(FileScreeningResult.file_name)
                ).all()
                
                for refine_result, screen_result in results:
                    files.append({
                        "id": refine_result.id,
                        "file_path": screen_result.file_path,
                        "file_name": screen_result.file_name,
                        "extension": screen_result.extension,
                        "file_size": screen_result.file_size,
                        "modified_time": format_modified_time(screen_result.modified_time),
                        "category_id": screen_result.category_id,
                        "tags": screen_result.tags or []
                    })
        
        elif folder_type == "category":
            category_id = criteria.get("category_id")
            if category_id:
                # 查询分类中的文件
                results = self.session.exec(
                    select(FileRefineResult, FileScreeningResult)
                    .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
                    .where(FileScreeningResult.category_id == category_id)
                    .order_by(FileScreeningResult.file_name)
                ).all()
                
                for refine_result, screen_result in results:
                    files.append({
                        "id": refine_result.id,
                        "file_path": screen_result.file_path,
                        "file_name": screen_result.file_name,
                        "extension": screen_result.extension,
                        "file_size": screen_result.file_size,
                        "modified_time": format_modified_time(screen_result.modified_time),
                        "category_id": screen_result.category_id,
                        "tags": screen_result.tags or []
                    })
        
        elif folder_type == "tag":
            tag = criteria.get("tag")
            if tag:
                # 查询带有特定标签的文件
                query = """
                SELECT fr.id, fs.file_path, fs.file_name, fs.extension, 
                       fs.file_size, fs.modified_time, fs.category_id, fs.tags
                FROM t_file_refine_results fr
                JOIN t_file_screening_results fs ON fr.screening_id = fs.id
                JOIN json_each(fs.tags) ON json_each.value = :tag
                ORDER BY fs.file_name
                """
                
                result = self.session.execute(text(query), {"tag": tag})
                
                for row in result:
                    files.append({
                        "id": row.id,
                        "file_path": row.file_path,
                        "file_name": row.file_name,
                        "extension": row.extension,
                        "file_size": row.file_size,
                        "modified_time": format_modified_time(row.modified_time),
                        "category_id": row.category_id,
                        "tags": json.loads(row.tags) if row.tags else []
                    })
        
        elif folder_type == "time":
            time_period = criteria.get("time_period")
            if time_period:
                today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                
                # 设置时间段起始时间
                if time_period == "today":
                    start_time = today
                elif time_period == "this_week":
                    start_time = today - timedelta(days=today.weekday())
                elif time_period == "this_month":
                    start_time = today.replace(day=1)
                elif time_period == "this_year":
                    start_time = today.replace(month=1, day=1)
                else:
                    return []
                
                # 查询时间段内修改的文件
                results = self.session.exec(
                    select(FileRefineResult, FileScreeningResult)
                    .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
                    .where(FileScreeningResult.modified_time >= start_time)
                    .order_by(FileScreeningResult.modified_time.desc())
                ).all()
                
                for refine_result, screen_result in results:
                    files.append({
                        "id": refine_result.id,
                        "file_path": screen_result.file_path,
                        "file_name": screen_result.file_name,
                        "extension": screen_result.extension,
                        "file_size": screen_result.file_size,
                        "modified_time": format_modified_time(screen_result.modified_time),
                        "category_id": screen_result.category_id,
                        "tags": screen_result.tags or []
                    })
        
        elif folder_type == "file_size":
            min_size_mb = criteria.get("min_size_mb")
            if min_size_mb:
                # 查询大于特定大小的文件
                results = self.session.exec(
                    select(FileRefineResult, FileScreeningResult)
                    .join(FileScreeningResult, FileRefineResult.screening_id == FileScreeningResult.id)
                    .where(FileScreeningResult.file_size >= min_size_mb * 1024 * 1024)
                    .order_by(FileScreeningResult.file_size.desc())
                ).all()
                
                for refine_result, screen_result in results:
                    files.append({
                        "id": refine_result.id,
                        "file_path": screen_result.file_path,
                        "file_name": screen_result.file_name,
                        "extension": screen_result.extension,
                        "file_size": screen_result.file_size,
                        "modified_time": format_modified_time(screen_result.modified_time),
                        "category_id": screen_result.category_id,
                        "tags": screen_result.tags or []
                    })
        
        return files


if __name__ == "__main__":
    # Example Usage (requires a database setup and some data)
    from sqlmodel import create_engine
    import pathlib

    # Setup a dummy in-memory database for testing
    engine = create_engine("sqlite:///:memory:")
    from db_mgr import SQLModel, FileCategory, FileFilterRule # Import SQLModel for create_all
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # 1. Setup some prerequisite data (Categories, Rules)
        doc_category = FileCategory(name="document", extensions=[".txt", ".md", ".pdf"])
        code_category = FileCategory(name="code", extensions=[".py", ".js"])
        session.add_all([doc_category, code_category])
        session.commit()

        # Add a project recognition rule for .git folders
        git_rule = ProjectRecognitionRule(
            name="Git Repo Rule", 
            description="Identifies Git repositories by .git folder",
            rule_type="file_exists_in_parent_folder", 
            pattern=".git", 
            priority="high",  # 使用枚举值
            indicators={"name_template": "Git Project: {folder_name}"},  # 在 indicators 字段中添加名称模板
            enabled=True,  # ProjectRecognitionRule 模型中使用 enabled 而不是 is_active
            is_system=True
        )
        session.add(git_rule)
        session.commit()

        # 2. Create a dummy FileScreeningResult
        # Create dummy project structure for testing project identification
        # /tmp/my_git_project/.git
        # /tmp/my_git_project/file1.txt
        # /tmp/another_folder/file2.py
        
        # Ensure dummy paths exist for the project rule to work if it checks os.path.exists
        # For this test, we'll mock pathlib.Path.exists if needed, or ensure the logic can run without actual file system access
        # For simplicity, let's assume _identify_project can be tested by just passing paths
        # Or, we can create the dummy structure if the test environment allows it.
        
        # Mocking pathlib.Path.exists for the test
        original_path_exists = pathlib.Path.exists
        def mock_exists(path_obj):
            if str(path_obj).endswith("/my_git_project/.git"):
                return True
            return original_path_exists(path_obj) # fallback to real exists for other paths
        
        pathlib.Path.exists = mock_exists

        screening_result1 = FileScreeningResult(
            file_path="/tmp/my_git_project/file1.txt",
            file_name="file1.txt",
            extension=".txt",
            file_size=1024,
            category_id=doc_category.id,
            tags=["draft"],
            created_time=datetime.now() - timedelta(days=1),
            modified_time=datetime.now(),
            # ... other fields
        )
        screening_result2 = FileScreeningResult(
            file_path="/tmp/another_folder/file2.py",
            file_name="file2.py",
            extension=".py",
            file_size=2048,
            category_id=code_category.id,
            created_time=datetime.now() - timedelta(days=2),
            modified_time=datetime.now() - timedelta(hours=5),
        )
        session.add_all([screening_result1, screening_result2])
        session.commit()
        session.refresh(screening_result1)
        session.refresh(screening_result2)

        # 3. Initialize RefineManager and process
        refine_mgr = RefineManager(session)
        
        print("--- Processing screening_result1 (in git project) ---")
        refined1 = refine_mgr.process_screening_result(screening_result1.id)
        if refined1:
            print(f"Refined1 ID: {refined1.id}, Status: {refined1.status}, Project ID: {refined1.project_id}")
            if refined1.project_id:
                project1 = session.get(Project, refined1.project_id)
                print(f"Project Name: {project1.name if project1 else 'Not Found'}")
            print(f"Features: {refined1.features}")
            print(f"Extra Metadata: {refined1.extra_metadata}")

        print("--- Processing screening_result2 (no project) ---")
        refined2 = refine_mgr.process_screening_result(screening_result2.id)
        if refined2:
            print(f"Refined2 ID: {refined2.id}, Status: {refined2.status}, Project ID: {refined2.project_id}")
            print(f"Features: {refined2.features}")
            print(f"Extra Metadata: {refined2.extra_metadata}")

        # 4. Test get_wise_folder_data
        print("--- Testing get_wise_folder_data --- ")
        if refined1 and refined1.project_id:
            project_files = refine_mgr.get_wise_folder_data("project", {"project_id": refined1.project_id})
            print(f"Files in Project ID {refined1.project_id}: {len(project_files)}")
            for f in project_files: print(f"  - {f.file_path}")

        text_files = refine_mgr.get_wise_folder_data("file_metadata", {"extension": ".txt"})
        print(f"Text files (.txt): {len(text_files)}")
        for f in text_files: print(f"  - {f.file_path}")

        draft_files = refine_mgr.get_wise_folder_data("filename_pattern_tag", {"tag": "draft"})
        print(f"Draft files (tag 'draft'): {len(draft_files)}")
        for f in draft_files: print(f"  - {f.file_path}")
        
        # Restore original pathlib.Path.exists
        pathlib.Path.exists = original_path_exists

        # Example of how to get files by category name
        doc_files = refine_mgr.get_wise_folder_data("file_category", {"category_name": "document"})
        print(f"Document category files: {len(doc_files)}")
        for f in doc_files: print(f"  - {f.file_path}")

        # Example of how to get files by processing status
        completed_files = refine_mgr.get_wise_folder_data("processing_status", {"status": "complete"})
        print(f"Completed refined files: {len(completed_files)}")
        for f in completed_files: print(f"  - {f.file_path}")

    print("RefineManager example run complete. Check logs for details.")