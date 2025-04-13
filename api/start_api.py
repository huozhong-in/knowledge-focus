"""
启动FastAPI服务的脚本，用于Tauri的sidecar调用
"""
import sys
import os
import subprocess

# 获取当前脚本所在目录
# Get the actual API directory path (not the execution directory)
api_dir = os.path.dirname(os.path.abspath(__file__))

# Set virtual environment path
venv_dir = os.path.join(api_dir, ".venv")
venv_python = os.path.join(venv_dir, "bin", "python")
print(f"虚拟环境路径: {venv_python}")

# Store current execution directory for reference
current_dir = api_dir
print(f"当前执行目录: {current_dir}")

def main():
    # 解析命令行参数
    port = 8000
    host = "127.0.0.1"
    
    # 检查命令行参数中是否有端口设置
    if len(sys.argv) > 1:
        for i, arg in enumerate(sys.argv[1:], 1):
            if arg == "--port" and i < len(sys.argv):
                try:
                    port = int(sys.argv[i+1])
                except (ValueError, IndexError):
                    pass
            elif arg == "--host" and i < len(sys.argv):
                host = sys.argv[i+1]
    
    # 构建命令，使用虚拟环境中的Python
    cmd = [venv_python, os.path.join(current_dir, "main.py"), 
           "--port", str(port), "--host", host]
    
    print(f"启动API服务: {' '.join(cmd)}")
    
    # 执行命令并保持输出流
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                              text=True, bufsize=1)
    
    # 实时输出日志
    for line in iter(process.stdout.readline, ''):
        print(line, end='', flush=True)
    
    process.stdout.close()
    return process.wait()

if __name__ == "__main__":
    sys.exit(main())