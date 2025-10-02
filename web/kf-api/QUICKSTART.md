# 🚀 快速开始 - 生产环境部署

本文档提供快速部署到 Cloudflare Pages + D1 的步骤。

## ⚡ 快速部署 (5 分钟)

### 1️⃣ 初始化 D1 数据库

```bash
cd web/kf-api

# 运行数据库设置脚本
bun run setup:d1
```

### 2️⃣ 配置 Secrets

```bash
# Google OAuth
wrangler secret put GOOGLE_CLIENT_ID
wrangler secret put GOOGLE_CLIENT_SECRET

# GitHub OAuth
wrangler secret put GITHUB_CLIENT_ID
wrangler secret put GITHUB_CLIENT_SECRET

# Better-Auth 配置
wrangler secret put BETTER_AUTH_SECRET    # 使用: openssl rand -base64 32
wrangler secret put BETTER_AUTH_URL       # 输入: https://kf.huozhong.in
wrangler secret put NODE_ENV              # 输入: production
```

### 3️⃣ 部署

```bash
# 构建并部署到生产环境
bun run deploy:prod
```

### 4️⃣ 配置 Cloudflare Dashboard

1. 进入 **Cloudflare Dashboard** → **Pages** → 你的项目
2. **Settings** → **Functions** → **D1 database bindings**:
   - Variable name: `knowledge_focus_db`
   - D1 database: 选择 `knowledge-focus-db`
3. **Custom domains** → 添加 `kf.huozhong.in`

### 5️⃣ 验证

```bash
# 健康检查
curl https://kf.huozhong.in/health

# 应该返回:
# {"status":"ok","env":"production","database":"D1","timestamp":"..."}
```

## 📝 常用命令

```bash
# 开发环境
bun run dev                  # 启动开发服务器

# 生产部署
bun run build                # 构建项目
bun run deploy:prod          # 部署到生产环境

# 数据库管理
bun run setup:d1             # 初始化 D1 数据库
bun run db:query --command="SELECT * FROM user LIMIT 5;"  # 执行 SQL 查询

# 监控
bun run logs:prod            # 查看生产环境实时日志

# Secrets 管理
wrangler secret list         # 查看所有 secrets
wrangler secret put <NAME>   # 添加/更新 secret
wrangler secret delete <NAME> # 删除 secret
```

## 🔧 OAuth 应用配置

### Google OAuth

在 [Google Cloud Console](https://console.cloud.google.com/) 添加回调 URL:
- `http://127.0.0.1:60325/api/auth/callback/google` (开发)
- `https://kf.huozhong.in/api/auth/callback/google` (生产)

### GitHub OAuth

在 [GitHub Developer Settings](https://github.com/settings/developers) 添加回调 URL:
- `http://127.0.0.1:60325/api/auth/callback/github` (开发)
- `https://kf.huozhong.in/api/auth/callback/github` (生产)

## 🎯 环境对比

| 特性 | 开发环境 | 生产环境 |
|------|----------|----------|
| 数据库 | 本地 SQLite (`kfuser.db`) | Cloudflare D1 |
| 端口 | `http://127.0.0.1:60325` | `https://kf.huozhong.in` |
| 配置 | `.env` 文件 | Wrangler Secrets |
| 运行命令 | `bun run dev` | Cloudflare Pages |

## 📚 详细文档

完整部署指南请参考: [DEPLOYMENT.md](./DEPLOYMENT.md)

## ❓ 常见问题

**Q: 如何回滚到之前的版本?**

A: 在 Cloudflare Dashboard → Pages → Deployments 中选择历史版本,点击 "Rollback"

**Q: 如何查看数据库中的数据?**

A: 使用命令:
```bash
bun run db:query --command="SELECT * FROM user;"
```

**Q: 部署失败怎么办?**

A: 
1. 检查 `bun run logs:prod` 查看错误日志
2. 确认 D1 数据库已正确绑定
3. 验证所有 secrets 是否已配置: `wrangler secret list`

---

**🎉 就是这么简单!** 如果遇到问题,请查看详细的 [DEPLOYMENT.md](./DEPLOYMENT.md) 文档。
