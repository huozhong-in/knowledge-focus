# Knowledge Focus Auth Server

Better-Auth OAuth 认证服务器,支持 Google 和 GitHub 社交登录。

## 🏗️ 架构

- **开发环境**: Bun + Vite + better-sqlite3
- **生产环境**: Cloudflare Pages + D1 (SQLite)
- **认证**: Better-Auth with OAuth 2.0
- **ORM**: Drizzle ORM

## 🚀 快速开始

### 开发环境

\`\`\`bash
# 安装依赖
bun install

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 OAuth 凭证

# 启动开发服务器
bun run dev
\`\`\`

服务器运行在: \`http://127.0.0.1:60325\`

### 生产环境

参考: [QUICKSTART.md](./QUICKSTART.md) 或 [DEPLOYMENT.md](./DEPLOYMENT.md)

## 📁 项目结构

\`\`\`
web/kf-api/
├── src/
│   ├── index.tsx          # Hono 应用入口 + Cloudflare Pages handler
│   ├── auth.ts            # Better-Auth 配置 (支持开发/生产环境)
│   ├── database.ts        # 数据库连接 (better-sqlite3 / D1)
│   ├── auth-schema.ts     # Drizzle ORM Schema
│   └── env.d.ts           # TypeScript 类型定义
├── migrations/
│   └── 0001_create_better_auth_tables.sql  # D1 数据库迁移
├── scripts/
│   └── setup-d1-database.sh  # D1 数据库初始化脚本
├── wrangler.jsonc         # Cloudflare Workers/Pages 配置
├── package.json
├── QUICKSTART.md          # 快速部署指南
└── DEPLOYMENT.md          # 详细部署文档
\`\`\`

## 🛠️ 可用命令

\`\`\`bash
# 开发
bun run dev                  # 启动开发服务器

# 构建 & 部署
bun run build                # 构建生产版本
bun run deploy:prod          # 部署到生产环境

# 数据库
bun run setup:d1             # 初始化 D1 数据库
bun run db:query --command="SQL"  # 执行 D1 SQL 查询

# 监控
bun run logs:prod            # 查看生产环境实时日志
\`\`\`

## 🔌 主要 API 端点

- \`GET  /start-oauth?provider=google\` - 启动 OAuth 流程
- \`GET  /api/auth/callback/google\` - Google OAuth 回调
- \`GET  /api/auth/callback/github\` - GitHub OAuth 回调
- \`GET  /health\` - 健康检查

## 📚 相关文档

- [快速开始指南](./QUICKSTART.md)
- [详细部署文档](./DEPLOYMENT.md)
- [Better-Auth 官方文档](https://www.better-auth.com/docs)
- [Cloudflare D1 文档](https://developers.cloudflare.com/d1/)

---

**Made with ❤️ by Knowledge Focus Team**