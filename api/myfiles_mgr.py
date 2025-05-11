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
from db_mgr import MyFiles, AuthStatus
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
        
        Returns:
            List[Dict[str, str]]: 包含文件夹名称和路径的字典列表
        """
        dirs = []
        
        if self.system == "Darwin":  # macOS
            home_dir = os.path.expanduser("~")
            dirs = [
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
                dirs = [
                    {"name": "桌面", "path": os.path.join(home_dir, "Desktop")},
                    {"name": "文档", "path": os.path.join(home_dir, "Documents")},
                    {"name": "下载", "path": os.path.join(home_dir, "Downloads")},
                    {"name": "图片", "path": os.path.join(home_dir, "Pictures")},
                    {"name": "音乐", "path": os.path.join(home_dir, "Music")},
                    {"name": "视频", "path": os.path.join(home_dir, "Videos")},
                ]
                
                # 添加Windows特有的文件夹（如OneDrive）
                onedrive_dir = os.environ.get("OneDriveConsumer") or os.environ.get("OneDrive")
                if onedrive_dir:
                    dirs.append({"name": "OneDrive", "path": onedrive_dir})
        
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
                    auth_status=AuthStatus.PENDING.value,
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
        """获取所有已授权的文件夹
        
        Returns:
            List[MyFiles]: 已授权的文件夹记录列表
        """
        return self.session.exec(
            select(MyFiles).where(
                and_(
                    MyFiles.auth_status == AuthStatus.AUTHORIZED.value,
                    MyFiles.is_blacklist == False
                )
            )
        ).all()
    
    def get_pending_directories(self) -> List[MyFiles]:
        """获取所有待授权的文件夹
        
        Returns:
            List[MyFiles]: 待授权的文件夹记录列表
        """
        return self.session.exec(
            select(MyFiles).where(MyFiles.auth_status == AuthStatus.PENDING.value)
        ).all()
    
    def get_blacklist_directories(self) -> List[MyFiles]:
        """获取所有黑名单文件夹
        
        Returns:
            List[MyFiles]: 黑名单文件夹记录列表
        """
        return self.session.exec(
            select(MyFiles).where(MyFiles.is_blacklist == True)
        ).all()

    def add_directory(self, path: str, alias: Optional[str] = None) -> Tuple[bool, Union[MyFiles, str]]:
        """添加新文件夹
        
        Args:
            path (str): 文件夹路径
            alias (Optional[str], optional): 文件夹别名. Defaults to None.
        
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
            auth_status=AuthStatus.PENDING.value,
            is_blacklist=False
        )
        
        self.session.add(new_file)
        self.session.commit()
        self.session.refresh(new_file)  # 刷新以获取完整对象
        
        return True, new_file
    
    def update_auth_status(self, directory_id: int, status: AuthStatus) -> Tuple[bool, MyFiles | str]:
        """更新文件夹的授权状态

        Args:
            directory_id (int): 文件夹的ID
            status (AuthStatus): 新的授权状态

        Returns:
            Tuple[bool, MyFiles | str]: (成功标志, 更新后的文件夹对象或错误消息)
        """
        directory = self.session.get(MyFiles, directory_id)
        if not directory:
            return False, f"文件夹ID不存在: {directory_id}"

        directory.auth_status = status.value
        directory.updated_at = datetime.now()
        self.session.add(directory)
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
        """从数据库中删除文件夹记录
        
        Args:
            directory_id (int): 文件夹的ID
        
        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        # 查找记录
        directory = self.session.get(MyFiles, directory_id)
        
        if not directory:
            return False, f"文件夹ID不存在: {directory_id}"
            
        # 删除记录
        deleted_path = directory.path # 保存路径用于日志或消息
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
        
        # 如果路径存在于数据库，检查是否已授权
        if directory:
            return directory.auth_status == AuthStatus.AUTHORIZED.value
        
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
    
    def is_path_in_blacklist(self, path: str) -> bool:
        """检查路径是否在黑名单中
        
        Args:
            path (str): 要检查的路径
        
        Returns:
            bool: 如果路径在黑名单中则返回True，否则返回False
        """
        # 标准化路径
        path = os.path.normpath(path)
        
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
            
            # 如果成功读取，更新授权状态
            directory.auth_status = AuthStatus.AUTHORIZED.value
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
        print(f"- {directory.path} ({directory.alias or '无别名'}): {directory.auth_status}")
    
    # 测试添加文件夹
    home_dir = os.path.expanduser("~")
    success, msg = files_mgr.add_directory(os.path.join(home_dir, "Projects"), "我的项目")
    print(f"\n添加文件夹: {msg}")
    
    # 测试更新授权状态
    for directory in files_mgr.get_pending_directories()[:2]:
        success, msg = files_mgr.update_auth_status(directory.id, AuthStatus.AUTHORIZED)
        print(f"更新授权状态: {msg}")
    
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