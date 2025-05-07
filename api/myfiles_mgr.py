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
from typing import Dict, List, Optional, Tuple, Set
import os
import platform
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class MyFilesManager:
    """文件/文件夹资源管理、授权状态管理类
    
    负责:
    1. 管理用户授权的文件夹列表
    2. 维护常用目录的授权状态
    3. 管理黑名单功能
    4. 提供跨平台(macOS/Windows)的文件路径处理
    """
    def __init__(self, session: Session) -> None:
        self.session = session
        self.system = platform.system()  # 'Darwin' for macOS, 'Windows' for Windows
    
    def get_default_directories(self) -> List[Dict[str, str]]:
        """获取系统默认常用目录，根据操作系统返回不同的目录列表
        
        Returns:
            List[Dict[str, str]]: 包含目录名称和路径的字典列表
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
            # Windows系统使用USERPROFILE环境变量获取用户主目录
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
                
                # 添加Windows特有的目录（如OneDrive）
                onedrive_dir = os.environ.get("OneDriveConsumer") or os.environ.get("OneDrive")
                if onedrive_dir:
                    dirs.append({"name": "OneDrive", "path": onedrive_dir})
        
        return dirs
    
    def initialize_default_directories(self) -> None:
        """初始化默认目录到数据库
        
        如果数据库中不存在这些目录记录，将它们添加进去
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
            logger.info(f"已初始化 {len(new_records)} 个默认目录")
    
    def get_all_directories(self) -> List[MyFiles]:
        """获取所有目录记录
        
        Returns:
            List[MyFiles]: 所有目录记录列表
        """
        return self.session.exec(select(MyFiles)).all()
    
    def get_authorized_directories(self) -> List[MyFiles]:
        """获取所有已授权的目录
        
        Returns:
            List[MyFiles]: 已授权的目录记录列表
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
        """获取所有待授权的目录
        
        Returns:
            List[MyFiles]: 待授权的目录记录列表
        """
        return self.session.exec(
            select(MyFiles).where(MyFiles.auth_status == AuthStatus.PENDING.value)
        ).all()
    
    def get_blacklist_directories(self) -> List[MyFiles]:
        """获取所有黑名单目录
        
        Returns:
            List[MyFiles]: 黑名单目录记录列表
        """
        return self.session.exec(
            select(MyFiles).where(MyFiles.is_blacklist == True)
        ).all()

    def add_directory(self, path: str, alias: Optional[str] = None) -> Tuple[bool, str]:
        """添加新目录
        
        Args:
            path (str): 目录路径
            alias (Optional[str], optional): 目录别名. Defaults to None.
        
        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        # 标准化路径
        path = os.path.normpath(path)
        
        # 检查路径是否存在
        if not os.path.exists(path):
            return False, f"路径不存在: {path}"
            
        # 检查是否为目录
        if not os.path.isdir(path):
            return False, f"不是有效的目录: {path}"
            
        # 检查记录是否已存在
        existing = self.session.exec(
            select(MyFiles).where(MyFiles.path == path)
        ).first()
        
        if existing:
            return False, f"目录已存在: {path}"
            
        # 添加新记录
        new_file = MyFiles(
            path=path,
            alias=alias,
            auth_status=AuthStatus.PENDING.value,
            is_blacklist=False
        )
        
        self.session.add(new_file)
        self.session.commit()
        
        return True, f"成功添加目录: {path}"
    
    def update_auth_status(self, path: str, status: AuthStatus) -> Tuple[bool, str]:
        """更新目录的授权状态
        
        Args:
            path (str): 目录路径
            status (AuthStatus): 新的授权状态
        
        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        # 标准化路径
        path = os.path.normpath(path)
        
        # 查找记录
        directory = self.session.exec(
            select(MyFiles).where(MyFiles.path == path)
        ).first()
        
        if not directory:
            return False, f"目录不存在: {path}"
            
        # 更新状态
        directory.auth_status = status.value
        directory.updated_at = datetime.now()
        self.session.add(directory)
        self.session.commit()
        
        return True, f"成功更新目录状态: {path} -> {status.value}"
    
    def toggle_blacklist(self, path: str, is_blacklist: bool) -> Tuple[bool, str]:
        """切换目录的黑名单状态
        
        Args:
            path (str): 目录路径
            is_blacklist (bool): 是否加入黑名单
        
        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        # 标准化路径
        path = os.path.normpath(path)
        
        # 查找记录
        directory = self.session.exec(
            select(MyFiles).where(MyFiles.path == path)
        ).first()
        
        if not directory:
            return False, f"目录不存在: {path}"
            
        # 更新黑名单状态
        directory.is_blacklist = is_blacklist
        directory.updated_at = datetime.now()
        self.session.add(directory)
        self.session.commit()
        
        action = "加入" if is_blacklist else "移出"
        return True, f"成功{action}黑名单: {path}"
    
    def remove_directory(self, path: str) -> Tuple[bool, str]:
        """从数据库中删除目录记录
        
        Args:
            path (str): 目录路径
        
        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        # 标准化路径
        path = os.path.normpath(path)
        
        # 查找记录
        directory = self.session.exec(
            select(MyFiles).where(MyFiles.path == path)
        ).first()
        
        if not directory:
            return False, f"目录不存在: {path}"
            
        # 删除记录
        self.session.delete(directory)
        self.session.commit()
        
        return True, f"成功删除目录: {path}"
    
    def update_alias(self, path: str, alias: str) -> Tuple[bool, str]:
        """更新目录别名
        
        Args:
            path (str): 目录路径
            alias (str): 新别名
        
        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        # 标准化路径
        path = os.path.normpath(path)
        
        # 查找记录
        directory = self.session.exec(
            select(MyFiles).where(MyFiles.path == path)
        ).first()
        
        if not directory:
            return False, f"目录不存在: {path}"
            
        # 更新别名
        directory.alias = alias
        directory.updated_at = datetime.now()
        self.session.add(directory)
        self.session.commit()
        
        return True, f"成功更新目录别名: {path} -> {alias}"
    
    def is_path_monitored(self, path: str) -> bool:
        """检查路径是否被监控（已授权且不在黑名单中）
        
        Args:
            path (str): 要检查的路径
        
        Returns:
            bool: 如果路径被监控则返回True，否则返回False
        """
        # 标准化路径
        path = os.path.normpath(path)
        
        # 检查路径是否在已授权的目录中，且不在黑名单中
        directory = self.session.exec(
            select(MyFiles).where(
                and_(
                    MyFiles.path == path,
                    MyFiles.auth_status == AuthStatus.AUTHORIZED.value,
                    MyFiles.is_blacklist == False
                )
            )
        ).first()
        
        return directory is not None
    
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
            
        # 检查路径是否是黑名单目录的子目录
        blacklist_dirs = self.get_blacklist_directories()
        path_obj = Path(path)
        
        for black_dir in blacklist_dirs:
            black_path = Path(black_dir.path)
            # 检查path是否是black_path的子目录
            try:
                _ = path_obj.relative_to(black_path)
                return True
            except ValueError:
                continue
                
        return False
    
    def check_authorization_needed(self) -> List[Dict]:
        """检查需要授权的目录
        
        Returns:
            List[Dict]: 包含需要授权的目录信息的字典列表
        """
        pending_dirs = self.get_pending_directories()
        result = []
        
        for directory in pending_dirs:
            # 检查目录是否存在
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
            "full_disk_access": "需要在'系统设置'>'隐私与安全性'>'完全磁盘访问权限'中授权，才能读取非标准目录",
            "docs_desktop_downloads": "需要在'系统设置'>'隐私与安全性'>'文件与文件夹'中授权读取这些目录",
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
    
    # 初始化默认目录
    files_mgr.initialize_default_directories()
    
    # 打印所有目录
    print("所有目录:")
    for directory in files_mgr.get_all_directories():
        print(f"- {directory.path} ({directory.alias or '无别名'}): {directory.auth_status}")
    
    # 测试添加目录
    home_dir = os.path.expanduser("~")
    success, msg = files_mgr.add_directory(os.path.join(home_dir, "Projects"), "我的项目")
    print(f"\n添加目录: {msg}")
    
    # 测试更新授权状态
    for directory in files_mgr.get_pending_directories()[:2]:
        success, msg = files_mgr.update_auth_status(directory.path, AuthStatus.AUTHORIZED)
        print(f"更新授权状态: {msg}")
    
    # 测试黑名单
    if files_mgr.get_all_directories():
        test_dir = files_mgr.get_all_directories()[0]
        success, msg = files_mgr.toggle_blacklist(test_dir.path, True)
        print(f"\n切换黑名单: {msg}")
    
    # 打印授权目录
    print("\n已授权目录:")
    for directory in files_mgr.get_authorized_directories():
        print(f"- {directory.path} ({directory.alias or '无别名'})")
    
    # 打印黑名单目录
    print("\n黑名单目录:")
    for directory in files_mgr.get_blacklist_directories():
        print(f"- {directory.path} ({directory.alias or '无别名'})")