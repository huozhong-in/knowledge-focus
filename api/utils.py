import psutil
import subprocess
import re
import platform
import logging
import os
import time
import signal
import sys

# 为当前模块创建专门的日志器（最佳实践）
logger = logging.getLogger(__name__)


def kill_process_on_port(port):
    # 检测操作系统类型
    system_platform = platform.system()
    
    if system_platform == "Windows":
        return kill_process_on_port_windows(port)
    else:  # macOS 或 Linux
        return kill_process_on_port_unix(port)

def kill_process_on_port_windows(port):
    try:
        # 在Windows上使用netstat命令查找占用端口的进程
        cmd = f"netstat -ano | findstr :{port} | findstr LISTENING"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0 and result.stdout.strip():
            # 使用正则表达式提取PID
            pid_match = re.search(r'\s+(\d+)$', result.stdout.strip())
            if pid_match:
                pid = int(pid_match.group(1))
                
                # 获取进程名称
                try:
                    process = psutil.Process(pid)
                    process_name = process.name()
                except psutil.NoSuchProcess:
                    process_name = "未知进程"
                
                logger.info(f"发现端口 {port} 被进程 {pid} ({process_name}) 占用，正在终止...")

                # 终止所有子进程
                kill_all_child_processes(pid)
                
                # 使用taskkill命令终止进程
                kill_cmd = f"taskkill /PID {pid} /F"
                kill_result = subprocess.run(kill_cmd, shell=True)
                
                if kill_result.returncode == 0:
                    logger.info(f"已终止占用端口 {port} 的进程")
                    # 等待短暂时间确保端口释放
                    import time
                    time.sleep(1)
                    return True
                else:
                    logger.error(f"无法终止进程 {pid}，可能需要管理员权限")
            else:
                logger.warning(f"找到端口 {port} 的占用，但无法确定进程PID")
        else:
            # 没有找到占用端口的进程
            return False
    except Exception as e:
        logger.error(f"检查端口时发生错误: {str(e)}")
    
    return False

def kill_process_on_port_unix(port):
    # 尝试使用命令行工具获取占用端口的进程
    try:
        # 在macOS/Linux上使用lsof命令
        cmd = f"lsof -i :{port} -sTCP:LISTEN -t"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0 and result.stdout.strip():
            # 获取PID
            pid = result.stdout.strip()
            # 如果有多行，只取第一行
            if '\n' in pid:
                pid = pid.split('\n')[0]
            
            pid = int(pid)
            # 获取进程名称
            try:
                process = psutil.Process(pid)
                process_name = process.name()
            except psutil.NoSuchProcess:
                process_name = "未知进程"
            
            logger.info(f"发现端口 {port} 被进程 {pid} ({process_name}) 占用，正在终止...")
            
            # 终止所有子进程
            kill_all_child_processes(pid)
            
            # 使用kill命令终止进程
            kill_cmd = f"kill {pid}"
            kill_result = subprocess.run(kill_cmd, shell=True)
            
            if kill_result.returncode == 0:
                logger.info(f"已终止占用端口 {port} 的进程")
                return True
            else:
                # 如果普通终止失败，可以尝试强制终止
                logger.info("进程没有响应终止信号，尝试强制终止...")
                force_kill_cmd = f"kill -9 {pid}"
                force_kill_result = subprocess.run(force_kill_cmd, shell=True)
                
                if force_kill_result.returncode == 0:
                    logger.info(f"已强制终止占用端口 {port} 的进程")
                    return True
                else:
                    logger.info(f"无法终止进程 {pid}，可能需要管理员权限")
        else:
            # 如果lsof没有找到占用端口的进程
            # 尝试查找并终止所有Python进程中的潜在子进程
            kill_orphaned_processes("python", "task_processor")
            return False
    except Exception as e:
        logger.info(f"检查端口时发生错误: {str(e)}")
    
    return False

def kill_all_child_processes(parent_pid):
    """递归终止指定进程及其所有子进程"""
    try:
        parent = psutil.Process(parent_pid)
        children = parent.children(recursive=True)
        
        for child in children:
            try:
                # 记录子进程信息
                logger.info(f"终止子进程: {child.pid} ({child.name()})")
                # 先尝试正常终止
                child.terminate()
            except psutil.NoSuchProcess:
                pass
            try:
                # 如果正常终止失败，强制终止
                logger.info(f"强制终止子进程: {child.pid}")
                child.kill()
            except psutil.NoSuchProcess:
                    logger.error(f"无法终止子进程 {child.pid}")
        
        # 等待短暂时间让子进程有时间终止
        psutil.wait_procs(children, timeout=3)
        
        # 检查是否有子进程仍然存活，再次尝试强制终止
        for child in children:
            if child.is_running():
                logger.warning(f"子进程 {child.pid} 仍然活着，再次尝试强制终止")
                try:
                    os.kill(child.pid, signal.SIGKILL)
                except psutil.NoSuchProcess:
                    pass
    except Exception as e:
        logger.error(f"终止子进程时出错: {str(e)}")

def kill_orphaned_processes(process_name, function_name=None):
    """终止可能是孤立子进程的进程
    
    Args:
        process_name: 进程名称 (例如: "python")
        function_name: 可选参数，进程中可能包含的函数名 (例如: "task_processor")
    """
    try:
        logger.info(f"查找可能的孤立 {process_name} 进程...")
        count = 0
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                # 检查进程名
                if process_name.lower() in proc.info['name'].lower():
                    # 如果指定了函数名，检查命令行参数
                    if function_name is None or (
                        proc.info['cmdline'] and 
                        any(function_name in cmd for cmd in proc.info['cmdline'] if cmd)
                    ):
                        logger.info(f"发现可能的孤立进程: {proc.info['pid']} {' '.join(proc.info['cmdline'] if proc.info['cmdline'] else [])}")
                        
                        # 终止该进程
                        try:
                            proc.terminate()
                            count += 1
                        except psutil.NoSuchProcess:
                            try:
                                proc.kill()
                                count += 1
                            except Exception as e:
                                logger.error(f"无法终止进程 {proc.info['pid']}: {str(e)}")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        if count > 0:
            logger.info(f"已终止 {count} 个可能的孤立 {process_name} 进程")
        else:
            logger.info(f"未发现孤立的 {process_name} 进程")
            
    except Exception as e:
        logger.error(f"查找孤立进程时出错: {str(e)}")

def monitor_parent():
    """Monitor the parent process and exit if it's gone"""
    parent_pid = os.getppid()
    print(f"Parent PID: {parent_pid}")
    
    while True:
        try:
            # Check if parent process still exists
            parent = psutil.Process(parent_pid)
            if not parent.is_running():
                print("Parent process terminated, shutting down...")
                os.kill(os.getpid(), signal.SIGTERM)
                sys.exit(0)
        except psutil.NoSuchProcess:
            print("Parent process no longer exists, shutting down...")
            os.kill(os.getpid(), signal.SIGTERM)
            sys.exit(0)
        
        time.sleep(2)