#!/bin/bash
# Knowledge Focus - 模型手动下载脚本
# 此脚本会自动下载 Qwen3-VL 4B 模型（2.61GB）
# 包含镜像切换和自动重试功能

set -e  # 遇到错误立即退出

echo "================================"
echo "Knowledge Focus 模型下载工具"
echo "================================"
echo ""

# 固定路径配置
APP_DATA_DIR="$HOME/Library/Application Support/knowledge-focus.huozhong.in"
MODEL_DIR="$APP_DATA_DIR/builtin_models"
DB_PATH="$APP_DATA_DIR/knowledge-focus.db"
UV_PATH="/Applications/KnowledgeFocus.app/Contents/MacOS/uv"
API_DIR="/Applications/KnowledgeFocus.app/Contents/Resources/api"
# 开发和测试配置
# UV_PATH="~/workspace/knowledge-focus/tauri-app/src-tauri/bin/uv-aarch64-apple-darwin"
# API_DIR="~/workspace/knowledge-focus/api"

echo "📁 模型将下载到："
echo "   $MODEL_DIR"
echo ""

# 创建目录
mkdir -p "$MODEL_DIR"

# 检查网络连接
echo "🌐 检查网络连接..."
if ! ping -c 1 8.8.8.8 &> /dev/null; then
    echo "❌ 网络连接失败，请检查网络后重试"
    exit 1
fi

echo "✅ 网络连接正常"
echo ""

# 定义镜像列表
declare -a MIRRORS=(
    "https://huggingface.co|HuggingFace 官方"
    "https://hf-mirror.com|HF-Mirror 国内镜像"
)

# 定义下载函数
download_model() {
    local endpoint=$1
    local mirror_name=$2
    
    echo "📦 尝试从 ${mirror_name} 下载..."
    echo "   地址: ${endpoint}"
    echo ""
    
    # 设置环境变量指定镜像和数据目录
    export HF_ENDPOINT="${endpoint}"
    export KF_DATA_DIR="$APP_DATA_DIR"
    
    # 调用 Python 下载脚本（使用独立的 CLI 脚本）
    "$UV_PATH" run \
      --directory "$API_DIR" \
      python download_model_cli.py
}

# 尝试所有镜像，每个镜像最多重试 2 次
SUCCESS=false

for mirror_info in "${MIRRORS[@]}"; do
    IFS='|' read -r endpoint mirror_name <<< "$mirror_info"
    
    for attempt in {1..2}; do
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "尝试 ${attempt}/2 - ${mirror_name}"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        
        if download_model "${endpoint}" "${mirror_name}"; then
            SUCCESS=true
            break 2
        else
            echo ""
            echo "⚠️  尝试失败"
            if [ $attempt -lt 2 ]; then
                echo "等待 3 秒后重试..."
                sleep 3
            else
                echo "此镜像所有尝试均失败，切换到下一个镜像..."
                echo ""
            fi
        fi
    done
done

if [ "$SUCCESS" = true ]; then
    echo ""
    echo "================================"
    echo "✅ 全部完成！"
    echo "请完全退出 Knowledge Focus 并重新启动。"
    echo "================================"
else
    echo ""
    echo "================================"
    echo "❌ 所有镜像下载均失败"
    echo ""
    echo "请尝试："
    echo "1. 检查网络连接"
    echo "2. 使用 VPN（如果在中国大陆）"
    echo "3. 查看文档: https://kf.huozhong.in/docs"
    echo "4. 报告问题: https://github.com/huozhong-in/knowledge-focus/issues"
    echo "================================"
    exit 1
fi
