#!/usr/bin/env python3
"""
模型下载命令行工具
用于从终端手动下载模型，支持通过 HF_ENDPOINT 环境变量指定镜像
"""
import os
import sys
from models_builtin import ModelsBuiltin
from sqlmodel import create_engine

def main():
    # 从环境变量获取数据目录（如果有的话）
    app_data_dir = os.environ.get(
        'KF_DATA_DIR',
        os.path.expanduser('~/Library/Application Support/knowledge-focus.huozhong.in')
    )
    
    db_path = os.path.join(app_data_dir, 'knowledge-focus.db')
    
    try:
        engine = create_engine(f'sqlite:///{db_path}')
        mgr = ModelsBuiltin(engine=engine, base_dir=app_data_dir)
        
        # 获取当前使用的镜像端点
        endpoint = os.environ.get('HF_ENDPOINT', 'https://huggingface.co')
        print(f'🔗 使用端点: {endpoint}')
        print('')
        print('开始下载 Qwen3-VL 4B 模型...')
        
        local_path = mgr.download_model('qwen3-vl-4b')
        
        print('')
        print('✅ 下载完成！')
        print(f'   路径: {local_path}')
        print('')
        
    except Exception as e:
        print(f'❌ 下载失败: {e}', file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
