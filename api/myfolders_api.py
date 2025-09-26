from fastapi import APIRouter, Depends, Body
from sqlmodel import Session, select
from sqlalchemy import Engine
from typing import Dict, Any
import time
import sys
from db_mgr import MyFolders, FileCategory, FileFilterRule, FileExtensionMap, BundleExtension
from myfolders_mgr import MyFoldersManager
from screening_mgr import ScreeningManager
import logging
logger = logging.getLogger()

def get_router(get_engine: Engine) -> APIRouter:
    router = APIRouter()

    def get_myfolders_manager(engine: Engine = Depends(get_engine)) -> MyFoldersManager:
        """获取文件夹管理器实例"""
        return MyFoldersManager(engine=engine)

    def get_screening_manager(engine: Engine = Depends(get_engine)) -> ScreeningManager:
        return ScreeningManager(engine=engine)
    
    # 获取所有配置信息的API端点
    @router.get("/config/all", tags=["myfolders"], summary="获取所有配置")
    def get_all_configuration(
        engine: Engine = Depends(get_engine),
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """
        获取所有Rust端进行文件处理所需的配置信息。
        包括文件分类、粗筛规则、文件扩展名映射、项目识别规则以及监控的文件夹列表。
        """
        try:
            with Session(engine) as session:
                start_time = time.time()
                file_categories = session.exec(select(FileCategory)).all()
                file_filter_rules = session.exec(select(FileFilterRule)).all()
                file_extension_maps = session.exec(select(FileExtensionMap)).all()
                monitored_folders = session.exec(select(MyFolders)).all()
                
                # 检查完全磁盘访问权限状态 
                full_disk_access = False
                if sys.platform == "darwin":  # macOS
                    access_status = myfolders_mgr.check_full_disk_access_status()
                    full_disk_access = access_status.get("has_full_disk_access", False)
                    logger.info(f"[CONFIG] Full disk access status: {full_disk_access}")
                
                elapsed = time.time() - start_time
                logger.info(f"[CONFIG] 获取所有配置耗时 {elapsed:.3f}s (从数据库)")
                
                # 获取 bundle 扩展名列表（直接从数据库获取，不使用正则规则）
                bundle_extensions = myfolders_mgr.get_bundle_extensions_for_rust()
                logger.info(f"[CONFIG] 获取到 {len(bundle_extensions)} 个 bundle 扩展名")
                # from file_tagging_mgr import MARKITDOWN_EXTENSIONS, OTHER_PARSEABLE_EXTENSIONS  # 确保解析器扩展名已加载
                return {
                    "file_categories": file_categories,
                    "file_filter_rules": file_filter_rules,
                    "file_extension_maps": file_extension_maps,
                    "monitored_folders": monitored_folders,
                    # "parsable_extensions": list(set(MARKITDOWN_EXTENSIONS + OTHER_PARSEABLE_EXTENSIONS)),  # 去重
                    "full_disk_access": full_disk_access,  # 完全磁盘访问权限状态
                    "bundle_extensions": bundle_extensions  # 添加直接可用的 bundle 扩展名列表
                }
        except Exception as e:
            logger.error(f"Error fetching all configuration: {e}", exc_info=True)
            # Return a default structure in case of error to prevent client-side parsing issues.
            # The client can check for the presence of 'error_message' or if data arrays are empty.
            return {
                "file_categories": [],
                "file_filter_rules": [],
                "file_extension_maps": [],
                "monitored_folders": [],
                "full_disk_access": False,  # Default to false on error
                "error_message": f"Failed to fetch configuration: {str(e)}"
            }

    @router.get("/file-scanning-config", tags=["myfolders"], summary="获取文件扫描配置（简化版）")
    async def get_file_scanning_config(
        engine: Engine = Depends(get_engine),
    ):
        """
        获取Rust端文件扫描所需的简化配置信息。
        只包含扩展名映射、Bundle扩展名和基础忽略规则。
        """
        try:
            with Session(engine) as session:
                # 获取文件分类和扩展名映射
                file_categories = session.exec(select(FileCategory)).all()
                file_extension_maps = session.exec(select(FileExtensionMap)).all()
                
                # 构建扩展名到分类ID的映射
                extension_mappings = {}
                for ext_map in file_extension_maps:
                    extension_mappings[ext_map.extension] = ext_map.category_id
                
                # 获取Bundle扩展名列表
                bundle_extensions_data = session.exec(select(BundleExtension).where(BundleExtension.is_active)).all()
                bundle_extensions = [be.extension for be in bundle_extensions_data]
                
                # 获取基础忽略规则
                ignore_rules = session.exec(
                    select(FileFilterRule).where(
                        FileFilterRule.action == "exclude",
                        FileFilterRule.enabled
                    )
                ).all()
                ignore_patterns = [rule.pattern for rule in ignore_rules]
                
                return {
                    "extension_mappings": extension_mappings,
                    "bundle_extensions": bundle_extensions,
                    "ignore_patterns": ignore_patterns,
                    "file_categories": [{"id": cat.id, "name": cat.name, "description": cat.description} for cat in file_categories]
                }
            
        except Exception as e:
            logger.error(f"Error fetching file scanning config: {e}", exc_info=True)
            return {
                "extension_mappings": {},
                "bundle_extensions": [],
                "ignore_patterns": [],
                "file_categories": [],
                "error_message": f"Failed to fetch file scanning configuration: {str(e)}"
            }
    
    # 添加文件夹管理相关API
    @router.get("/directories", tags=["myfolders"])
    def get_directories(
        engine: Engine = Depends(get_engine),
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        try:
            # 根据系统平台设置 full_disk_access 状态
            # 只在 macOS 上才有意义
            fda_status = False
            if sys.platform == "darwin":  # macOS
                # 在 macOS 上，检查应用是否有完全磁盘访问权限
                access_status = myfolders_mgr.check_full_disk_access_status()
                fda_status = access_status.get("has_full_disk_access", False)
                logger.info(f"[API DEBUG] Full disk access status: {fda_status}, details: {access_status}")

            # 使用 select 语句从数据库获取所有监控的目录
            stmt = select(MyFolders)
            with Session(engine) as session:
                directories_from_db = session.exec(stmt).all()
                processed_dirs = []
                for d in directories_from_db:
                    dir_dict = {
                        "id": getattr(d, 'id', None),
                        "path": getattr(d, 'path', None),
                        "alias": getattr(d, 'alias', None),
                        "is_blacklist": getattr(d, 'is_blacklist', False),
                        "created_at": d.created_at.isoformat() if getattr(d, 'created_at', None) else None,
                        "updated_at": d.updated_at.isoformat() if getattr(d, 'updated_at', None) else None,
                    }
                    processed_dirs.append(dir_dict)
                
                logger.info(f"[API DEBUG] /directories returning: fda_status={fda_status}, num_dirs={len(processed_dirs)}")
                return {"status": "success", "full_disk_access": fda_status, "data": processed_dirs}
        except Exception as e:
            logger.error(f"Error in get_directories: {e}", exc_info=True)
            return {"status": "error", "full_disk_access": False, "data": [], "message": str(e)}

    @router.post("/directories", tags=["myfolders"])
    def add_directory(
        data: Dict[str, Any] = Body(...),
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """添加新文件夹"""
        try:
            path = data.get("path", "")
            alias = data.get("alias", "")
            is_blacklist = data.get("is_blacklist", False)
            
            if not path: # 修正：之前是 if name或not path:
                return {"status": "error", "message": "路径不能为空"}
            
            success, message_or_dir = myfolders_mgr.add_directory(path, alias, is_blacklist)
            
            if success:
                logger.info(f"添加了新文件夹: {path}")

                # 检查返回值是否是字符串或MyFolders对象
                if isinstance(message_or_dir, str):
                    return {"status": "success", "message": message_or_dir}
                else:                
                    # 如果不是黑名单，前端会立即启动Rust监控
                    if not is_blacklist:
                        # 添加Rust监控的触发信号
                        # 此处日志记录即可，实际监控由前端Tauri通过fetch_and_store_all_config获取最新配置
                        logger.info(f"[MONITOR] 新文件夹已添加，需要立即启动监控: {path}")
                        
                    return {"status": "success", "data": message_or_dir.model_dump(), "message": "文件夹添加成功"}
            else:
                return {"status": "error", "message": message_or_dir}
        except Exception as e:
            logger.error(f"添加文件夹失败: {str(e)}")
            return {"status": "error", "message": f"添加文件夹失败: {str(e)}"}

    @router.put("/directories/{directory_id}", tags=["myfolders"])
    def update_directory(
        directory_id: int,
        data: Dict[str, Any] = Body(...),
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """更新文件夹的信息"""
        try:
            # 这里可以添加更新文件夹其他信息的逻辑
            return {"status": "success", "message": "文件夹信息更新成功"}
        except Exception as e:
            logger.error(f"更新文件夹信息失败: {directory_id}, {str(e)}")
            return {"status": "error", "message": f"更新文件夹信息失败: {str(e)}"}

    @router.put("/directories/{directory_id}/blacklist", tags=["myfolders"])
    def toggle_directory_blacklist(
        directory_id: int,
        data: Dict[str, Any] = Body(...), # 包含 is_blacklist: bool
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """切换文件夹的黑名单状态"""
        try:
            is_blacklist = data.get("is_blacklist")
            if not isinstance(is_blacklist, bool):
                return {"status": "error", "message": "无效的黑名单状态参数"}

            success, message_or_dir = myfolders_mgr.toggle_blacklist(directory_id, is_blacklist)
            if success:
                logger.info(f"切换了文件夹 {directory_id} 的黑名单状态为 {is_blacklist}")
                return {"status": "success", "data": message_or_dir.model_dump(), "message": "黑名单状态更新成功"}
            else:
                return {"status": "error", "message": message_or_dir}
        except Exception as e:
            logger.error(f"切换文件夹黑名单状态失败: {directory_id}, {str(e)}")
            return {"status": "error", "message": f"切换文件夹黑名单状态失败: {str(e)}"}

    @router.delete("/directories/{directory_id}", tags=["myfolders"])
    def delete_directory(
        directory_id: int,
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """删除文件夹"""
        try:
            success, message = myfolders_mgr.remove_directory(directory_id)
            if success:
                logger.info(f"删除了文件夹 {directory_id}")
                return {"status": "success", "message": "文件夹删除成功"}
            else:
                return {"status": "error", "message": message}
        except Exception as e:
            logger.error(f"删除文件夹失败: {directory_id}, {str(e)}")
            return {"status": "error", "message": f"删除文件夹失败: {str(e)}"}

    @router.put("/directories/{directory_id}/alias", tags=["myfolders"])
    def update_directory_alias(
        directory_id: int,
        data: Dict[str, Any] = Body(...), # 包含 alias: str
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """更新文件夹的别名"""
        try:
            alias = data.get("alias")
            if alias is None: # 允许空字符串作为别名，但不允许None
                return {"status": "error", "message": "别名不能为空"}

            success, message_or_dir = myfolders_mgr.update_alias(directory_id, alias)
            if success:
                return {"status": "success", "data": message_or_dir.model_dump(), "message": "别名更新成功"}
            else:
                return {"status": "error", "message": message_or_dir}
        except Exception as e:
            logger.error(f"更新文件夹别名失败: {directory_id}, {str(e)}")
            return {"status": "error", "message": f"更新文件夹别名失败: {str(e)}"}

    # 在文件末尾添加以下端点，用于初始化默认文件夹和获取权限提示
    @router.get("/directories/default")
    def initialize_default_directories_endpoint(myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)):
        """初始化默认系统文件夹"""
        try:
            count = myfolders_mgr.initialize_default_directories()
            return {"status": "success", "message": f"成功初始化/检查了 {count} 个默认文件夹。"}
        except Exception as e:
            logger.error(f"初始化默认文件夹失败: {str(e)}")
            return {"status": "error", "message": f"初始化默认文件夹失败: {str(e)}"}

    @router.get("/directories/default-list", tags=["myfolders"])
    def get_default_directories_list(myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)):
        """获取默认系统文件夹列表（不进行数据库操作）"""
        try:
            directories = myfolders_mgr.get_default_directories()
            return {"status": "success", "data": directories}
        except Exception as e:
            logger.error(f"获取默认文件夹列表失败: {str(e)}")
            return {"status": "error", "message": f"获取默认文件夹列表失败: {str(e)}"}

    @router.get("/macos-permissions-hint", tags=["myfolders"])
    def get_macos_permissions_hint_endpoint(myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)):
        """获取 macOS 权限提示"""
        try:
            hint = myfolders_mgr.get_macOS_permissions_hint()
            return {"status": "success", "data": hint}
        except Exception as e:
            logger.error(f"获取 macOS 权限提示失败: {str(e)}")
            return {"status": "error", "message": f"获取 macOS 权限提示失败: {str(e)}"}

    @router.post("/directories/{directory_id}/request-access", tags=["myfolders"])
    def request_directory_access(
        directory_id: int,
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """尝试读取目录以触发系统授权对话框"""
        try:
            success, message = myfolders_mgr.test_directory_access(directory_id)
            if success:
                return {"status": "success", "message": message}
            else:
                return {"status": "error", "message": message}
        except Exception as e:
            logger.error(f"请求目录访问失败: {directory_id}, {str(e)}")
            return {"status": "error", "message": f"请求目录访问失败: {str(e)}"}

    @router.get("/directories/{directory_id}/access-status", tags=["myfolders"])
    def check_directory_access_status(
        directory_id: int,
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """检查目录的访问权限状态"""
        try:
            success, result = myfolders_mgr.check_directory_access_status(directory_id)
            if success:
                return {"status": "success", "data": result}
            else:
                return {"status": "error", "message": result.get("message", "检查访问状态失败")}
        except Exception as e:
            logger.error(f"检查目录访问状态失败: {directory_id}, {str(e)}")
            return {"status": "error", "message": f"检查目录访问状态失败: {str(e)}"}

    # ========== Bundle扩展名管理端点 ==========
    @router.get("/bundle-extensions", tags=["myfolders"])
    def get_bundle_extensions(
        active_only: bool = True,
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """获取Bundle扩展名列表"""
        try:
            extensions = myfolders_mgr.get_bundle_extensions(active_only=active_only)
            extensions_data = []
            for ext in extensions:
                extensions_data.append({
                    "id": ext.id,
                    "extension": ext.extension,
                    "description": ext.description,
                    "is_active": ext.is_active,
                    "created_at": ext.created_at.isoformat() if ext.created_at else None,
                    "updated_at": ext.updated_at.isoformat() if ext.updated_at else None,
                })
            
            return {
                "status": "success",
                "data": extensions_data,
                "count": len(extensions_data),
                "message": f"成功获取 {len(extensions_data)} 个Bundle扩展名"
            }
        except Exception as e:
            logger.error(f"获取Bundle扩展名失败: {str(e)}")
            return {"status": "error", "message": f"获取Bundle扩展名失败: {str(e)}"}

    @router.post("/bundle-extensions", tags=["myfolders"])
    def add_bundle_extension(
        data: Dict[str, Any] = Body(...),
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """添加新的Bundle扩展名"""
        try:
            extension = data.get("extension", "").strip()
            description = data.get("description", "").strip()
            
            if not extension:
                return {"status": "error", "message": "扩展名不能为空"}
            
            success, result = myfolders_mgr.add_bundle_extension(extension, description)
            
            if success:
                return {
                    "status": "success",
                    "data": {
                        "id": result.id,
                        "extension": result.extension,
                        "description": result.description,
                        "is_active": result.is_active,
                        "created_at": result.created_at.isoformat() if result.created_at else None,
                        "updated_at": result.updated_at.isoformat() if result.updated_at else None,
                    },
                    "message": f"成功添加Bundle扩展名: {result.extension}"
                }
            else:
                return {"status": "error", "message": result}
                
        except Exception as e:
            logger.error(f"添加Bundle扩展名失败: {str(e)}")
            return {"status": "error", "message": f"添加Bundle扩展名失败: {str(e)}"}

    @router.delete("/bundle-extensions/{ext_id}", tags=["myfolders"])
    def remove_bundle_extension(
        ext_id: int,
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """删除Bundle扩展名（设为不活跃）"""
        try:
            success, message = myfolders_mgr.remove_bundle_extension(ext_id)
            
            if success:
                return {"status": "success", "message": message}
            else:
                return {"status": "error", "message": message}
                
        except Exception as e:
            logger.error(f"删除Bundle扩展名失败: {str(e)}")
            return {"status": "error", "message": f"删除Bundle扩展名失败: {str(e)}"}

    # ========== 层级文件夹管理端点 ==========
    @router.post("/folders/blacklist/{parent_id}", tags=["myfolders"])
    def add_blacklist_folder_under_parent(
        parent_id: int,
        data: Dict[str, Any] = Body(...),
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager),
        screening_mgr: ScreeningManager = Depends(get_screening_manager)
    ):
        """在指定的白名单父文件夹下添加黑名单子文件夹"""
        try:
            folder_path = data.get("path", "").strip()
            folder_alias = data.get("alias", "").strip() or None
            
            if not folder_path:
                return {"status": "error", "message": "文件夹路径不能为空"}
            
            success, result = myfolders_mgr.add_blacklist_folder(parent_id, folder_path, folder_alias)
            
            if success:
                logger.info(f"添加了黑名单文件夹: {folder_path}")
                
                # 当文件夹变为黑名单时，清理相关的粗筛结果数据
                deleted_count = screening_mgr.delete_screening_results_by_folder(folder_path)
                
                return {
                    "status": "success",
                    "data": {
                        "id": result.id,
                        "path": result.path,
                        "alias": result.alias,
                        "is_blacklist": result.is_blacklist,
                        "parent_id": result.parent_id,
                        "created_at": result.created_at.isoformat() if result.created_at else None,
                        "updated_at": result.updated_at.isoformat() if result.updated_at else None,
                    },
                    "message": f"成功添加黑名单文件夹: {result.path}，清理了 {deleted_count} 条相关粗筛结果"
                }
            else:
                return {"status": "error", "message": result}
                
        except Exception as e:
            logger.error(f"添加黑名单文件夹失败: {str(e)}")
            return {"status": "error", "message": f"添加黑名单文件夹失败: {str(e)}"}

    @router.get("/folders/hierarchy", tags=["myfolders"])
    def get_folder_hierarchy(
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """获取文件夹层级关系（白名单+其下的黑名单）"""
        try:
            start_time = time.time()
            hierarchy = myfolders_mgr.get_folder_hierarchy()
            elapsed = time.time() - start_time
            logger.info(f"[FOLDERS] 获取文件夹层级关系耗时 {elapsed:.3f}s (从数据库)")
            
            return {
                "status": "success",
                "data": hierarchy,
                "count": len(hierarchy),
                "message": f"成功获取 {len(hierarchy)} 个父文件夹的层级关系"
            }
        except Exception as e:
            logger.error(f"获取文件夹层级关系失败: {str(e)}")
            return {"status": "error", "message": f"获取文件夹层级关系失败: {str(e)}"}

    # ========== Bundle扩展名状态切换端点 ==========
    
    @router.patch("/bundle-extensions/{ext_id}/toggle", tags=["myfolders"])
    def toggle_bundle_extension_status(
        ext_id: int,
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """切换Bundle扩展名的启用状态"""
        try:
            success, result = myfolders_mgr.toggle_bundle_extension_status(ext_id)
            if success:
                status_text = "启用" if result.is_active else "禁用"
                return {
                    "status": "success",
                    "data": result,
                    "message": f"Bundle扩展名 '{result.extension}' 已{status_text}"
                }
            else:
                return {"status": "error", "message": result}
        except Exception as e:
            logger.error(f"切换Bundle扩展名状态失败: {str(e)}")
            return {"status": "error", "message": f"切换Bundle扩展名状态失败: {str(e)}"}

    # ========== 文件分类管理端点 ==========
    
    @router.get("/file-categories", tags=["myfolders"])
    def get_file_categories(
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """获取所有文件分类"""
        try:
            categories = myfolders_mgr.get_file_categories()
            return {
                "status": "success",
                "data": categories,
                "count": len(categories),
                "message": f"成功获取 {len(categories)} 个文件分类"
            }
        except Exception as e:
            logger.error(f"获取文件分类失败: {str(e)}")
            return {"status": "error", "message": f"获取文件分类失败: {str(e)}"}

    @router.post("/file-categories", tags=["myfolders"])
    def add_file_category(
        data: Dict[str, Any] = Body(...),
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """添加新的文件分类"""
        try:
            name = data.get("name", "").strip()
            description = data.get("description")
            icon = data.get("icon")
            
            if not name:
                return {"status": "error", "message": "分类名称不能为空"}
            
            success, result = myfolders_mgr.add_file_category(name, description, icon)
            if success:
                return {
                    "status": "success",
                    "data": result,
                    "message": f"文件分类 '{result.name}' 添加成功"
                }
            else:
                return {"status": "error", "message": result}
        except Exception as e:
            logger.error(f"添加文件分类失败: {str(e)}")
            return {"status": "error", "message": f"添加文件分类失败: {str(e)}"}

    @router.put("/file-categories/{category_id}", tags=["myfolders"])
    def update_file_category(
        category_id: int,
        data: Dict[str, Any] = Body(...),
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """更新文件分类信息"""
        try:
            name = data.get("name")
            description = data.get("description")
            icon = data.get("icon")
            
            success, result = myfolders_mgr.update_file_category(category_id, name, description, icon)
            if success:
                return {
                    "status": "success",
                    "data": result,
                    "message": f"文件分类 '{result.name}' 更新成功"
                }
            else:
                return {"status": "error", "message": result}
        except Exception as e:
            logger.error(f"更新文件分类失败: {str(e)}")
            return {"status": "error", "message": f"更新文件分类失败: {str(e)}"}

    @router.delete("/file-categories/{category_id}", tags=["myfolders"])
    def delete_file_category(
        category_id: int,
        force: bool = False,
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """删除文件分类"""
        try:
            success, message = myfolders_mgr.delete_file_category(category_id, force)
            if success:
                return {"status": "success", "message": message}
            else:
                return {"status": "error", "message": message}
        except Exception as e:
            logger.error(f"删除文件分类失败: {str(e)}")
            return {"status": "error", "message": f"删除文件分类失败: {str(e)}"}

    # ========== 扩展名映射管理端点 ==========
    
    @router.get("/extension-mappings", tags=["myfolders"])
    def get_extension_mappings(
        category_id: int = None,
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """获取扩展名映射列表"""
        try:
            mappings = myfolders_mgr.get_extension_mappings(category_id)
            return {
                "status": "success",
                "data": mappings,
                "count": len(mappings),
                "message": f"成功获取 {len(mappings)} 个扩展名映射"
            }
        except Exception as e:
            logger.error(f"获取扩展名映射失败: {str(e)}")
            return {"status": "error", "message": f"获取扩展名映射失败: {str(e)}"}

    @router.post("/extension-mappings", tags=["myfolders"])
    def add_extension_mapping(
        data: Dict[str, Any] = Body(...),
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """添加新的扩展名映射"""
        try:
            extension = data.get("extension", "").strip()
            category_id = data.get("category_id")
            description = data.get("description")
            priority = data.get("priority", "medium")
            
            if not extension:
                return {"status": "error", "message": "扩展名不能为空"}
            if not category_id:
                return {"status": "error", "message": "必须选择文件分类"}
            
            success, result = myfolders_mgr.add_extension_mapping(extension, category_id, description, priority)
            if success:
                return {
                    "status": "success",
                    "data": result,
                    "message": f"扩展名映射 '{result.extension}' 添加成功"
                }
            else:
                return {"status": "error", "message": result}
        except Exception as e:
            logger.error(f"添加扩展名映射失败: {str(e)}")
            return {"status": "error", "message": f"添加扩展名映射失败: {str(e)}"}

    @router.put("/extension-mappings/{mapping_id}", tags=["myfolders"])
    def update_extension_mapping(
        mapping_id: int,
        data: Dict[str, Any] = Body(...),
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """更新扩展名映射"""
        try:
            extension = data.get("extension")
            category_id = data.get("category_id")
            description = data.get("description")
            priority = data.get("priority")
            
            success, result = myfolders_mgr.update_extension_mapping(mapping_id, extension, category_id, description, priority)
            if success:
                return {
                    "status": "success",
                    "data": result,
                    "message": f"扩展名映射 '{result.extension}' 更新成功"
                }
            else:
                return {"status": "error", "message": result}
        except Exception as e:
            logger.error(f"更新扩展名映射失败: {str(e)}")
            return {"status": "error", "message": f"更新扩展名映射失败: {str(e)}"}

    @router.delete("/extension-mappings/{mapping_id}", tags=["myfolders"])
    def delete_extension_mapping(
        mapping_id: int,
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """删除扩展名映射"""
        try:
            success, message = myfolders_mgr.delete_extension_mapping(mapping_id)
            if success:
                return {"status": "success", "message": message}
            else:
                return {"status": "error", "message": message}
        except Exception as e:
            logger.error(f"删除扩展名映射失败: {str(e)}")
            return {"status": "error", "message": f"删除扩展名映射失败: {str(e)}"}

    # ========== 文件过滤规则管理端点 ==========
    
    @router.get("/filter-rules", tags=["myfolders"])
    def get_filter_rules(
        enabled_only: bool = False,
        user_only: bool = False,
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """获取文件过滤规则列表"""
        try:
            rules = myfolders_mgr.get_filter_rules(enabled_only, user_only)
            return {
                "status": "success",
                "data": rules,
                "count": len(rules),
                "message": f"成功获取 {len(rules)} 个文件过滤规则"
            }
        except Exception as e:
            logger.error(f"获取文件过滤规则失败: {str(e)}")
            return {"status": "error", "message": f"获取文件过滤规则失败: {str(e)}"}

    @router.post("/filter-rules", tags=["myfolders"])
    def add_filter_rule(
        data: Dict[str, Any] = Body(...),
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """添加新的文件过滤规则"""
        try:
            name = data.get("name", "").strip()
            rule_type = data.get("rule_type", "")
            pattern = data.get("pattern", "").strip()
            action = data.get("action", "exclude")
            description = data.get("description")
            priority = data.get("priority", "medium")
            pattern_type = data.get("pattern_type", "regex")
            category_id = data.get("category_id")
            extra_data = data.get("extra_data")
            
            if not name:
                return {"status": "error", "message": "规则名称不能为空"}
            if not rule_type:
                return {"status": "error", "message": "必须选择规则类型"}
            if not pattern:
                return {"status": "error", "message": "匹配模式不能为空"}
            
            success, result = myfolders_mgr.add_filter_rule(
                name, rule_type, pattern, action, description, priority, pattern_type, category_id, extra_data
            )
            if success:
                return {
                    "status": "success",
                    "data": result,
                    "message": f"文件过滤规则 '{result.name}' 添加成功"
                }
            else:
                return {"status": "error", "message": result}
        except Exception as e:
            logger.error(f"添加文件过滤规则失败: {str(e)}")
            return {"status": "error", "message": f"添加文件过滤规则失败: {str(e)}"}

    @router.put("/filter-rules/{rule_id}", tags=["myfolders"])
    def update_filter_rule(
        rule_id: int,
        data: Dict[str, Any] = Body(...),
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """更新文件过滤规则"""
        try:
            # 移除空值
            update_data = {k: v for k, v in data.items() if v is not None}
            
            success, result = myfolders_mgr.update_filter_rule(rule_id, **update_data)
            if success:
                return {
                    "status": "success",
                    "data": result,
                    "message": f"文件过滤规则 '{result.name}' 更新成功"
                }
            else:
                return {"status": "error", "message": result}
        except Exception as e:
            logger.error(f"更新文件过滤规则失败: {str(e)}")
            return {"status": "error", "message": f"更新文件过滤规则失败: {str(e)}"}

    @router.patch("/filter-rules/{rule_id}/toggle", tags=["myfolders"])
    def toggle_filter_rule_status(
        rule_id: int,
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """切换文件过滤规则的启用状态"""
        try:
            success, result = myfolders_mgr.toggle_filter_rule_status(rule_id)
            if success:
                status_text = "启用" if result.enabled else "禁用"
                return {
                    "status": "success",
                    "data": result,
                    "message": f"文件过滤规则 '{result.name}' 已{status_text}"
                }
            else:
                return {"status": "error", "message": result}
        except Exception as e:
            logger.error(f"切换文件过滤规则状态失败: {str(e)}")
            return {"status": "error", "message": f"切换文件过滤规则状态失败: {str(e)}"}

    @router.delete("/filter-rules/{rule_id}", tags=["myfolders"])
    def delete_filter_rule(
        rule_id: int,
        force: bool = False,
        myfolders_mgr: MyFoldersManager = Depends(get_myfolders_manager)
    ):
        """删除文件过滤规则"""
        try:
            success, message = myfolders_mgr.delete_filter_rule(rule_id, force)
            if success:
                return {"status": "success", "message": message}
            else:
                return {"status": "error", "message": message}
        except Exception as e:
            logger.error(f"删除文件过滤规则失败: {str(e)}")
            return {"status": "error", "message": f"删除文件过滤规则失败: {str(e)}"}

    return router