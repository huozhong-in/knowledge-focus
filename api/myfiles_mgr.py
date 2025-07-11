from sqlmodel import (
    Field, 
    SQLModel, 
    create_engine, 
    Session, 
    select, 
    inspect, 
    text, 
    asc, 
    and_, 
    or_, 
    desc, 
    not_,
    Column,
    Enum,
    JSON,
)
from datetime import datetime
from db_mgr import MyFiles, BundleExtension, SystemConfig
from typing import Dict, List, Optional, Tuple, Set, Union
import os
import platform
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class MyFilesManager:
    """文件/文件夹资源管理、授权状态管理类
    
    负责:
    1. 管理用户授权的文件夹列表
    2. 维护常用文件夹的授权状态
    3. 管理黑名单功能
    4. 提供跨平台(macOS/Windows)的文件路径处理
    """
    def __init__(self, session: Session) -> None:
        self.session = session
        self.system = platform.system()  # 'Darwin' for macOS, 'Windows' for Windows
    
    def get_default_directories(self) -> List[Dict[str, str]]:
        """获取系统默认常用文件夹，根据操作系统返回不同的文件夹列表
        
        添加文件夹存在性检查，只返回实际存在的文件夹
        
        Returns:
            List[Dict[str, str]]: 包含文件夹名称和路径的字典列表
        """
        dirs = []
        
        if self.system == "Darwin":  # macOS
            home_dir = os.path.expanduser("~")
            potential_dirs = [
                {"name": "桌面", "path": os.path.join(home_dir, "Desktop")},
                {"name": "文稿", "path": os.path.join(home_dir, "Documents")},
                {"name": "下载", "path": os.path.join(home_dir, "Downloads")},
                {"name": "图片", "path": os.path.join(home_dir, "Pictures")},
                {"name": "音乐", "path": os.path.join(home_dir, "Music")},
                {"name": "影片", "path": os.path.join(home_dir, "Movies")},
            ]
        elif self.system == "Windows":
            # Windows系统使用USERPROFILE环境变量获取用户主文件夹
            home_dir = os.environ.get("USERPROFILE")
            if home_dir:
                potential_dirs = [
                    {"name": "桌面", "path": os.path.join(home_dir, "Desktop")},
                    {"name": "文档", "path": os.path.join(home_dir, "Documents")},
                    {"name": "下载", "path": os.path.join(home_dir, "Downloads")},
                    {"name": "图片", "path": os.path.join(home_dir, "Pictures")},
                    {"name": "音乐", "path": os.path.join(home_dir, "Music")},
                    {"name": "视频", "path": os.path.join(home_dir, "Videos")},
                ]
                
                # 添加Windows特有的文件夹（如OneDrive）
                onedrive_dir = os.environ.get("OneDriveConsumer") or os.environ.get("OneDrive")
                if onedrive_dir and os.path.exists(onedrive_dir):
                    potential_dirs.append({"name": "OneDrive", "path": onedrive_dir})
            else:
                potential_dirs = []
        else:
            potential_dirs = []
        
        # 添加文件夹存在性检查
        for dir_info in potential_dirs:
            if os.path.exists(dir_info["path"]) and os.path.isdir(dir_info["path"]):
                dirs.append(dir_info)
            else:
                logger.warning(f"默认文件夹不存在: {dir_info['path']}")
        
        return dirs
    
    def initialize_default_directories(self) -> int:
        """初始化默认文件夹到数据库
        
        如果数据库中不存在这些文件夹记录，将它们添加进去
        
        Returns:
            int: 初始化的文件夹数量
        """
        default_dirs = self.get_default_directories()
        existing_paths = {myfile.path for myfile in self.session.exec(select(MyFiles)).all()}
        
        new_records = []
        for dir_info in default_dirs:
            if dir_info["path"] not in existing_paths:
                new_file = MyFiles(
                    path=dir_info["path"],
                    alias=dir_info["name"],
                    is_blacklist=False
                )
                new_records.append(new_file)
        
        if new_records:
            self.session.add_all(new_records)
            self.session.commit()
            logger.info(f"已初始化 {len(new_records)} 个默认文件夹")
        
        return len(new_records)
    
    def get_all_directories(self) -> List[MyFiles]:
        """获取所有文件夹记录
        
        Returns:
            List[MyFiles]: 所有文件夹记录列表
        """
        return self.session.exec(select(MyFiles)).all()
    
    def get_authorized_directories(self) -> List[MyFiles]:
        """获取所有已授权的文件夹（即非黑名单的文件夹）
        
        Returns:
            List[MyFiles]: 已授权的文件夹记录列表
        """
        return self.session.exec(
            select(MyFiles).where(
                MyFiles.is_blacklist == False
            )
        ).all()
    
    # 已移除 get_pending_directories 方法，不再需要检查授权状态
    
    def get_blacklist_directories(self) -> List[MyFiles]:
        """获取所有黑名单文件夹
        
        Returns:
            List[MyFiles]: 黑名单文件夹记录列表
        """
        return self.session.exec(
            select(MyFiles).where(MyFiles.is_blacklist == True)
        ).all()

    def add_directory(self, path: str, alias: Optional[str] = None, is_blacklist: bool = False) -> Tuple[bool, Union[MyFiles, str]]:
        """添加新文件夹
        
        Args:
            path (str): 文件夹路径
            alias (Optional[str], optional): 文件夹别名. Defaults to None.
            is_blacklist (bool, optional): 是否为黑名单文件夹. Defaults to False.
        
        Returns:
            Tuple[bool, Union[MyFiles, str]]: (成功标志, 文件夹对象或错误消息)
        """
        # 标准化路径
        path = os.path.normpath(path)
        
        # 检查路径是否存在
        if not os.path.exists(path):
            return False, f"路径不存在: {path}"
            
        # 检查是否为文件夹
        if not os.path.isdir(path):
            return False, f"不是有效的文件夹: {path}"
            
        # 检查记录是否已存在
        existing = self.session.exec(
            select(MyFiles).where(MyFiles.path == path)
        ).first()
        
        if existing:
            return False, f"文件夹已存在: {path}"
            
        # 添加新记录
        new_file = MyFiles(
            path=path,
            alias=alias,

            is_blacklist=is_blacklist
        )
        
        self.session.add(new_file)
        self.session.commit()
        self.session.refresh(new_file)  # 刷新以获取完整对象
        
        return True, new_file
    
    # 授权状态方法已移除
        self.session.commit()
        self.session.refresh(directory)
        return True, directory
    
    def toggle_blacklist(self, directory_id: int, is_blacklist: bool) -> Tuple[bool, MyFiles | str]:
        """切换文件夹的黑名单状态

        Args:
            directory_id (int): 文件夹的ID
            is_blacklist (bool): 是否加入黑名单

        Returns:
            Tuple[bool, MyFiles | str]: (成功标志, 更新后的文件夹对象或错误消息)
        """
        directory = self.session.get(MyFiles, directory_id)
        if not directory:
            return False, f"文件夹ID不存在: {directory_id}"

        directory.is_blacklist = is_blacklist
        directory.updated_at = datetime.now()
        self.session.add(directory)
        self.session.commit()
        self.session.refresh(directory)
        return True, directory
    
    def remove_directory(self, directory_id: int) -> Tuple[bool, str]:
        """从数据库中删除文件夹记录，并清理相关的粗筛记录
        
        Args:
            directory_id (int): 文件夹的ID
        
        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        # 查找记录
        directory = self.session.get(MyFiles, directory_id)
        
        if not directory:
            return False, f"文件夹ID不存在: {directory_id}"
        
        # 保存路径用于日志或消息
        deleted_path = directory.path
        
        # 1. 先删除该目录相关的所有粗筛记录
        try:
            from screening_mgr import ScreeningManager
            screening_mgr = ScreeningManager(self.session)
            deleted_count = screening_mgr.delete_screening_results_by_path_prefix(deleted_path)
            logger.info(f"已删除文件夹'{deleted_path}'相关的 {deleted_count} 条粗筛记录")
        except Exception as e:
            logger.error(f"删除文件夹'{deleted_path}'相关的粗筛记录时出错: {str(e)}")
            # 继续执行删除目录操作，即使清理粗筛记录失败
        
        # 2. 删除目录记录
        self.session.delete(directory)
        self.session.commit()
        
        return True, f"成功删除文件夹: {deleted_path}"
    
    def update_alias(self, directory_id: int, alias: str) -> Tuple[bool, MyFiles | str]:
        """更新文件夹别名
        
        Args:
            directory_id (int): 文件夹的ID
            alias (str): 新别名
        
        Returns:
            Tuple[bool, MyFiles | str]: (成功标志, 更新后的文件夹对象或错误消息)
        """
        # 查找记录
        directory = self.session.get(MyFiles, directory_id)
        
        if not directory:
            return False, f"文件夹ID不存在: {directory_id}"
            
        # 更新别名
        directory.alias = alias
        directory.updated_at = datetime.now()
        self.session.add(directory)
        self.session.commit()
        self.session.refresh(directory)
        
        return True, directory
    
    def is_path_monitored(self, path: str) -> bool:
        """检查路径是否被监控（已授权且不在黑名单中）
        
        Args:
            path (str): 要检查的路径
        
        Returns:
            bool: 如果路径被监控则返回True，否则返回False
        """
        # 标准化路径
        path = os.path.normpath(path)
        
        # 首先检查是否在黑名单中
        if self.is_path_in_blacklist(path):
            return False
        
        # 检查路径是否存在于数据库
        directory = self.session.exec(
            select(MyFiles).where(MyFiles.path == path)
        ).first()
        
        # 如果路径存在于数据库且不是黑名单，则认为已授权
        if directory:
            return not directory.is_blacklist
        
        # 检查是否是已授权文件夹的子文件夹
        authorized_dirs = self.get_authorized_directories()
        path_obj = Path(path)
        
        for auth_dir in authorized_dirs:
            auth_path = Path(auth_dir.path)
            # 检查path是否是auth_path的子文件夹
            try:
                _ = path_obj.relative_to(auth_path)
                return True
            except ValueError:
                continue
        
        # 如果路径不在数据库中，且不是任何已授权文件夹的子文件夹，则不监控
        return False
    
    def is_path_in_blacklist(self, path: str, use_cache: bool = True) -> bool:
        """检查路径是否在黑名单中
        
        Args:
            path (str): 要检查的路径
            use_cache (bool, optional): 是否使用缓存的黑名单列表。默认为True
        
        Returns:
            bool: 如果路径在黑名单中则返回True，否则返回False
        """
        if not path:
            return False
            
        # 标准化路径
        path = os.path.normpath(path).replace("\\", "/")
        
        # 检查路径本身是否在黑名单中
        directory = self.session.exec(
            select(MyFiles).where(
                and_(
                    MyFiles.path == path,
                    MyFiles.is_blacklist == True
                )
            )
        ).first()
        
        if directory:
            return True
            
        # 优化黑名单子目录检查
        # 1. 使用SQL的LIKE操作符更高效地检查路径前缀匹配
        blacklist_paths_query = self.session.exec(
            select(MyFiles.path).where(MyFiles.is_blacklist == True)
        ).all()
        
        # 将当前路径与所有黑名单路径进行比较
        for blacklist_path in blacklist_paths_query:
            normalized_blacklist = os.path.normpath(blacklist_path).replace("\\", "/")
            
            # 确保两个路径都以/结尾，以处理目录
            if not normalized_blacklist.endswith("/"):
                normalized_blacklist += "/"
                
            # 简单的字符串前缀匹配
            if path.startswith(normalized_blacklist):
                return True
                
            # 另一种情况是当前路径是黑名单的父目录，这种情况不应该被标记为黑名单
                
        # 备用方法：使用Path对象进行比较（较慢但更精确）
        # 检查路径是否是黑名单文件夹的子文件夹
        blacklist_dirs = self.get_blacklist_directories()
        path_obj = Path(path)
        
        for black_dir in blacklist_dirs:
            black_path = Path(black_dir.path)
            # 检查path是否是black_path的子文件夹
            try:
                _ = path_obj.relative_to(black_path)
                return True
            except ValueError:
                continue
                
        return False
    
    def check_authorization_needed(self) -> List[Dict]:
        """获取需要用户授权的文件夹列表
        
        Returns:
            List[Dict]: 需要授权的文件夹列表，每个文件夹包含id, path和alias信息
        """
        # 获取所有待授权的文件夹
        pending_dirs = self.get_pending_directories()
        result = []
        
        for directory in pending_dirs:
            # 检查文件夹是否存在
            if os.path.exists(directory.path):
                result.append({
                    "id": directory.id,
                    "path": directory.path,
                    "alias": directory.alias or os.path.basename(directory.path),
                    "exists": True
                })
            else:
                result.append({
                    "id": directory.id,
                    "path": directory.path,
                    "alias": directory.alias or os.path.basename(directory.path),
                    "exists": False
                })
                
        return result
    
    def get_monitored_paths(self) -> Set[str]:
        """获取所有需要监控的路径
        这些路径会被传递给Rust监听器用于文件变更检测
        
        Returns:
            Set[str]: 需要监控的路径集合
        """
        authorized_dirs = self.get_authorized_directories()
        return {directory.path for directory in authorized_dirs if os.path.exists(directory.path)}
    
    def get_macOS_permissions_hint(self) -> Dict[str, str]:
        """获取macOS权限提示信息
        
        Returns:
            Dict[str, str]: macOS权限提示信息
        """
        if self.system != "Darwin":
            return {}
            
        return {
            "full_disk_access": "需要在'系统设置'>'隐私与安全性'>'完全磁盘访问权限'中授权，才能读取非标准文件夹",
            "docs_desktop_downloads": "需要在'系统设置'>'隐私与安全性'>'文件与文件夹'中授权读取这些文件夹",
            "removable_volumes": "需要在'系统设置'>'隐私与安全性'>'可移除的卷宗'中授权读取外接设备",
            "network_volumes": "需要在'系统设置'>'隐私与安全性'>'网络卷宗'中授权读取网络设备",
        }
    
    def get_windows_permissions_hint(self) -> Dict[str, str]:
        """获取Windows权限提示信息
        
        Returns:
            Dict[str, str]: Windows权限提示信息
        """
        if self.system != "Windows":
            return {}
            
        return {
            "admin_access": "以管理员权限运行应用可以读取系统大部分位置",
            "removable_drives": "可能需要单独授权访问可移动设备",
            "network_drives": "访问网络驱动器可能需要额外凭据",
        }

    def test_directory_access(self, directory_id: int) -> Tuple[bool, str]:
        """尝试读取文件夹以触发系统授权对话框
        
        Args:
            directory_id (int): 文件夹ID
            
        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        try:
            # 获取目录
            directory = self.session.get(MyFiles, directory_id)
            if not directory:
                return False, f"文件夹ID不存在: {directory_id}"
            
            path = directory.path
            
            # 检查路径是否存在
            if not os.path.exists(path):
                return False, f"路径不存在: {path}"
                
            # 尝试列出文件夹内容，这将触发系统授权对话框
            file_list = os.listdir(path)
            
            # 如果成功读取，更新最后修改时间
            directory.updated_at = datetime.now()
            self.session.add(directory)
            self.session.commit()
            
            return True, f"成功读取文件夹，发现 {len(file_list)} 个文件/文件夹"
        except PermissionError:
            return False, "没有访问权限，用户可能拒绝了授权请求"
        except Exception as e:
            return False, f"读取文件夹时出错: {str(e)}"
    
    def check_directory_access_status(self, directory_id: int) -> Tuple[bool, Dict]:
        """检查文件夹的访问权限状态
        
        Args:
            directory_id (int): 文件夹ID
            
        Returns:
            Tuple[bool, Dict]: (成功标志, 包含访问状态信息的字典)
        """
        try:
            # 获取目录
            directory = self.session.get(MyFiles, directory_id)
            if not directory:
                return False, {"message": f"文件夹ID不存在: {directory_id}"}
            
            path = directory.path
            
            # 检查路径是否存在
            if not os.path.exists(path):
                return False, {"message": f"路径不存在: {path}", "access_granted": False}
                
            # 尝试列出文件夹内容
            try:
                file_list = os.listdir(path)
                # 如果成功读取，返回访问权限状态为True
                return True, {
                    "message": f"成功读取文件夹，发现 {len(file_list)} 个文件/文件夹",
                    "access_granted": True, 
                    "file_count": len(file_list)
                }
            except PermissionError:
                # 权限错误，返回访问权限状态为False
                return True, {
                    "message": "没有访问权限",
                    "access_granted": False
                }
            except Exception as e:
                return False, {
                    "message": f"读取文件夹时出错: {str(e)}",
                    "access_granted": False
                }
        except Exception as e:
            return False, {"message": f"检查访问权限时出错: {str(e)}", "access_granted": False}

    def check_full_disk_access_status(self) -> Dict:
        """检查系统完全磁盘访问权限状态
        
        Returns:
            Dict: 包含完全磁盘访问权限状态的字典
        """
        try:
            # 检查操作系统类型
            if self.system != "Darwin":
                return {
                    "has_full_disk_access": False,
                    "message": "完全磁盘访问权限仅适用于macOS系统",
                    "status": "not_applicable"
                }
                
            # 尝试读取一些系统目录，这些目录通常需要完全磁盘访问权限
            test_paths = [
                "/Library/Application Support",
                "/Library/Preferences",
                "/System/Library/Preferences",
                "/private/var/db",
                "/usr/local"
            ]
            
            # 尝试读取每个路径
            access_results = {}
            for path in test_paths:
                if os.path.exists(path):
                    try:
                        # 尝试列出目录内容
                        files = os.listdir(path)
                        access_results[path] = {
                            "accessible": True,
                            "file_count": len(files)
                        }
                    except PermissionError:
                        access_results[path] = {
                            "accessible": False,
                            "error": "权限错误"
                        }
                    except Exception as e:
                        access_results[path] = {
                            "accessible": False,
                            "error": str(e)
                        }
                else:
                    access_results[path] = {
                        "accessible": False,
                        "error": "路径不存在"
                    }
            
            # 如果所有测试路径都能访问，则认为有完全磁盘访问权限
            accessible_count = sum(1 for res in access_results.values() if res.get("accessible", False))
            has_full_access = accessible_count >= len(test_paths) * 0.8  # 80%以上的路径可访问
            
            return {
                "has_full_disk_access": has_full_access,
                "access_results": access_results,
                "test_paths_count": len(test_paths),
                "accessible_paths_count": accessible_count,
                "status": "checked"
            }
        
        except Exception as e:
            return {
                "has_full_disk_access": False,
                "message": f"检查时出错: {str(e)}",
                "status": "error"
            }

    # ========== 黑名单层级管理方法 ==========
    
    def add_blacklist_folder(self, parent_id: int, folder_path: str, folder_alias: str = None) -> Tuple[bool, Union[MyFiles, str]]:
        """在指定的白名单文件夹下添加黑名单子文件夹
        
        Args:
            parent_id (int): 父文件夹（白名单）的ID
            folder_path (str): 黑名单文件夹路径
            folder_alias (str, optional): 黑名单文件夹别名
            
        Returns:
            Tuple[bool, Union[MyFiles, str]]: (成功标志, 黑名单文件夹对象或错误消息)
        """
        try:
            # 验证父文件夹存在且不是黑名单
            parent_folder = self.session.get(MyFiles, parent_id)
            if not parent_folder:
                return False, f"父文件夹ID不存在: {parent_id}"
            
            if parent_folder.is_blacklist:
                return False, "不能在黑名单文件夹下添加子文件夹"
            
            # 验证子文件夹路径在父文件夹下
            folder_path = os.path.normpath(folder_path)
            parent_path = os.path.normpath(parent_folder.path)
            
            if not folder_path.startswith(parent_path):
                return False, f"文件夹路径必须在父文件夹 {parent_path} 下"
            
            # 检查是否已存在
            existing = self.session.exec(
                select(MyFiles).where(MyFiles.path == folder_path)
            ).first()
            
            if existing:
                # 如果已存在，更新为黑名单
                existing.is_blacklist = True
                existing.parent_id = parent_id
                existing.updated_at = datetime.now()
                if folder_alias:
                    existing.alias = folder_alias
                self.session.add(existing)
                self.session.commit()
                self.session.refresh(existing)
                return True, existing
            
            # 创建新的黑名单记录
            blacklist_folder = MyFiles(
                path=folder_path,
                alias=folder_alias or os.path.basename(folder_path),
                is_blacklist=True,
                is_common_folder=False,
                parent_id=parent_id  # 黑名单不需要授权状态
            )
            
            self.session.add(blacklist_folder)
            self.session.commit()
            self.session.refresh(blacklist_folder)
            
            return True, blacklist_folder
            
        except Exception as e:
            logger.error(f"添加黑名单文件夹失败: {str(e)}")
            self.session.rollback()
            return False, f"添加黑名单文件夹失败: {str(e)}"
    
    def get_folder_hierarchy(self) -> List[Dict]:
        """获取文件夹层级关系（白名单+其下的黑名单）
        
        Returns:
            List[Dict]: 层级结构化的文件夹列表
        """
        try:
            # 获取所有一级文件夹：白名单文件夹 + 已转为黑名单的常用文件夹
            root_folders = self.session.exec(
                select(MyFiles).where(
                    and_(
                        # 要么是白名单文件夹，要么是已转为黑名单的常用文件夹
                        or_(
                            MyFiles.is_blacklist == False,
                            and_(MyFiles.is_blacklist == True, MyFiles.is_common_folder == True)
                        ),
                        # 都是一级文件夹
                        or_(MyFiles.parent_id.is_(None), MyFiles.parent_id == 0)
                    )
                ).order_by(MyFiles.created_at)
            ).all()
            
            hierarchy = []
            for folder in root_folders:
                # 获取此文件夹下的所有黑名单子文件夹（如果当前文件夹是白名单）
                black_children = []
                if not folder.is_blacklist:
                    black_children = self.session.exec(
                        select(MyFiles).where(
                            and_(
                                MyFiles.is_blacklist == True,
                                MyFiles.parent_id == folder.id
                            )
                        ).order_by(MyFiles.created_at)
                    ).all()
                
                folder_data = {
                    "id": folder.id,
                    "path": folder.path,
                    "alias": folder.alias,
                    "is_blacklist": folder.is_blacklist,
                    "is_common_folder": folder.is_common_folder,
                    "created_at": folder.created_at.isoformat() if folder.created_at else None,
                    "updated_at": folder.updated_at.isoformat() if folder.updated_at else None,
                    "blacklist_children": [
                        {
                            "id": black_child.id,
                            "path": black_child.path,
                            "alias": black_child.alias,
                            "is_blacklist": True,
                            "parent_id": black_child.parent_id,
                            "created_at": black_child.created_at.isoformat() if black_child.created_at else None,
                            "updated_at": black_child.updated_at.isoformat() if black_child.updated_at else None,
                        }
                        for black_child in black_children
                    ]
                }
                hierarchy.append(folder_data)
            
            return hierarchy
            
        except Exception as e:
            logger.error(f"获取文件夹层级关系失败: {str(e)}")
            return []
    
    # ========== Bundle扩展名管理方法 ==========
    
    def get_bundle_extensions(self, active_only: bool = True) -> List[BundleExtension]:
        """获取所有Bundle扩展名
        
        Args:
            active_only (bool): 是否只返回启用的扩展名
            
        Returns:
            List[BundleExtension]: Bundle扩展名列表
        """
        try:
            query = select(BundleExtension)
            if active_only:
                query = query.where(BundleExtension.is_active == True)
            
            return self.session.exec(query.order_by(BundleExtension.extension)).all()
        except Exception as e:
            logger.error(f"获取Bundle扩展名失败: {str(e)}")
            return []
    
    def add_bundle_extension(self, extension: str, description: str = None) -> Tuple[bool, Union[BundleExtension, str]]:
        """添加新的Bundle扩展名
        
        Args:
            extension (str): 扩展名（如.app）
            description (str, optional): 描述
            
        Returns:
            Tuple[bool, Union[BundleExtension, str]]: (成功标志, Bundle扩展名对象或错误消息)
        """
        try:
            # 标准化扩展名格式
            if not extension.startswith('.'):
                extension = '.' + extension
            
            # 检查是否已存在
            existing = self.session.exec(
                select(BundleExtension).where(BundleExtension.extension == extension)
            ).first()
            
            if existing:
                if existing.is_active:
                    return False, f"Bundle扩展名 {extension} 已存在"
                else:
                    # 重新激活已存在但被禁用的扩展名
                    existing.is_active = True
                    existing.updated_at = datetime.now()
                    if description:
                        existing.description = description
                    self.session.add(existing)
                    self.session.commit()
                    self.session.refresh(existing)
                    return True, existing
            
            # 创建新扩展名
            bundle_ext = BundleExtension(
                extension=extension,
                description=description or f"{extension} Bundle",
                is_active=True
            )
            
            self.session.add(bundle_ext)
            self.session.commit()
            self.session.refresh(bundle_ext)
            
            return True, bundle_ext
            
        except Exception as e:
            logger.error(f"添加Bundle扩展名失败: {str(e)}")
            self.session.rollback()
            return False, f"添加Bundle扩展名失败: {str(e)}"
    
    def remove_bundle_extension(self, extension_id: int) -> Tuple[bool, str]:
        """删除Bundle扩展名（设为不活跃）
        
        Args:
            extension_id (int): Bundle扩展名ID
            
        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        try:
            bundle_ext = self.session.get(BundleExtension, extension_id)
            if not bundle_ext:
                return False, f"Bundle扩展名ID不存在: {extension_id}"
            
            bundle_ext.is_active = False
            bundle_ext.updated_at = datetime.now()
            
            self.session.add(bundle_ext)
            self.session.commit()
            
            return True, f"Bundle扩展名 {bundle_ext.extension} 已禁用"
            
        except Exception as e:
            logger.error(f"删除Bundle扩展名失败: {str(e)}")
            self.session.rollback()
            return False, f"删除Bundle扩展名失败: {str(e)}"
    
    def get_bundle_extensions_for_rust(self) -> List[str]:
        """获取用于Rust端的Bundle扩展名列表
        
        Returns:
            List[str]: 扩展名字符串列表
        """
        try:
            extensions = self.get_bundle_extensions(active_only=True)
            return [ext.extension for ext in extensions]
        except Exception as e:
            logger.error(f"获取Rust端Bundle扩展名列表失败: {str(e)}")
            # 返回基本的默认扩展名作为备选
            return [".app", ".bundle", ".framework", ".fcpbundle", ".photoslibrary", ".imovielibrary"]


if __name__ == '__main__':
    # 测试代码
    from db_mgr import DBManager
    
    # 创建内存数据库用于测试
    engine = create_engine("sqlite:///:memory:")
    session = Session(engine)
    
    # 初始化数据库结构
    db_mgr = DBManager(session)
    db_mgr.init_db()
    
    # 测试文件管理器
    files_mgr = MyFilesManager(session)
    
    # 初始化默认文件夹
    files_mgr.initialize_default_directories()
    
    # 打印所有文件夹
    print("所有文件夹:")
    for directory in files_mgr.get_all_directories():
        print(f"- {directory.path} ({directory.alias or '无别名'})")
    
    # 测试添加文件夹
    home_dir = os.path.expanduser("~")
    success, msg = files_mgr.add_directory(os.path.join(home_dir, "Projects"), "我的项目")
    print(f"\n添加文件夹: {msg}")
    
    # 不再需要测试更新授权状态
    
    # 测试黑名单
    if files_mgr.get_all_directories():
        test_dir = files_mgr.get_all_directories()[0]
        success, msg = files_mgr.toggle_blacklist(test_dir.id, True)
        print(f"\n切换黑名单: {msg}")
    
    # 打印授权文件夹
    print("\n已授权文件夹:")
    for directory in files_mgr.get_authorized_directories():
        print(f"- {directory.path} ({directory.alias or '无别名'})")
    
    # 打印黑名单文件夹
    print("\n黑名单文件夹:")
    for directory in files_mgr.get_blacklist_directories():
        print(f"- {directory.path} ({directory.alias or '无别名'})")