#!/usr/bin/env python3
"""
自动生成 latest.json 文件的 Python 脚本
使用方法: python generate-latest-json.py [version] [release_notes]
"""

import json
import sys
import re
from datetime import datetime
from pathlib import Path

def read_version_from_tauri_config():
    """从 tauri.conf.json 读取版本号"""
    try:
        config_path = Path("src-tauri/tauri.conf.json")
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 使用正则表达式提取版本号
                match = re.search(r'"version"\s*:\s*"([^"]+)"', content)
                if match:
                    return match.group(1)
    except Exception as e:
        print(f"❌ 读取 tauri.conf.json 失败: {e}")
    return None

def main():
    # 配置
    REPO_OWNER = "huozhong-in"
    REPO_NAME = "knowledge-focus"
    
    # 获取参数
    version = sys.argv[1] if len(sys.argv) > 1 else read_version_from_tauri_config()
    if not version:
        print("❌ 错误: 无法获取版本号")
        print("   使用方法: python generate-latest-json.py [version] [release_notes]")
        sys.exit(1)
    
    release_notes = sys.argv[2] if len(sys.argv) > 2 else f"更新到版本 {version}"
    
    print(f"🔄 生成 latest.json for version: {version}")
    
    # 构建文件路径
    bundle_dir = Path("src-tauri/target/release/bundle/macos")
    app_tar_gz = bundle_dir / "KnowledgeFocus.app.tar.gz"
    app_sig = bundle_dir / "KnowledgeFocus.app.tar.gz.sig"
    
    # 检查文件是否存在
    if not app_tar_gz.exists():
        print(f"❌ 错误: 找不到 {app_tar_gz}")
        print("   请先运行: ./build.sh")
        sys.exit(1)
    
    if not app_sig.exists():
        print(f"❌ 错误: 找不到 {app_sig}")
        print("   请先运行: ./build.sh")
        sys.exit(1)
    
    # 读取签名文件内容
    try:
        with open(app_sig, 'r', encoding='utf-8') as f:
            signature = f.read().strip()
    except Exception as e:
        print(f"❌ 错误: 读取签名文件失败: {e}")
        sys.exit(1)
    
    # 生成当前时间戳 (RFC 3339 格式)
    from datetime import timezone
    pub_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 生成 latest.json 数据结构 (Tauri updater 格式)
    latest_data = {
        "version": version,
        "notes": release_notes,
        "pub_date": pub_date,
        "url": f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/v{version}/KnowledgeFocus.app.tar.gz",
        "signature": signature
    }
    
    # 写入 latest.json 文件
    try:
        with open("latest.json", 'w', encoding='utf-8') as f:
            json.dump(latest_data, f, indent=2, ensure_ascii=False)
        
        print("✅ 生成完成: latest.json")
        print("")
        print("📋 接下来请按照以下步骤发布:")
        print("1. 在 GitHub 上创建新的 Release")
        print(f"2. 创建 tag: v{version}")
        print("3. 上传以下文件:")
        print(f"   - {app_tar_gz}")
        print("   - latest.json")
        print("")
        print("📄 生成的 latest.json 内容:")
        print(json.dumps(latest_data, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"❌ 错误: 写入 latest.json 失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
