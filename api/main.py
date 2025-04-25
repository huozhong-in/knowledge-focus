from fastapi import FastAPI, Body
from typing import List
import uvicorn
import argparse
import os
import psutil
import time
import subprocess
import re
import platform

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
                except:
                    process_name = "未知进程"
                
                print(f"发现端口 {port} 被进程 {pid} ({process_name}) 占用，正在终止...")
                
                # 使用taskkill命令终止进程
                kill_cmd = f"taskkill /PID {pid} /F"
                kill_result = subprocess.run(kill_cmd, shell=True)
                
                if kill_result.returncode == 0:
                    print(f"已终止占用端口 {port} 的进程")
                    # 等待短暂时间确保端口释放
                    import time
                    time.sleep(1)
                    return True
                else:
                    print(f"无法终止进程 {pid}，可能需要管理员权限")
            else:
                print(f"找到端口 {port} 的占用，但无法确定进程PID")
        else:
            # 没有找到占用端口的进程
            return False
    except Exception as e:
        print(f"检查端口时发生错误: {str(e)}")
    
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
            except:
                process_name = "未知进程"
            
            print(f"发现端口 {port} 被进程 {pid} ({process_name}) 占用，正在终止...")
            
            # 使用kill命令终止进程
            kill_cmd = f"kill {pid}"
            kill_result = subprocess.run(kill_cmd, shell=True)
            
            if kill_result.returncode == 0:
                print(f"已终止占用端口 {port} 的进程")
                return True
            else:
                # 如果普通终止失败，可以尝试强制终止
                print(f"进程没有响应终止信号，尝试强制终止...")
                force_kill_cmd = f"kill -9 {pid}"
                force_kill_result = subprocess.run(force_kill_cmd, shell=True)
                
                if force_kill_result.returncode == 0:
                    print(f"已强制终止占用端口 {port} 的进程")
                    return True
                else:
                    print(f"无法终止进程 {pid}，可能需要管理员权限")
        else:
            # 如果lsof没有找到占用端口的进程
            return False
    except Exception as e:
        print(f"检查端口时发生错误: {str(e)}")
    
    return False

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: str = None):
    return {"item_id": item_id, "q": q}

# 读取给定绝对路径的文件内容
@app.post("/file-content")
def read_file_content(file_paths: List[str] = Body(...)):
    results = []
    for file_path in file_paths:
        try:
            if not os.path.exists(file_path):
                results.append({
                    "path": file_path,
                    "success": False,
                    "error": "文件不存在",
                    "content": None
                })
                continue
                
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                results.append({
                    "path": file_path,
                    "success": True,
                    "error": None,
                    "content": content
                })
        except Exception as e:
            results.append({
                "path": file_path,
                "success": False,
                "error": str(e),
                "content": None
            })
    
    return {"results": results}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=60000, help="API服务监听端口")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="API服务监听地址")
    args = parser.parse_args()
    
    # 检查端口是否被占用，如果被占用则终止占用进程
    kill_process_on_port(args.port)
    time.sleep(2)  # 等待端口释放
    
    print(f"API服务启动在: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)