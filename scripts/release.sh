#!/bin/bash

# 发布脚本 - 自动化版本发布流程
# 用法: ./scripts/release.sh 0.3.4 "修复了XXX问题"

set -e

if [ $# -ne 2 ]; then
    echo "用法: $0 <版本号> <发布说明>"
    echo "示例: $0 0.3.4 \"修复了XXX问题，新增了YYY功能\""
    exit 1
fi

VERSION=$1
RELEASE_NOTES=$2

echo "🚀 开始发布流程 v$VERSION"

# 1. 检查是否在 main 分支
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "❌ 错误: 请在 main 分支上执行发布"
    echo "当前分支: $CURRENT_BRANCH"
    exit 1
fi

# 2. 检查工作区是否干净
if [ -n "$(git status --porcelain)" ]; then
    echo "❌ 错误: 工作区有未提交的更改，请先提交或暂存"
    git status --short
    exit 1
fi

# 3. 更新版本号到 tauri.conf.json
echo "📝 更新版本号到 $VERSION"
sed -i.bak "s/\"version\": \".*\"/\"version\": \"$VERSION\"/" tauri-app/src-tauri/tauri.conf.json
rm tauri-app/src-tauri/tauri.conf.json.bak

# 4. 同步版本号到前端
echo "🔄 同步版本号到前端"
cd tauri-app
bash scripts/sync-version.sh
cd ..

# 5. 提交更改
echo "💾 提交版本更新"
git add .
git commit -m "release: bump version to $VERSION

$RELEASE_NOTES"

# 6. 创建标签
echo "🏷️  创建标签 v$VERSION"
git tag "v$VERSION"

# 7. 推送
echo "📤 推送代码和标签"
git push origin main
git push origin "v$VERSION"

echo "✅ 发布流程完成!"
echo "🔗 查看构建进度: https://github.com/huozhong-in/knowledge-focus/actions"
echo "📦 发布完成后记得在GitHub上发布Draft Release"