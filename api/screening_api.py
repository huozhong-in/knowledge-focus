from fastapi import APIRouter, Depends, Body
from sqlalchemy import Engine
from typing import Dict, Any
from datetime import datetime
import os
from screening_mgr import ScreeningManager
from task_mgr import TaskManager
from db_mgr import (
    TaskType, TaskPriority, Task,
)
import logging
logger = logging.getLogger()

def get_router(get_engine: Engine) -> APIRouter:
    router = APIRouter()

    def get_screening_manager(engine: Engine = Depends(get_engine)) -> ScreeningManager:
        return ScreeningManager(engine)
    
    def get_task_manager(engine: Engine = Depends(get_engine)) -> TaskManager:
        return TaskManager(engine)

    @router.post("/file-screening/batch")
    def add_batch_file_screening_results(
        request: Dict[str, Any] = Body(...), 
        screening_mgr: ScreeningManager = Depends(get_screening_manager),
        task_mgr: TaskManager = Depends(get_task_manager)
    ):
        """批量添加文件粗筛结果
        
        参数:
        - data_list: 文件粗筛结果列表
        """
        try:
            # 从请求体中提取数据和参数
            logger.info(f"接收到批量文件粗筛结果，请求体键名: {list(request.keys())}")
            
            # 适配Rust客户端发送的格式: {data_list: [...], auto_create_tasks: true}
            if "data_list" in request:
                data_list = request.get("data_list", [])
            elif isinstance(request, dict):
                data_list = request.get("files", [])
            else:
                # 假设请求体本身就是列表
                data_list = request
                
            if not data_list:
                return {"success": True, "processed_count": 0, "failed_count": 0, "message": "没有需要处理的文件"}

            # 预处理每个文件记录中的时间戳，转换为Python datetime对象
            for data in data_list:
                # 处理Unix时间戳的转换 (从Rust发送的秒数转换为Python datetime)
                if "created_time" in data and isinstance(data["created_time"], (int, float)):
                    data["created_time"] = datetime.fromtimestamp(data["created_time"])
                    
                if "modified_time" in data and isinstance(data["modified_time"], (int, float)):
                    data["modified_time"] = datetime.fromtimestamp(data["modified_time"])
                    
                if "accessed_time" in data and isinstance(data["accessed_time"], (int, float)):
                    data["accessed_time"] = datetime.fromtimestamp(data["accessed_time"])
            
            # 处理字符串格式的时间字段（处理之前已经先处理了整数时间戳）
            for data in data_list:
                for time_field in ["created_time", "modified_time", "accessed_time"]:
                    # 只处理仍然是字符串格式的时间字段（整数时间戳已在前一步转换）
                    if time_field in data and isinstance(data[time_field], str):
                        try:
                            data[time_field] = datetime.fromisoformat(data[time_field].replace("Z", "+00:00"))
                        except Exception as e:
                            logger.warning(f"转换字符串时间字段 {time_field} 失败: {str(e)}")
                            # 如果是修改时间字段转换失败，设置为当前时间
                            if time_field == "modified_time":
                                data[time_field] = datetime.now()
                    
                    # 确保每个时间字段都有值，对于必填字段
                    if time_field == "modified_time" and (time_field not in data or data[time_field] is None):
                        logger.warning(f"缺少必填时间字段 {time_field}，使用当前时间")
                        data[time_field] = datetime.now()
                                
                # Ensure 'extra_metadata' is used, but allow 'metadata' for backward compatibility from client
                if "metadata" in data and "extra_metadata" not in data:
                    data["extra_metadata"] = data.pop("metadata")

            # 1. 先创建任务，获取 task_id
            task_name = f"批量处理文件: {len(data_list)} 个文件"
            task: Task = task_mgr.add_task(
                task_name=task_name,
                task_type=TaskType.TAGGING,
                priority=TaskPriority.MEDIUM,
                extra_data={"file_count": len(data_list)}
            )
            logger.info(f"已创建标记任务 ID: {task.id}，准备处理 {len(data_list)} 个文件")

            # 2. 批量添加粗筛结果，并关联 task_id
            result = screening_mgr.add_batch_screening_results(data_list, task_id=task.id)
            
            # 3. 返回结果
            if result["success"] > 0:
                message = f"已为 {result['success']} 个文件创建处理任务，失败 {result['failed']} 个"
            else:
                message = f"未能处理任何文件，失败 {result['failed']} 个"

            return {
                "success": result["success"] > 0,
                "processed_count": result["success"],
                "failed_count": result["failed"],
                "errors": result.get("errors"),
                "task_id": task.id,
                "message": message
            }
            
        except Exception as e:
            logger.error(f"批量处理文件粗筛结果失败: {str(e)}")
            return {
                "success": False,
                "message": f"批量处理失败: {str(e)}"
            }

    @router.get("/file-screening/results")
    def get_file_screening_results(
        limit: int = 1000,
        category_id: int = None,
        time_range: str = None,
        screening_mgr: ScreeningManager = Depends(get_screening_manager)
    ):
        """获取文件粗筛结果列表，支持按分类和时间范围筛选
        
        参数:
        - limit: 最大返回结果数
        - category_id: 可选，按文件分类ID过滤
        - time_range: 可选，按时间范围过滤 ("today", "last7days", "last30days")
        """
        try:
            from datetime import datetime, timedelta
            
            # 基础查询
            results = screening_mgr.get_all_results(limit)
            
            # 如果结果为空，直接返回空列表，防止后续处理出错
            if not results:
                return {
                    "success": True,
                    "count": 0,
                    "data": []
                }
            
            # 转换为可序列化字典列表
            results_dict = [result.model_dump() for result in results]
            
            # 过滤逻辑
            filtered_results = results_dict
            
            # 按分类过滤
            if (category_id is not None):
                filtered_results = [r for r in filtered_results if r.get('category_id') == category_id]
            
            # 按时间范围过滤
            if time_range:
                now = datetime.now()
                # Ensure modified_time is a string before parsing
                date_format = "%Y-%m-%d %H:%M:%S" # Define the correct format

                if time_range == "today":
                    today = datetime(now.year, now.month, now.day)
                    filtered_results = [r for r in filtered_results if r.get('modified_time') and datetime.strptime(r.get('modified_time'), date_format) >= today]
                elif time_range == "last7days":
                    week_ago = now - timedelta(days=7)
                    filtered_results = [r for r in filtered_results if r.get('modified_time') and datetime.strptime(r.get('modified_time'), date_format) >= week_ago]
                elif time_range == "last30days":
                    month_ago = now - timedelta(days=30)
                    filtered_results = [r for r in filtered_results if r.get('modified_time') and datetime.strptime(r.get('modified_time'), date_format) >= month_ago]
            
            return {
                "success": True,
                "count": len(filtered_results),
                "data": filtered_results
            }
            
        except Exception as e:
            logger.error(f"获取文件粗筛结果列表失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "message": f"获取失败: {str(e)}"
            }
    @router.get("/file-screening/results/search")
    def search_files_by_path_substring(
        substring: str,
        limit: int = 100,
        screening_mgr: ScreeningManager = Depends(get_screening_manager)
    ):
        """根据路径子字符串搜索文件粗筛结果
        
        参数:
        - substring: 要搜索的路径子字符串
        - limit: 最大返回结果数
        """
        try:
            # 使用 ScreeningManager 的搜索方法，现在返回字典列表
            results_dict = screening_mgr.search_files_by_path_substring(substring, limit)
            
            return {
                "success": True,
                "count": len(results_dict),
                "data": results_dict
            }
            
        except Exception as e:
            logger.error(f"根据路径子字符串搜索文件粗筛结果失败: {str(e)}")
            return {
                "success": False,
                "message": f"搜索失败: {str(e)}"
            }


    @router.post("/screening/clean-by-path")
    def clean_screening_results_by_path(
        data: Dict[str, Any] = Body(...),
        screening_mgr: ScreeningManager = Depends(get_screening_manager)
    ):
        """手动清理指定路径下的粗筛结果（用于添加黑名单子文件夹时）
        
        前端可以使用此端点在用户在白名单下添加黑名单子文件夹后清理数据，
        相当于在集合中扣出一个子集来删掉。
        """
        try:
            folder_path = data.get("path", "").strip()
            
            if not folder_path:
                return {"status": "error", "message": "文件夹路径不能为空"}
            
            # 使用 delete_screening_results_by_path_prefix 方法，用于在白名单下添加黑名单子文件夹
            deleted_count = screening_mgr.delete_screening_results_by_path_prefix(folder_path)
            return {
                "status": "success", 
                "deleted": deleted_count,
                "message": f"已清理 {deleted_count} 条与路径前缀 '{folder_path}' 相关的粗筛结果"
            }
                
        except Exception as e:
            logger.error(f"手动清理粗筛结果失败: {str(e)}")
            return {"status": "error", "message": f"清理失败: {str(e)}"}

    @router.post("/screening/delete-by-path")
    def delete_screening_by_path(
        data: Dict[str, Any] = Body(...),
        screening_mgr: ScreeningManager = Depends(get_screening_manager)
    ):
        """删除指定路径的文件粗筛记录
        
        当客户端检测到文件删除事件时，调用此API端点删除对应的粗筛记录。
        
        请求体:
        - file_path: 要删除的文件路径
        
        返回:
        - success: 操作是否成功
        - deleted_count: 删除的记录数量
        - message: 操作结果消息
        """
        try:
            file_path = data.get("file_path")
            
            if not file_path:
                logger.warning("删除粗筛记录请求中未提供文件路径")
                return {
                    "success": False,
                    "deleted_count": 0,
                    "message": "文件路径不能为空"
                }
            
            # 对于单个文件删除，我们需要确保路径是精确匹配的
            # 我们可以使用delete_screening_results_by_path_prefix方法，但需要确保只删除这个确切路径
            # 通常情况下，这个路径应该是一个文件路径，不会匹配到其他文件
            
            # 标准化路径
            normalized_path = os.path.normpath(file_path).replace("\\", "/")
            
            # 执行删除操作
            deleted_count = screening_mgr.delete_screening_results_by_path_prefix(normalized_path)
            
            # 记录操作结果
            if deleted_count > 0:
                logger.info(f"成功删除文件 '{normalized_path}' 的粗筛记录，共 {deleted_count} 条")
            else:
                logger.info(f"未找到文件 '{normalized_path}' 的粗筛记录，无需删除")
            
            return {
                "success": True,
                "deleted_count": deleted_count,
                "message": f"成功删除文件 '{normalized_path}' 的粗筛记录，共 {deleted_count} 条"
            }
            
        except Exception as e:
            logger.error(f"删除文件粗筛记录失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "deleted_count": 0,
                "message": f"删除失败: {str(e)}"
            }
    
    @router.get("/file-screening/total")
    def get_total_screening_results_count(
        screening_mgr: ScreeningManager = Depends(get_screening_manager)
    ):
        """获取文件粗筛结果总数"""
        try:
            total_count = screening_mgr.get_all_results_count()
            return {
                "success": True,
                "total_count": total_count
            }
        except Exception as e:
            logger.error(f"获取文件粗筛结果总数失败: {str(e)}")
            return {
                "success": False,
                "message": f"获取失败: {str(e)}"
            }

    @router.get("/file-screening/by-path-hash")
    def get_screening_by_path_and_hash(
        file_path: str,
        file_hash: str = None,
        screening_mgr: ScreeningManager = Depends(get_screening_manager)
    ):
        """根据文件路径和哈希值获取粗筛结果
        
        参数:
        - file_path: 文件路径
        - file_hash: 文件哈希值（可选）
        
        返回:
        - 匹配的文件粗筛结果记录
        """
        try:
            result = screening_mgr.get_by_path_and_hash(file_path, file_hash)
            
            if result:
                return {
                    "success": True,
                    "data": result.model_dump()
                }
            else:
                return {
                    "success": False,
                    "message": "未找到匹配的文件记录"
                }
                
        except Exception as e:
            logger.error(f"根据路径和哈希获取粗筛结果失败: {str(e)}")
            return {
                "success": False,
                "message": f"查询失败: {str(e)}"
            }

    return router