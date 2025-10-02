#!/bin/bash

# Knowledge Focus Auth Server - Cloudflare D1 数据库初始化脚本
# 用于在 Cloudflare D1 中创建 Better-Auth 所需的表

set -e

echo "🗄️  Knowledge Focus Auth Server - D1 Database Setup"
echo "=================================================="
echo ""

# 检查 wrangler 是否已安装
if ! command -v wrangler &> /dev/null; then
    echo "❌ Error: wrangler CLI not found"
    echo "   Please install: npm install -g wrangler"
    exit 1
fi

# 检查迁移文件是否存在
MIGRATION_FILE="./migrations/0001_create_better_auth_tables.sql"
if [ ! -f "$MIGRATION_FILE" ]; then
    echo "❌ Error: Migration file not found: $MIGRATION_FILE"
    exit 1
fi

# 数据库名称 (从 wrangler.jsonc 读取)
DB_NAME="knowledge-focus-db"

echo "📋 Database: $DB_NAME"
echo ""

# 询问用户是否要继续
read -p "This will execute the migration on the REMOTE D1 database. Continue? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Aborted"
    exit 1
fi

echo ""
echo "🔄 Executing migration..."
echo ""

# 执行迁移
wrangler d1 execute $DB_NAME --remote --file=$MIGRATION_FILE

echo ""
echo "✅ Migration completed!"
echo ""

# 验证表是否创建成功
echo "🔍 Verifying tables..."
echo ""

wrangler d1 execute $DB_NAME --remote --command="SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"

echo ""
echo "🎉 D1 database setup complete!"
echo ""
echo "Next steps:"
echo "  1. Configure secrets: wrangler secret put <SECRET_NAME>"
echo "  2. Build the project: bun run build"
echo "  3. Deploy to Cloudflare Pages: wrangler pages deploy dist"
echo ""
