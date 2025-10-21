#!/bin/bash

# 更新器测试配置管理脚本

TAURI_CONF="src-tauri/tauri.conf.json"

show_help() {
    echo "用法: $0 [dev|prod|show]"
    echo ""
    echo "选项:"
    echo "  dev   - 切换到开发环境 (使用本地 latest.json)"
    echo "  prod  - 切换到生产环境 (使用 GitHub releases)"
    echo "  show  - 显示当前配置"
    echo "  help  - 显示帮助信息"
}

show_current_config() {
    echo "当前更新器配置:"
    echo "=================="
    cat "$TAURI_CONF" | jq '.plugins.updater.endpoints' 2>/dev/null || echo "无法解析配置文件"
}

set_dev_config() {
    echo "切换到开发环境配置..."
    
    # 使用临时文件来修改配置
    tmp_file=$(mktemp)
    
    # 更新 endpoints 数组
    cat "$TAURI_CONF" | jq '.plugins.updater.endpoints = [
        "http://localhost:1420/latest.json",
        "https://github.com/huozhong-in/knowledge-focus/releases/latest/download/latest.json"
    ]' > "$tmp_file" && mv "$tmp_file" "$TAURI_CONF"
    
    echo "✅ 已切换到开发环境"
    echo "📝 现在会优先使用本地的 latest.json 进行测试"
}

set_prod_config() {
    echo "切换到生产环境配置..."
    
    # 使用临时文件来修改配置
    tmp_file=$(mktemp)
    
    # 更新 endpoints 数组
    cat "$TAURI_CONF" | jq '.plugins.updater.endpoints = [
        "https://github.com/huozhong-in/knowledge-focus/releases/latest/download/latest.json"
    ]' > "$tmp_file" && mv "$tmp_file" "$TAURI_CONF"
    
    echo "✅ 已切换到生产环境"
    echo "📝 现在只会使用 GitHub releases 进行更新"
}

case "$1" in
    "dev")
        set_dev_config
        show_current_config
        ;;
    "prod")
        set_prod_config
        show_current_config
        ;;
    "show")
        show_current_config
        ;;
    "help"|"")
        show_help
        ;;
    *)
        echo "❌ 未知参数: $1"
        show_help
        exit 1
        ;;
esac
