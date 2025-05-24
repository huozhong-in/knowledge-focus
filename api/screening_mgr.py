from typing import List, Dict, Any, Optional
from sqlmodel import Session, select, delete, update
from db_mgr import FileScreeningResult, FileScreenResult
from datetime import datetime
import logging
import json
from typing import Dict, Any, Optional, List, Tuple, Union

logger = logging.getLogger(__name__)

class ScreeningManager:
    """文件粗筛结果管理类，提供增删改查方法"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def add_screening_result(self, data: Dict[str, Any]) -> Optional[FileScreeningResult]:
        """添加一条文件粗筛结果
        
        Args:
            data: 包含文件元数据和初步分类信息的字典
            
        Returns:
            添加成功返回记录对象，失败返回None
        """
        try:
            # 检查是否已存在相同路径和哈希值的记录
            file_path = data.get("file_path", "")
            file_hash = data.get("file_hash")
            
            existing_record = self.get_by_path_and_hash(file_path, file_hash)
            if existing_record:
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
            self.session.commit()
            self.session.refresh(result)
            
            logger.info(f"添加文件粗筛结果成功: {result.file_path}")
            return result
            
        except Exception as e:
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
        
        for data in results_data:
            try:
                result = self.add_screening_result(data)
                if result:
                    success_count += 1
                else:
                    failed_count += 1
                    errors.append(f"添加文件失败: {data.get('file_path', 'unknown path')}")
            except Exception as e:
                failed_count += 1
                errors.append(f"处理文件出错: {data.get('file_path', 'unknown path')} - {str(e)}")
        
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