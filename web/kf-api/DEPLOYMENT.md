# Cloudflare Pages + D1 生产环境部署指南

本指南帮助你将 Better-Auth 服务器部署到 Cloudflare Pages,使用 D1 (SQLite) 作为数据库。

## 📋 前置条件

1. Cloudflare 账号
2. Wrangler CLI 已安装: `npm install -g wrangler`
3. 已登录 Wrangler: `wrangler login`

## 🗄️ 步骤 1: 创建 D1 数据库

```bash
# 在 web/kf-api 目录下
cd web/kf-api

# 创建 D1 数据库
wrangler d1 create knowledge-focus-db
```

输出示例:
```
✅ Successfully created DB 'knowledge-focus-db'!

[[d1_databases]]
binding = "knowledge_focus_db"
database_name = "knowledge-focus-db"
database_id = "9368451d-a0de-4d77-ab52-5d85560dcbd8"
```

✅ **你已经在 `wrangler.jsonc` 中配置好了数据库 ID!**

## 🔧 步骤 2: 运行数据库迁移

执行 SQL 迁移脚本来创建 Better-Auth 需要的表:

```bash
# 应用迁移到远程 D1 数据库
wrangler d1 execute knowledge-focus-db --remote --file=./migrations/0001_create_better_auth_tables.sql
```

验证表是否创建成功:
```bash
# 查看所有表
wrangler d1 execute knowledge-focus-db --remote --command="SELECT name FROM sqlite_master WHERE type='table';"
```

## 🔐 步骤 3: 配置环境变量 (Secrets)

Better-Auth 需要以下敏感信息,使用 Wrangler Secrets 保存:

### 3.1 Google OAuth 凭证
```bash
wrangler secret put GOOGLE_CLIENT_ID
# 粘贴你的 Google Client ID,按 Enter

wrangler secret put GOOGLE_CLIENT_SECRET
# 粘贴你的 Google Client Secret,按 Enter
```

### 3.2 GitHub OAuth 凭证
```bash
wrangler secret put GITHUB_CLIENT_ID
# 粘贴你的 GitHub Client ID,按 Enter

wrangler secret put GITHUB_CLIENT_SECRET
# 粘贴你的 GitHub Client Secret,按 Enter
```

### 3.3 Better-Auth 配置
```bash
wrangler secret put BETTER_AUTH_SECRET
# 输入一个随机密钥 (至少 32 字符),按 Enter
# 可以使用: openssl rand -base64 32

wrangler secret put BETTER_AUTH_URL
# 输入: https://kf.huozhong.in
```

### 3.4 环境标记
```bash
wrangler secret put NODE_ENV
# 输入: production
```

查看所有已配置的 secrets:
```bash
wrangler secret list
```

## 📦 步骤 4: 构建项目

```bash
# 安装依赖
bun install

# 构建生产版本
bun run build
```

## 🚀 步骤 5: 部署到 Cloudflare Pages

### 5.1 首次部署

```bash
# 部署到 Cloudflare Pages
wrangler pages deploy dist --project-name=kf-auth-server

# 或者使用 npm script (如果已配置)
bun run deploy
```

### 5.2 配置自定义域名

1. 进入 Cloudflare Dashboard
2. 导航到 **Pages** → 你的项目 → **Custom domains**
3. 添加域名: `kf.huozhong.in`
4. 按照提示配置 DNS 记录

### 5.3 绑定 D1 数据库

在 Cloudflare Dashboard 中:
1. **Pages** → 你的项目 → **Settings** → **Functions**
2. **D1 database bindings**:
   - Variable name: `knowledge_focus_db`
   - D1 database: 选择 `knowledge-focus-db`
3. 保存设置

## ✅ 步骤 6: 验证部署

### 6.1 健康检查
```bash
curl https://kf.huozhong.in/health
```

预期响应:
```json
{
  "status": "ok",
  "env": "production",
  "database": "D1",
  "timestamp": "2025-10-02T12:00:00.000Z"
}
```

### 6.2 测试 OAuth 流程

访问: `https://kf.huozhong.in/start-oauth?provider=google`

应该会跳转到 Google OAuth 授权页面。

## 🔄 后续更新部署

```bash
# 1. 构建
bun run build

# 2. 部署
wrangler pages deploy dist --project-name=kf-auth-server
```

## 📊 监控和日志

### 查看实时日志
```bash
wrangler pages deployment tail --project-name=kf-auth-server
```

### D1 数据库查询
```bash
# 查看用户数
wrangler d1 execute knowledge-focus-db --remote --command="SELECT COUNT(*) as user_count FROM user;"

# 查看最近的用户
wrangler d1 execute knowledge-focus-db --remote --command="SELECT * FROM user ORDER BY created_at DESC LIMIT 5;"
```

## 🔧 故障排查

### 问题 1: "Database not found"
**解决**: 确保在 Cloudflare Dashboard 的 Pages 设置中正确绑定了 D1 数据库

### 问题 2: "OAuth redirect_uri mismatch"
**解决**: 在 Google/GitHub OAuth 应用设置中添加生产环境回调 URL:
- Google: `https://kf.huozhong.in/api/auth/callback/google`
- GitHub: `https://kf.huozhong.in/api/auth/callback/github`

### 问题 3: "Missing environment variables"
**解决**: 使用 `wrangler secret list` 检查是否所有 secrets 都已设置

## 📝 配置清单

- ✅ D1 数据库已创建
- ✅ 数据库表已迁移
- ✅ 所有 Secrets 已配置
- ✅ 项目已构建
- ✅ 已部署到 Cloudflare Pages
- ✅ D1 数据库已绑定
- ✅ 自定义域名已配置
- ✅ OAuth 回调 URL 已更新
- ✅ 健康检查通过

## 🎉 完成!

你的 Better-Auth 服务器现在运行在:
- **开发环境**: `http://127.0.0.1:60325`
- **生产环境**: `https://kf.huozhong.in`

数据库:
- **开发环境**: 本地 SQLite (`kfuser.db`)
- **生产环境**: Cloudflare D1

---

**参考文档**:
- [Cloudflare D1 文档](https://developers.cloudflare.com/d1/)
- [Wrangler CLI 文档](https://developers.cloudflare.com/workers/wrangler/)
- [Better-Auth 文档](https://www.better-auth.com/docs)
