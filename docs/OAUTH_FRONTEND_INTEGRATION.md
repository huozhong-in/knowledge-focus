# OAuth 前端集成完成文档

## ✅ 已完成工作总结

### 1. 核心代码更新

#### `tauri-app/src/lib/auth-store.ts`
- ✅ 移除旧的 Better-Auth 客户端依赖
- ✅ 实现 `initAuthListener()` 监听 Rust 转发的 `oauth-login-success` 事件
- ✅ 更新 `login()` 使用外部浏览器打开 OAuth URL
- ✅ 更新 `logout()` 和 `checkAuth()` 调用 Python API
- ✅ **移除 `updateVipStatus()`** - VIP 业务不在本次范围

#### `tauri-app/src/App.tsx`
- ✅ API 就绪后调用 `initAuthListener()` 初始化监听器
- ✅ 添加清理函数避免内存泄漏

#### `tauri-app/src/components/AuthSection.tsx`
- ✅ 更新用户界面显示字段 (`avatar_url` 替代 `image`)
- ✅ **移除所有 VIP 相关 UI** (Badge, Crown, vipLevel, vipExpiresAt)
- ✅ 简化为只显示: 头像、姓名、邮箱

#### `tauri-app/src-tauri/src/event_buffer.rs`
- ✅ 将 `oauth-login-success` 配置为**立即转发**策略
- ✅ 确保登录事件零延迟到达前端

### 2. 数据结构定义

```typescript
// 用户对象 - 匹配 Python API User 模型
interface User {
  id: string;
  oauth_provider: string;  // 'google', 'github', etc.
  oauth_id: string;         // OAuth provider's user ID
  email: string;
  name: string;
  avatar_url?: string;      // 注意: 不是 'image'
  created_at: string;
  updated_at: string;
}

// OAuth 事件 payload
interface AuthPayload {
  user: User;
  token: string;           // JWT from Python API
  expires_at: string;      // ISO 8601 timestamp
}
```

## 🚀 完整 OAuth 流程

```
┌─────────────┐
│ Tauri App   │
│ 用户点击登录  │
└──────┬──────┘
       │ useAuthStore.login('google')
       │ 
       ↓
┌──────────────────────────┐
│ @tauri-apps/plugin-shell │
│ open(127.0.0.1:60325)    │
└──────┬───────────────────┘
       │ 打开外部浏览器
       ↓
┌─────────────────┐
│ Better-Auth     │
│ /start-oauth    │  ←─ POST 表单提交
└────────┬────────┘
         │ /api/auth/sign-in/social
         │ provider=google
         ↓
┌──────────────────┐
│ Google OAuth     │  ←─ 用户授权
└────────┬─────────┘
         │ callback
         ↓
┌─────────────────────┐
│ Better-Auth         │
│ /callback/google    │  ←─ Google 回调
└────────┬────────────┘
         │ 创建 session
         │
         ↓
┌──────────────────────────┐
│ Better-Auth              │
│ /auth-callback-bridge    │  ←─ 提取用户信息
└────────┬─────────────────┘
         │ 重定向到 Python API
         │ ?provider=google&oauth_id=...
         ↓
┌─────────────────────────┐
│ Python API              │
│ /api/auth/success       │  ←─ 接收用户信息
└────────┬────────────────┘
         │ 1. Upsert 用户到数据库
         │ 2. 生成 JWT (6个月有效期)
         │ 3. print(EVENT_NOTIFY_JSON:...)
         │ 4. 返回 HTML 成功页面
         ↓
┌─────────────────────┐
│ Rust Sidecar        │
│ api_startup.rs      │  ←─ 监听 Python stdout
└────────┬────────────┘
         │ parse_bridge_event()
         │ EventBuffer.handle_event()
         │ 策略: Immediate (立即转发)
         ↓
┌─────────────────────┐
│ Tauri IPC           │
│ emit('oauth-login-  │
│      success')      │
└────────┬────────────┘
         │
         ↓
┌─────────────────────────────┐
│ auth-store                  │
│ listen('oauth-login-success')│
└────────┬────────────────────┘
         │ 更新 Zustand state:
         │ - user
         │ - token
         │ - tokenExpiresAt
         │ - isAuthenticated: true
         │ 
         │ 持久化到 localStorage
         ↓
┌────────────────────┐
│ UI 自动更新         │
│ 显示用户信息        │
└────────────────────┘
```

## 🧪 测试步骤

### 1. 启动服务

```bash
# Terminal 1: Better-Auth Server
cd web/kf-api
bun run dev
# ✅ 监听: http://127.0.0.1:60325

# Terminal 2: Tauri App (自动启动 Python API)
cd tauri-app
./dev.sh
# ✅ Python API: http://127.0.0.1:60315
# ✅ Tauri App: http://localhost:1420
```

### 2. 测试登录

#### 方法 A: 通过 UI
1. 启动 Tauri App
2. 按 `⌘,` 打开设置
3. 点击 "使用 Google 登录"
4. 在浏览器中完成授权
5. **预期结果**: Tauri App 自动显示已登录状态

#### 方法 B: 通过控制台
```javascript
// 1. 打开浏览器控制台 (⌘⌥I)
// 2. 执行登录
useAuthStore.getState().login('google')

// 3. 完成授权后,检查状态
const { user, token, isAuthenticated } = useAuthStore.getState()
console.log({ user, token, isAuthenticated })
```

### 3. 验证功能

#### 检查存储
```javascript
// localStorage 持久化
const stored = JSON.parse(localStorage.getItem('auth-storage'))
console.log('Stored:', stored)
```

#### 测试 API 调用
```javascript
// 使用 token 调用 Python API
const { token } = useAuthStore.getState()
const res = await fetch('http://127.0.0.1:60315/api/user/profile', {
  headers: { 'Authorization': `Bearer ${token}` }
})
console.log('Profile:', await res.json())
```

#### 测试登出
```javascript
await useAuthStore.getState().logout()
// ✅ 应该清空 user, token, isAuthenticated
```

## 🐛 调试技巧

### Python API 日志
```bash
# 查看 Python API 日志
tail -f ~/Library/Application\ Support/knowledge-focus.huozhong.in/logs/*.log

# 关键日志:
# - "EVENT_NOTIFY_JSON:" - bridge event 发送
# - "OAuth 回调成功" - 接收到用户信息
# - "生成 JWT token" - token 生成
```

### Better-Auth 日志
- 查看 Terminal 1 输出
- 重点关注 OAuth 请求和回调

### Rust 日志
- 查看 Terminal 2 (Tauri App) 输出
- 重点关注: `⚡ 立即转发事件: oauth-login-success`

### 前端日志
```javascript
// 浏览器控制台应该看到:
// "🎧 OAuth 事件监听器已初始化"
// "✅ 收到 OAuth 登录成功事件:"
// "✅ 用户状态已更新:"
```

## ⚠️ 常见问题

### Q1: 点击登录没反应
**检查**:
- 是否在 Tauri 环境? `await isTauri()` 应该返回 `true`
- `@tauri-apps/plugin-shell` 是否安装?

### Q2: Bridge event 未收到
**排查步骤**:
1. Python API 是否发送? 检查日志是否有 `EVENT_NOTIFY_JSON:`
2. Rust 是否接收? 检查是否有 `⚡ 立即转发事件`
3. 前端是否监听? 检查是否有 `🎧 OAuth 事件监听器已初始化`

**解决**: 重启 Tauri App 确保监听器初始化

### Q3: Token 验证失败
**检查**:
```javascript
const { token } = useAuthStore.getState()
const res = await fetch('http://127.0.0.1:60315/api/user/validate-token', {
  headers: { 'Authorization': `Bearer ${token}` }
})
console.log(await res.json())
```

**可能原因**:
- JWT secret 不一致
- Token 已过期 (6个月有效期)
- Token 格式错误

### Q4: CORS 错误
**检查**: Python API 的 CORS 配置是否允许 Tauri App 的 origin

### Q5: State Mismatch
**原因**: Better-Auth 的 state 验证失败

**解决**: 确保所有请求通过 `/start-oauth` 端点,不要手动构造 OAuth URL

## 📋 架构决策记录

### ✅ 采用的方案

1. **外部浏览器 OAuth**
   - 理由: 避免 Tauri WebView 的 cookie 限制
   - 工具: `@tauri-apps/plugin-shell`

2. **Bridge Event 通信**
   - 理由: 实时、低延迟、无需轮询
   - 格式: `EVENT_NOTIFY_JSON:{...}`

3. **JWT 由 Python API 生成**
   - 理由: Better-Auth 只负责认证,业务逻辑在 Python
   - 有效期: 6 个月
   - 刷新策略: 重新登录

4. **标准 socialProviders.google**
   - 理由: 稳定、不强制 PKCE
   - 不使用: genericOAuth (会强制 PKCE)

5. **VIP 逻辑分离**
   - 理由: 认证层不应包含业务逻辑
   - 实现: 后续通过独立 API 查询

### ❌ 放弃的方案

1. ~~WebView 内 OAuth~~ - Cookie 限制问题
2. ~~genericOAuth 插件~~ - 强制 PKCE 导致错误
3. ~~VIP 字段在 Better-Auth~~ - 业务逻辑不属于认证层
4. ~~手动构造 OAuth URL~~ - State 验证失败

## 🔐 安全注意事项

### 当前实现 (开发环境)
- ⚠️ JWT secret: 硬编码 "your-secret-key-change-in-production"
- ✅ CORS: 限制 origin
- ✅ Token 有效期: 6 个月
- ⚠️ HTTP: 开发环境使用明文传输

### 生产环境待办
- [ ] JWT secret 使用环境变量
- [ ] 启用 HTTPS (所有服务)
- [ ] 配置生产 OAuth 回调 URL
- [ ] 实现 Token 刷新机制 (可选)
- [ ] 添加 Rate Limiting
- [ ] 日志脱敏 (不记录 token)
- [ ] Deep Link 回调 (macOS App Store)

## 📚 相关文件清单

### Python API
- `api/db_mgr.py` - User 模型定义
- `api/user_mgr.py` - JWT 生成/验证
- `api/user_api.py` - OAuth 回调和用户 API
- `api/bridge_events.py` - Bridge event 发送

### Better-Auth
- `web/kf-api/src/auth.ts` - Better-Auth 配置
- `web/kf-api/src/index.tsx` - Hono 路由

### Rust
- `tauri-app/src-tauri/src/api_startup.rs` - Bridge event 解析
- `tauri-app/src-tauri/src/event_buffer.rs` - 事件缓冲策略

### Frontend
- `tauri-app/src/lib/auth-store.ts` - 状态管理
- `tauri-app/src/App.tsx` - 监听器初始化
- `tauri-app/src/components/AuthSection.tsx` - 认证 UI

## 🎯 当前状态

**✅ 开发完成,等待集成测试**

### 已完成
- [x] Python API OAuth 回调和 JWT 生成
- [x] Better-Auth 服务器配置
- [x] Rust Bridge Event 处理
- [x] 前端状态管理和监听器
- [x] UI 组件更新
- [x] **清理 VIP 相关代码**

### 待测试
- [ ] 完整登录流程
- [ ] Token 持久化和恢复
- [ ] 登出功能
- [ ] API 调用授权
- [ ] 错误处理

### 未来工作 (不在本次范围)
- [ ] VIP 业务逻辑实现
- [ ] GitHub OAuth 支持
- [ ] 生产环境配置
- [ ] Token 刷新机制

---

**文档版本**: 2.0  
**最后更新**: 2025-10-01  
**状态**: Ready for Testing 🚀
