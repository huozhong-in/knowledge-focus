from typing import List, Dict, Any, Optional, Tuple, Union
from sqlmodel import Session, select, delete, update
from db_mgr import FileScreeningResult, FileScreenResult
from datetime import datetime, timedelta
import logging
import os
import time

logger = logging.getLogger(__name__)

class ScreeningManager:
    """文件粗筛结果管理类，提供增删改查方法"""
    
    def __init__(self, session: Session): # No change to __init__
        self.session = session
    
    def add_screening_result(self, data: Dict[str, Any], commit_session: bool = True) -> Optional[FileScreeningResult]:
        """添加一条文件粗筛结果
        
        Args:
            data: 包含文件元数据和初步分类信息的字典
            commit_session: 是否在此方法内提交会话 (用于批量操作时设为False)
            
        Returns:
            添加成功返回记录对象，失败返回None
        """
        try:
            # 检查是否已存在相同路径和哈希值的记录
            file_path = data.get("file_path", "")
            file_hash = data.get("file_hash")
            
            existing_record = self.get_by_path_and_hash(file_path, file_hash)
            if (existing_record):
                # 如果已存在记录，则更新现有记录，同时确保状态为pending
                update_data = data.copy()
                update_data["status"] = FileScreenResult.PENDING.value  # 确保状态重置为pending
                logger.info(f"找到现有记录 ID:{existing_record.id}，更新状态为pending并更新元数据")
                return self.update_screening_result(existing_record.id, update_data)
            
            # 将字典转换为FileScreeningResult对象
            result = FileScreeningResult(
                file_path=data.get("file_path", ""),
                file_name=data.get("file_name", ""),
                file_size=data.get("file_size", 0),
                extension=data.get("extension"),
                file_hash=data.get("file_hash"),
                created_time=data.get("created_time"),
                modified_time=data.get("modified_time", datetime.now()),
                accessed_time=data.get("accessed_time"),
                category_id=data.get("category_id"),
                matched_rules=data.get("matched_rules"), # Ensure this matches the key from Rust if it's 'metadata'
                extra_metadata=data.get("extra_metadata", data.get("metadata")), # Handle potential old key 'metadata'
                tags=data.get("tags"),
                status=data.get("status", FileScreenResult.PENDING.value),
                task_id=data.get("task_id")
            )
            
            # 添加到数据库
            self.session.add(result)
            if commit_session: # Only commit if flag is true
                self.session.commit()
                self.session.refresh(result)
            
            logger.info(f"添加文件粗筛结果成功: {result.file_path}")
            return result
            
        except Exception as e:
            if commit_session: # Only rollback if we were supposed to commit
                self.session.rollback()
            logger.error(f"添加文件粗筛结果失败: {str(e)}")
            return None
    
    def add_batch_screening_results(self, results_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量添加文件粗筛结果
        
        Args:
            results_data: 包含多个文件元数据和初步分类信息的字典列表
            
        Returns:
            包含成功和失败计数的结果字典
        """
        success_count = 0
        failed_count = 0
        errors = []
        added_results_for_refresh = [] # Store results to refresh after commit
        
        for data_item in results_data: # Renamed 'data' to 'data_item' to avoid conflict
            try:
                # Call add_screening_result with commit_session=False
                result = self.add_screening_result(data_item, commit_session=False)
                if result:
                    success_count += 1
                    added_results_for_refresh.append(result) # Add to list for refresh
                else:
                    failed_count += 1
                    errors.append(f"添加文件失败: {data_item.get('file_path', 'unknown path')}")
            except Exception as e:
                failed_count += 1
                errors.append(f"处理文件出错: {data_item.get('file_path', 'unknown path')} - {str(e)}")
        
        if success_count > 0:
            try:
                self.session.commit() # Commit once after all additions
                for res in added_results_for_refresh:
                    self.session.refresh(res) # Refresh all added objects
                logger.info(f"批量添加 {success_count} 条记录成功提交。")
            except Exception as e:
                self.session.rollback()
                logger.error(f"批量提交失败: {str(e)}")
                # Mark all as failed if commit fails
                failed_count += success_count
                success_count = 0
                errors.append(f"批量提交数据库失败: {str(e)}")
        elif failed_count > 0 : # If only failures, still good to rollback any session changes
             self.session.rollback()
        
        return {
            "success": success_count,
            "failed": failed_count,
            "errors": errors if errors else None
        }

    def get_by_path(self, file_path: str) -> Optional[FileScreeningResult]:
        """根据文件路径获取粗筛结果"""
        statement = select(FileScreeningResult).where(FileScreeningResult.file_path == file_path)
        return self.session.exec(statement).first()
    
    def get_by_path_and_hash(self, file_path: str, file_hash: str = None) -> Optional[FileScreeningResult]:
        """根据文件路径和哈希值获取粗筛结果
        
        如果同时提供路径和哈希值，则进行更严格的匹配；
        如果只提供路径，则退化为仅路径匹配。
        
        Args:
            file_path: 文件路径
            file_hash: 文件哈希值（可选）
            
        Returns:
            匹配的记录或None
        """
        if not file_hash:
            return self.get_by_path(file_path)
            
        # 同时匹配路径和哈希
        statement = select(FileScreeningResult).where(
            (FileScreeningResult.file_path == file_path) & 
            (FileScreeningResult.file_hash == file_hash)
        )
        return self.session.exec(statement).first()
    
    def get_by_id(self, result_id: int) -> Optional[FileScreeningResult]:
        """根据ID获取粗筛结果"""
        return self.session.get(FileScreeningResult, result_id)
    
    def get_pending_results(self, limit: int = 100) -> List[FileScreeningResult]:
        """获取待处理的粗筛结果
        
        Args:
            limit: 返回结果的最大数量
            
        Returns:
            待处理粗筛结果列表
        """
        try:
            # 使用更优化的查询，避免排序大量数据
            statement = select(FileScreeningResult)\
                .where(FileScreeningResult.status == FileScreenResult.PENDING.value)\
                .limit(limit)
                
            results = self.session.exec(statement).all()
            if results:
                logger.info(f"获取到 {len(results)} 个待处理粗筛结果")
            return results
            
        except Exception as e:
            logger.error(f"获取待处理粗筛结果失败: {str(e)}")
            return []
    
    def get_results_by_category(self, category_id: int, limit: int = 100) -> List[FileScreeningResult]:
        """根据分类ID获取粗筛结果"""
        statement = select(FileScreeningResult)\
            .where(FileScreeningResult.category_id == category_id)\
            .order_by(FileScreeningResult.modified_time.desc())\
            .limit(limit)
        return self.session.exec(statement).all()
    
    def get_results_by_tag(self, tag: str, limit: int = 100) -> List[FileScreeningResult]:
        """根据标签获取粗筛结果（需要查询JSON数组）"""
        # 使用JSON查询，SQLite的JSON支持有限，可能需要根据具体数据库调整
        # 这里使用LIKE操作符进行简单模糊匹配
        statement = select(FileScreeningResult)\
            .where(FileScreeningResult.tags.like(f"%{tag}%"))\
            .order_by(FileScreeningResult.modified_time.desc())\
            .limit(limit)
        return self.session.exec(statement).all()
    
    def search_by_filename(self, filename_pattern: str, limit: int = 100) -> List[FileScreeningResult]:
        """根据文件名模式搜索粗筛结果"""
        statement = select(FileScreeningResult)\
            .where(FileScreeningResult.file_name.like(f"%{filename_pattern}%"))\
            .order_by(FileScreeningResult.modified_time.desc())\
            .limit(limit)
        return self.session.exec(statement).all()
        
    def get_all_results(self, limit: int = 1000) -> List[FileScreeningResult]:
        """获取所有文件粗筛结果
        
        Args:
            limit: 最大返回结果数量
            
        Returns:
            文件粗筛结果列表
        """
        try:
            statement = select(FileScreeningResult)\
                .order_by(FileScreeningResult.modified_time.desc())\
                .limit(limit)
            return self.session.exec(statement).all()
        except Exception as e:
            logger.error(f"获取所有文件粗筛结果失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def update_screening_result(self, result_id: int, data: Dict[str, Any]) -> Optional[FileScreeningResult]:
        """更新粗筛结果
        
        Args:
            result_id: 记录ID
            data: 更新数据
            
        Returns:
            更新成功返回记录对象，失败返回None
        """
        try:
            result = self.get_by_id(result_id)
            if not result:
                logger.warning(f"更新粗筛结果失败: ID {result_id} 不存在")
                return None
            
            # 记录原始状态，用于日志记录
            original_status = result.status
            
            # 更新字段
            for key, value in data.items():
                if hasattr(result, key) and key != "id":
                    setattr(result, key, value)
            
            # 状态处理逻辑
            # 只在明确要求更新为pending状态时进行状态重置，不自动根据内容变更重置状态
            # 因为在当前阶段，精炼主要基于元数据进行，不深入分析文件内容
            if "status" in data and data["status"] == FileScreenResult.PENDING.value:
                # 明确设置为pending
                result.status = FileScreenResult.PENDING.value
                logger.info(f"文件粗筛结果状态由 {original_status} 明确重置为 {result.status}")
            
            # 如果是文件路径变更的情况（如文件重命名），需要重新进行精炼处理
            # 因为文件名包含的语义信息可能影响聚类结果
            elif result.status != FileScreenResult.PENDING.value and "file_path" in data and data["file_path"] != result.file_path:
                # 对于文件名/路径变更的情况，需要重新处理
                result.status = FileScreenResult.PENDING.value
                logger.info(f"检测到文件路径变更，将状态由 {original_status} 重置为 {result.status}")
            
            # 更新时间戳
            result.updated_at = datetime.now()
            
            self.session.add(result)
            self.session.commit()
            self.session.refresh(result)
            
            logger.info(f"更新文件粗筛结果成功: ID {result_id}")
            return result
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"更新文件粗筛结果失败: {str(e)}")
            return None
    
    def update_status(self, result_id: int, status: FileScreenResult, error_message: str = None) -> bool:
        """更新粗筛结果状态
        
        Args:
            result_id: 记录ID
            status: 新状态
            error_message: 错误信息（如果有）
            
        Returns:
            更新成功返回True，失败返回False
        """
        try:
            result = self.get_by_id(result_id)
            if not result:
                logger.warning(f"更新粗筛结果状态失败: ID {result_id} 不存在")
                return False
            
            result.status = status.value
            if error_message:
                result.error_message = error_message
                
            result.updated_at = datetime.now()
            
            self.session.add(result)
            self.session.commit()
            
            logger.info(f"更新文件粗筛结果状态成功: ID {result_id} -> {status.value}")
            return True
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"更新文件粗筛结果状态失败: {str(e)}")
            return False
    
    def bulk_update_status(self, result_ids: List[int], status: FileScreenResult) -> Dict[str, Any]:
        """批量更新粗筛结果状态
        
        Args:
            result_ids: 记录ID列表
            status: 新状态
            
        Returns:
            包含成功和失败计数的结果字典
        """
        success_count = 0
        failed_count = 0
        
        try:
            # 使用批量更新
            update_statement = update(FileScreeningResult)\
                .where(FileScreeningResult.id.in_(result_ids))\
                .values(status=status.value, updated_at=datetime.now())
                
            self.session.execute(update_statement)
            self.session.commit()
            
            success_count = len(result_ids)  # 假设全部成功
            logger.info(f"批量更新文件粗筛结果状态成功: {success_count} 条记录")
                
        except Exception as e:
            self.session.rollback()
            failed_count = len(result_ids)
            logger.error(f"批量更新文件粗筛结果状态失败: {str(e)}")
        
        return {
            "success": success_count,
            "failed": failed_count
        }
    
    def delete_screening_result(self, result_id: int) -> bool:
        """删除粗筛结果
        
        Args:
            result_id: 记录ID
            
        Returns:
            删除成功返回True，失败返回False
        """
        try:
            result = self.get_by_id(result_id)
            if not result:
                logger.warning(f"删除粗筛结果失败: ID {result_id} 不存在")
                return False
            
            self.session.delete(result)
            self.session.commit()
            
            logger.info(f"删除文件粗筛结果成功: ID {result_id}")
            return True
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"删除文件粗筛结果失败: {str(e)}")
            return False
    
    def clear_old_results(self, days: int = 30) -> int:
        """清理指定天数前的已处理记录
        
        Args:
            days: 天数，默认30天
            
        Returns:
            删除的记录数
        """
        try:
            # 计算截止时间
            cutoff_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff_date = cutoff_date.replace(day=cutoff_date.day - days)
            
            # 删除已处理且早于截止日期的记录
            delete_statement = delete(FileScreeningResult)\
                .where(FileScreeningResult.status.in_([FileScreenResult.PROCESSED.value, FileScreenResult.IGNORED.value]))\
                .where(FileScreeningResult.updated_at < cutoff_date)
                
            result = self.session.execute(delete_statement)
            self.session.commit()
            
            deleted_count = result.rowcount if hasattr(result, 'rowcount') else 0
            logger.info(f"清理旧粗筛结果成功: 删除了 {deleted_count} 条记录")
            return deleted_count
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"清理旧粗筛结果失败: {str(e)}")
            return 0

    def delete_screening_results_by_path_prefix(self, path_prefix: str) -> int:
        """删除以指定路径前缀开头的所有粗筛记录
        
        Args:
            path_prefix: 路径前缀
            
        Returns:
            删除的记录数
        """
        try:
            # 确保路径以"/"结尾，便于前缀匹配
            if not path_prefix.endswith("/"):
                path_prefix = f"{path_prefix}/"
            
            # 查询以该路径前缀开头的所有记录
            statement = delete(FileScreeningResult).where(FileScreeningResult.file_path.like(f"{path_prefix}%"))
            result = self.session.execute(statement)
            self.session.commit()
            
            deleted_count = result.rowcount if hasattr(result, 'rowcount') else 0
            logger.info(f"删除路径前缀为'{path_prefix}'的粗筛结果成功: 删除了 {deleted_count} 条记录")
            return deleted_count
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"删除路径前缀为'{path_prefix}'的粗筛结果失败: {str(e)}")
            return 0

    def find_similar_files_by_hash(self, file_hash: str, exclude_path: str = None, limit: int = 10) -> List[FileScreeningResult]:
        """根据哈希值查找可能的重复文件
        
        Args:
            file_hash: 文件哈希值
            exclude_path: 排除的文件路径（通常是查询文件自身的路径）
            limit: 最大返回结果数量
            
        Returns:
            具有相同哈希值的文件列表
        """
        try:
            if not file_hash:
                return []
                
            if exclude_path:
                # 查找具有相同哈希值但路径不同的文件
                statement = select(FileScreeningResult)\
                    .where((FileScreeningResult.file_hash == file_hash) & 
                           (FileScreeningResult.file_path != exclude_path))\
                    .order_by(FileScreeningResult.modified_time.desc())\
                    .limit(limit)
            else:
                # 查找所有具有相同哈希值的文件
                statement = select(FileScreeningResult)\
                    .where(FileScreeningResult.file_hash == file_hash)\
                    .order_by(FileScreeningResult.modified_time.desc())\
                    .limit(limit)
                
            return self.session.exec(statement).all()
            
        except Exception as e:
            logger.error(f"根据哈希值查找相似文件失败: {str(e)}")
            return []
            
    def find_similar_files_by_name(self, file_name: str, exclude_path: str = None, limit: int = 10) -> List[FileScreeningResult]:
        """根据文件名查找可能的相似文件（名称相似度高的文件）
        
        Args:
            file_name: 文件名（不含路径）
            exclude_path: 排除的文件路径（通常是查询文件自身的路径）
            limit: 最大返回结果数量
            
        Returns:
            文件名相似的文件列表
        """
        try:
            if not file_name:
                return []
                
            # 去掉扩展名，只匹配文件主名
            base_name = file_name
            if '.' in base_name:
                base_name = base_name[:base_name.rindex('.')]
            
            # 查找名称类似的文件
            name_pattern = f"%{base_name}%"
            
            if exclude_path:
                statement = select(FileScreeningResult)\
                    .where((FileScreeningResult.file_name.like(name_pattern)) & 
                           (FileScreeningResult.file_path != exclude_path))\
                    .order_by(FileScreeningResult.modified_time.desc())\
                    .limit(limit)
            else:
                statement = select(FileScreeningResult)\
                    .where(FileScreeningResult.file_name.like(name_pattern))\
                    .order_by(FileScreeningResult.modified_time.desc())\
                    .limit(limit)
                
            return self.session.exec(statement).all()
            
        except Exception as e:
            logger.error(f"根据文件名查找相似文件失败: {str(e)}")
            return []

    def get_files_by_time_range(self, time_range: str, limit: int = 500) -> List[Dict[str, Any]]:
        """根据时间范围获取文件
        
        Args:
            time_range: 时间范围 ("today", "last7days", "last30days")
            limit: 最大返回结果数量，默认500
            
        Returns:
            文件信息字典列表
        """
        # 记录开始时间，用于性能监控
        query_start = time.time()
        
        now = datetime.now()
        
        # 确定开始时间
        if time_range == "today":
            start_time = datetime(now.year, now.month, now.day)  # 今天的开始 (00:00:00)
        elif time_range == "last7days":
            start_time = now - timedelta(days=7)  # 7天前
        elif time_range == "last30days":
            start_time = now - timedelta(days=30)  # 30天前
        else:
            raise ValueError(f"无效的时间范围: {time_range}")
        
        try:
            # 优化查询：
            # 1. 添加状态过滤，忽略被标记为ignored的文件
            # 2. 确保使用modified_time的索引
            statement = (
                select(FileScreeningResult)
                .where(
                    (FileScreeningResult.modified_time >= start_time) &
                    (FileScreeningResult.status != 'ignored')
                )
                .order_by(FileScreeningResult.modified_time.desc())
                .limit(limit)
            )
            
            # 执行查询，并记录时间
            query_exec_start = time.time()
            results = self.session.execute(statement).scalars().all()
            query_exec_time = time.time() - query_exec_start
            
            # 将结果转换为字典列表
            conversion_start = time.time()
            result_dicts = [self._result_to_dict(result) for result in results]
            conversion_time = time.time() - conversion_start
            
            # 记录总耗时和组件耗时
            total_time = time.time() - query_start
            
            # 记录查询性能信息
            logger.info(
                f"时间范围查询 [{time_range}] 性能: "
                f"总耗时={total_time:.3f}秒, "
                f"查询执行={query_exec_time:.3f}秒, "
                f"结果转换={conversion_time:.3f}秒, "
                f"结果数={len(results)}"
            )
            
            return result_dicts
            
        except Exception as e:
            logger.error(f"时间范围查询失败: {str(e)}")
            # 返回空列表而不是抛出异常，以确保API的健壮性
            return []
    
    def get_files_by_category_id(self, category_id: int, limit: int = 500) -> List[Dict[str, Any]]:
        """根据分类ID获取文件
        
        Args:
            category_id: 分类ID
            limit: 最大返回结果数量，默认500
            
        Returns:
            文件信息字典列表
        """
        # 记录开始时间，用于性能监控
        query_start = time.time()
        
        try:
            # 优化查询：
            # 1. 添加状态过滤，忽略被标记为ignored的文件
            # 2. 使用category_id索引（已在SQLModel中定义）
            statement = (
                select(FileScreeningResult)
                .where(
                    (FileScreeningResult.category_id == category_id) &
                    (FileScreeningResult.status != 'ignored')
                )
                .order_by(FileScreeningResult.modified_time.desc())
                .limit(limit)
            )
            
            # 执行查询，并记录时间
            query_exec_start = time.time()
            results = self.session.execute(statement).scalars().all()
            query_exec_time = time.time() - query_exec_start
            
            # 将结果转换为字典列表
            conversion_start = time.time()
            result_dicts = [self._result_to_dict(result) for result in results]
            conversion_time = time.time() - conversion_start
            
            # 记录总耗时和组件耗时
            total_time = time.time() - query_start
            
            # 记录查询性能信息
            logger.info(
                f"分类查询 [ID: {category_id}] 性能: "
                f"总耗时={total_time:.3f}秒, "
                f"查询执行={query_exec_time:.3f}秒, "
                f"结果转换={conversion_time:.3f}秒, "
                f"结果数={len(results)}"
            )
            
            return result_dicts
            
        except Exception as e:
            logger.error(f"分类查询失败 [ID: {category_id}]: {str(e)}")
            # 返回空列表而不是抛出异常，以确保API的健壮性
            return []
    
    def _result_to_dict(self, result: FileScreeningResult) -> Dict[str, Any]:
        """将 FileScreeningResult 对象转换为适合前端使用的字典格式
        
        Args:
            result: FileScreeningResult 对象
            
        Returns:
            前端友好的字典格式
        """
        # 对于高频调用的方法，可以手动构造字典而不是使用model_dump()来提高性能
        file_info = {
            "file_path": result.file_path,
            "file_name": result.file_name,
            "file_size": result.file_size,
            "extension": result.extension,
            "modified_time": result.modified_time,
            "created_time": result.created_time,
            "category_id": result.category_id
        }
        
        # 确保时间字段是字符串格式
        for time_field in ["modified_time", "created_time"]:
            if time_field in file_info and file_info[time_field] is not None:
                if isinstance(file_info[time_field], datetime):
                    file_info[time_field] = file_info[time_field].strftime("%Y-%m-%d %H:%M:%S")
        
        # 可以额外添加更多前端需要的字段
        if hasattr(result, 'id'):
            file_info['id'] = result.id
            
        return file_info

    def search_files_by_path_substring(self, substring: str, limit: int = 100) -> List[FileScreeningResult]:
        """根据路径子字符串搜索文件
        
        搜索文件全路径中含有指定子字符串的所有文件
        
        Args:
            substring: 要搜索的子字符串
            limit: 最大返回结果数量
            
        Returns:
            匹配的文件列表
        """
        try:
            if not substring:
                # 如果子字符串为空，返回空列表
                return []
            
            # 使用LIKE操作符进行子字符串匹配
            # 在子字符串前后添加%表示匹配任意字符
            statement = select(FileScreeningResult)\
                .where(FileScreeningResult.file_path.like(f"%{substring}%"))\
                .order_by(FileScreeningResult.modified_time.desc())\
                .limit(limit)
            
            results = self.session.exec(statement).all()
            # 判断结果中的每个文件是否存在
            existing_files = [file for file in results if os.path.exists(file.file_path)]
            logger.debug(f"按路径子字符串'{substring}'搜索到{len(existing_files)}个文件结果")
            return existing_files
        except Exception as e:
            logger.error(f"按路径子字符串搜索文件失败: {e}")
            return []