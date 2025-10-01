# OAuth 集成开发进度追踪

## 项目概述

通过自部署的 Better-Auth Server (Cloudflare Pages) 实现 Tauri App 的 Google 社交登录功能。

## 技术架构

### 开发环境流程
```
用户点击登录 (Tauri App)
  ↓
打开浏览器 → https://kf.huozhong.in/sign-in/google
  ↓
Google OAuth 授权
  ↓
Google 回调 → https://kf.huozhong.in/api/auth/callback/google
  ↓
Better-Auth Server 完成 token exchange，创建 session
  ↓
重定向 → http://127.0.0.1:60315/api/auth/success?token={jwt}&user={userJson}
  ↓
Python FastAPI 接收 → 保存用户到本地 SQLite → Bridge 事件发送给 Rust
  ↓
Rust → IPC 通知前端
  ↓
前端更新 UI，显示用户头像和信息
```

### 数据库设计

**users 表：**
- `id` (INTEGER, PRIMARY KEY) - 主键
- `oauth_provider` (VARCHAR) - OAuth提供商 (google/github)
- `oauth_id` (VARCHAR, UNIQUE) - Google用户唯一ID
- `email` (VARCHAR) - 邮箱
- `name` (VARCHAR) - 用户名
- `avatar_url` (VARCHAR, NULLABLE) - 头像URL
- `session_token` (TEXT, NULLABLE) - JWT token
- `token_expires_at` (DATETIME, NULLABLE) - Token过期时间
- `created_at` (DATETIME) - 创建时间
- `updated_at` (DATETIME) - 更新时间

### JWT Token 策略
- **生成者：** Python API (方案B)
- **有效期：** 6个月
- **刷新策略：** 每次登录都更新用户信息和 token
- **退出策略：** 仅清除本地 token

## GCP OAuth 配置

### 需要添加的重定向URI
- `http://127.0.0.1:60315/api/auth/success` (开发环境)

### 现有配置
- 授权 JavaScript 来源：`http://127.0.0.1:60325`, `https://kf.huozhong.in`
- 授权重定向 URI：`http://127.0.0.1:60325/api/auth/callback/google`, `https://kf.huozhong.in/api/auth/callback/google`

## 开发任务清单

### 阶段 1：后端基础设施 ✅
- [x] 创建进度追踪文档
- [ ] 在 `db_mgr.py` 中添加 `User` 表定义
- [ ] 创建 `api/user_mgr.py` 用户管理器
- [ ] 创建 `api/user_api.py` 用户API路由
- [ ] 在 `main.py` 中注册用户API路由
- [ ] 移除旧的 OAuth 文件 (`oauth_callback_api.py`, `bridge_oauth_api.py`)

### 阶段 2：Better-Auth Server 配置
- [ ] 修改 `web/kf-api/src/auth.ts` 的重定向URL配置
- [ ] 测试 Better-Auth Server 本地运行

### 阶段 3：前端集成
- [ ] 修改 `tauri-app/src/lib/auth-store.ts` 登录逻辑
- [ ] 修改 `tauri-app/src/lib/auth-client.ts` 如需要
- [ ] 确保用户头像在 `AuthSection` 组件中正确显示

### 阶段 4：测试验证
- [ ] 本地测试完整登录流程
- [ ] 验证用户信息持久化
- [ ] 验证退出登录功能
- [ ] 验证 token 过期处理

## API 端点设计

### 用户相关API
- `POST /api/auth/success` - 接收 Better-Auth 重定向，保存用户信息
- `GET /api/user/profile` - 获取当前用户信息（需要 token）
- `POST /api/user/logout` - 退出登录（清除本地 token）
- `GET /api/user/validate-token` - 验证 token 有效性

## 待决定问题

- ❓ 前端是否需要轮询检查 Bridge 事件？还是依赖 Rust IPC 主动推送？
- ❓ Token 存储在前端哪里？localStorage vs Zustand persist？

## 技术债务

- 生产环境流程暂未实现，需要后续补充
- GitHub 登录暂未实现
- Token 自动刷新机制暂未实现（当前策略：仅在重新登录时更新）

## 更新日志

### 2025-10-01
- 项目启动，创建技术方案和任务清单
- 确认使用方案B（Python API 生成 JWT）
- 确认 token 有效期为6个月，仅登录时刷新
