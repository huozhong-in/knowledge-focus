import psutil
import subprocess
import re
import platform
import logging
import os
import time
import signal
import tiktoken
from typing import Dict, Any

# 为当前模块创建专门的日志器（最佳实践）
logger = logging.getLogger()


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
        logger.info(f"查找可能的孤立 {process_name} 进程（函数: {function_name}）...")
        count = 0
        current_pid = os.getpid()
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'ppid']):
            try:
                # 跳过当前进程
                if proc.info['pid'] == current_pid:
                    continue
                    
                # 检查进程名
                if process_name.lower() in proc.info['name'].lower():
                    # 如果指定了函数名，检查命令行参数
                    if function_name is None or (
                        proc.info['cmdline'] and 
                        any(function_name in cmd for cmd in proc.info['cmdline'] if cmd)
                    ):
                        # 额外安全检查：确保不是系统关键进程
                        cmdline_str = ' '.join(proc.info['cmdline'] if proc.info['cmdline'] else [])
                        
                        # 检查是否包含我们的应用特征（更安全的匹配）
                        if any(pattern in cmdline_str for pattern in [
                            'task_processor', 
                            'high_priority_task_processor',
                            'knowledge-focus',
                            'main.py --host 127.0.0.1'
                        ]):
                            logger.info(f"发现可能的孤立进程: PID={proc.info['pid']}, PPID={proc.info['ppid']}, CMD={cmdline_str}")
                            
                            # 先尝试优雅终止，等待2秒
                            try:
                                proc.terminate()
                                proc.wait(timeout=2)
                                count += 1
                                logger.info(f"优雅终止进程 {proc.info['pid']} 成功")
                            except psutil.TimeoutExpired:
                                # 如果优雅终止超时，强制终止
                                try:
                                    proc.kill()
                                    count += 1
                                    logger.info(f"强制终止进程 {proc.info['pid']} 成功")
                                except Exception as kill_err:
                                    logger.error(f"无法强制终止进程 {proc.info['pid']}: {str(kill_err)}")
                            except psutil.NoSuchProcess:
                                # 进程已经不存在
                                count += 1
                            except Exception as term_err:
                                logger.error(f"无法终止进程 {proc.info['pid']}: {str(term_err)}")
                        
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        if count > 0:
            logger.info(f"已终止 {count} 个可能的孤立 {process_name} 进程")
        else:
            logger.info(f"未发现孤立的 {process_name} 进程")
            
    except Exception as e:
        logger.error(f"查找孤立进程时出错: {str(e)}", exc_info=True)

def monitor_parent():
    """Monitor the parent process and exit if it's gone"""
    parent_pid = os.getppid()
    logger.info(f"开始监控父进程 PID: {parent_pid}")
    
    while True:
        try:
            # Check if parent process still exists
            parent = psutil.Process(parent_pid)
            if not parent.is_running():
                logger.info(f"父进程 {parent_pid} 已终止，开始优雅关闭...")
                # 使用 SIGTERM 信号优雅关闭，让 lifespan 的 finally 块执行清理
                os.kill(os.getpid(), signal.SIGTERM)
                break
        except psutil.NoSuchProcess:
            logger.info(f"父进程 {parent_pid} 不存在，开始优雅关闭...")
            # 使用 SIGTERM 信号优雅关闭，让 lifespan 的 finally 块执行清理
            os.kill(os.getpid(), signal.SIGTERM)
            break
        except Exception as e:
            logger.error(f"监控父进程时发生错误: {e}")
        
        time.sleep(5)  # 降低监控频率到5秒，减少资源消耗
    
    logger.info("父进程监控线程已退出")

# copy & paste from https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
def num_tokens_from_string(string: str, encoding_name: str = "o200k_base") -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

def num_tokens_from_messages(messages, model="gpt-4o-mini-2024-07-18"):
    """Return the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        print("Warning: model not found. Using o200k_base encoding.")
        encoding = tiktoken.get_encoding("o200k_base")
    if model in {
        "gpt-3.5-turbo-0125",
        "gpt-4-0314",
        "gpt-4-32k-0314",
        "gpt-4-0613",
        "gpt-4-32k-0613",
        "gpt-4o-mini-2024-07-18",
        "gpt-4o-2024-08-06"
        }:
        tokens_per_message = 3
        tokens_per_name = 1
    elif "gpt-3.5-turbo" in model:
        print("Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-3.5-turbo-0125.")
        return num_tokens_from_messages(messages, model="gpt-3.5-turbo-0125")
    elif "gpt-4o-mini" in model:
        print("Warning: gpt-4o-mini may update over time. Returning num tokens assuming gpt-4o-mini-2024-07-18.")
        return num_tokens_from_messages(messages, model="gpt-4o-mini-2024-07-18")
    elif "gpt-4o" in model:
        print("Warning: gpt-4o and gpt-4o-mini may update over time. Returning num tokens assuming gpt-4o-2024-08-06.")
        return num_tokens_from_messages(messages, model="gpt-4o-2024-08-06")
    elif "gpt-4" in model:
        print("Warning: gpt-4 may update over time. Returning num tokens assuming gpt-4-0613.")
        return num_tokens_from_messages(messages, model="gpt-4-0613")
    else:
        raise NotImplementedError(
            f"""num_tokens_from_messages() is not implemented for model {model}."""
        )
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens

'''
总结：JSON字段操作的最佳实践
🔄 推荐的通用模式
1. 总是创建新字典实例：
new_data = dict(current_data)
new_data.update(changes)
obj.field = new_data

2. 总是使用flag_modified （保险做法）：
attributes.flag_modified(obj, 'field_name')

📋 何时必须使用
✅ 修改嵌套字典内容时
✅ 使用dict.update(), dict.pop(), dict.clear()等方法时
✅ 修改列表内元素时（如果JSON字段包含列表）
✅ 任何原地修改（in-place modification）操作

🎯 实际应用建议
对于您的项目，我建议：
1. 使用统一的辅助方法（已经实现）：

_update_json_field_safely() - 更新部分键值
_replace_json_field_safely() - 替换整个字段
_remove_json_keys_safely() - 删除特定键
2. 在所有JSON字段操作中都使用这些方法，这样能确保：

✅ 数据一致性
✅ 变化检测准确
✅ 代码可维护性高
'''

def update_json_field_safely(obj, field_name: str, updates: Dict[str, Any]) -> None:
    """
    安全地更新JSON字段，确保SQLAlchemy能正确检测到变化
    
    Args:
        obj: 数据库对象
        field_name: JSON字段名
        updates: 要更新的键值对
    """
    from sqlalchemy.orm import attributes
    
    # 获取当前JSON数据
    current_data = getattr(obj, field_name) or {}
    
    # 创建新的字典，包含更新
    new_data = dict(current_data)
    new_data.update(updates)
    
    # 设置新数据
    setattr(obj, field_name, new_data)
    
    # 显式标记字段已修改
    attributes.flag_modified(obj, field_name)

def replace_json_field_safely(obj, field_name: str, new_data: Dict[str, Any]) -> None:
    """
    安全地替换整个JSON字段
    
    Args:
        obj: 数据库对象
        field_name: JSON字段名
        new_data: 新的JSON数据
    """
    from sqlalchemy.orm import attributes
    
    # 替换整个字段
    setattr(obj, field_name, new_data)
    
    # 为了保险起见，仍然标记字段已修改
    attributes.flag_modified(obj, field_name)

def remove_json_keys_safely(obj, field_name: str, keys_to_remove: list) -> None:
    """
    安全地从JSON字段中删除指定键
    
    Args:
        obj: 数据库对象
        field_name: JSON字段名
        keys_to_remove: 要删除的键列表
    """
    from sqlalchemy.orm import attributes
    
    # 获取当前JSON数据
    current_data = getattr(obj, field_name) or {}
    
    # 创建新字典，排除要删除的键
    new_data = {k: v for k, v in current_data.items() if k not in keys_to_remove}
    
    # 设置新数据
    setattr(obj, field_name, new_data)
    
    # 显式标记字段已修改
    attributes.flag_modified(obj, field_name)