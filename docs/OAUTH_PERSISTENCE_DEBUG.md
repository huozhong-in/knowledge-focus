# OAuth 持久化调试指南

## 问题描述
用户登录成功后,重启 Tauri App 发现登录状态丢失。

## 持久化机制

### 当前实现
使用 Zustand 的 `persist` 中间件,默认存储到浏览器 `localStorage`:

```typescript
persist(
  (set, get) => ({ /* store logic */ }),
  {
    name: 'auth-storage',
    partialize: (state) => ({ 
      user: state.user,
      token: state.token,
      tokenExpiresAt: state.tokenExpiresAt,
      isAuthenticated: state.isAuthenticated 
    }),
  }
)
```

### 存储位置
- **Web 环境**: `localStorage` (浏览器标准 API)
- **Tauri 环境**: Tauri WebView 的 localStorage (持久化到用户数据目录)

### Tauri localStorage 路径
macOS: `~/Library/Application Support/knowledge-focus.huozhong.in/`

## 调试步骤

### 1. 检查 localStorage 是否保存

在浏览器控制台执行:
```javascript
// 检查存储的数据
const stored = localStorage.getItem('auth-storage');
console.log('Stored auth data:', stored);

// 解析查看
if (stored) {
  const data = JSON.parse(stored);
  console.log('Parsed:', data);
  console.log('Has token:', !!data.state?.token);
  console.log('Has user:', !!data.state?.user);
}
```

### 2. 检查 Zustand store 状态

```javascript
// 查看当前 store 状态
import { useAuthStore } from '@/lib/auth-store';
const state = useAuthStore.getState();
console.log('Current auth state:', {
  user: state.user,
  token: state.token ? state.token.substring(0, 20) + '...' : null,
  tokenExpiresAt: state.tokenExpiresAt,
  isAuthenticated: state.isAuthenticated,
  isLoading: state.isLoading
});
```

### 3. 测试 checkAuth() 

```javascript
// 手动调用检查认证
await useAuthStore.getState().checkAuth();
```

查看控制台输出:
- `🔍 检查认证状态...` - 开始检查
- `Token: ...` - Token 存在
- `ExpiresAt: ...` - 过期时间
- `Current User: ...` - 当前用户邮箱
- `✅ Token 未过期，调用 API 验证...` - Token 有效
- `API 响应状态: 200` - API 调用成功
- `✅ Token 有效，用户已认证: xxx@gmail.com` - 验证通过

### 4. 检查 API 调用

```javascript
// 测试 validate-token API
const token = useAuthStore.getState().token;
const response = await fetch('http://127.0.0.1:60315/api/user/validate-token', {
  headers: { 'Authorization': `Bearer ${token}` }
});
const data = await response.json();
console.log('API Response:', data);
```

预期响应:
```json
{
  "valid": true,
  "user": {
    "id": "1",
    "email": "user@example.com",
    "name": "User Name",
    "avatar_url": "...",
    "oauth_provider": "google",
    "oauth_id": "...",
    "created_at": "...",
    "updated_at": "..."
  }
}
```

## 常见问题排查

### 问题 1: localStorage 为空
**症状**: `localStorage.getItem('auth-storage')` 返回 `null`

**可能原因**:
1. 登录时状态未正确保存
2. Tauri WebView 清除了缓存
3. 使用了不同的域名/协议

**解决方案**:
```javascript
// 登录后手动检查
console.log('After login:', localStorage.getItem('auth-storage'));
```

### 问题 2: Token 存在但验证失败
**症状**: localStorage 有数据,但 API 返回 401

**可能原因**:
1. Token 格式错误
2. JWT secret 不一致
3. Token 已在服务端失效

**解决方案**:
```bash
# 检查 Python API 日志
tail -f ~/Library/Application\ Support/knowledge-focus.huozhong.in/logs/*.log | grep validate
```

### 问题 3: checkAuth() 未执行
**症状**: 启动后没有看到 `🔍 检查认证状态...` 日志

**可能原因**:
1. API 未就绪时就调用了
2. 监听器初始化失败

**解决方案**:
查看 `App.tsx` 中的 `useEffect`:
```typescript
useEffect(() => {
  if (isApiReady) {
    checkAuth()  // 确保这里被调用
  }
}, [isApiReady])
```

### 问题 4: Zustand persist 未工作
**症状**: 登录后刷新页面状态丢失

**可能原因**:
1. `partialize` 配置错误
2. localStorage 权限问题
3. Tauri WebView 配置问题

**解决方案**:
```javascript
// 测试 Zustand persist
useAuthStore.persist.rehydrate();
console.log('After rehydrate:', useAuthStore.getState());
```

## 测试场景

### 场景 1: 首次登录
1. ✅ 点击登录按钮
2. ✅ 完成 OAuth 授权
3. ✅ 看到用户信息
4. ✅ 检查 localStorage: `localStorage.getItem('auth-storage')`
5. ✅ 应该看到完整的 state 数据

### 场景 2: 刷新页面 (开发环境)
1. ✅ 按 `Cmd+R` 刷新页面
2. ✅ 应该自动恢复登录状态
3. ✅ 控制台应该看到:
   - `🔍 检查认证状态...`
   - `✅ Token 有效，用户已认证`

### 场景 3: 重启应用
1. ✅ 完全关闭 Tauri App (`Cmd+Q`)
2. ✅ 重新启动应用
3. ✅ 应该自动恢复登录状态
4. ✅ 如果失败,查看控制台日志

### 场景 4: Token 过期
1. ✅ 修改 localStorage 中的 `tokenExpiresAt` 为过去的时间
2. ✅ 刷新页面
3. ✅ 应该看到 `⚠️ Token 已过期` 并清除状态

## 调试命令集合

```javascript
// === 查看当前状态 ===
useAuthStore.getState()

// === 查看 localStorage ===
JSON.parse(localStorage.getItem('auth-storage'))

// === 手动触发检查 ===
await useAuthStore.getState().checkAuth()

// === 清除状态 (重新登录测试) ===
localStorage.removeItem('auth-storage')
useAuthStore.getState().logout()

// === 强制重新加载 persist 数据 ===
useAuthStore.persist.rehydrate()

// === 测试 API ===
const token = useAuthStore.getState().token;
await fetch('http://127.0.0.1:60315/api/user/validate-token', {
  headers: { 'Authorization': `Bearer ${token}` }
}).then(r => r.json())
```

## 预期行为

### 正常流程
```
启动应用
    ↓
isApiReady = true
    ↓
Zustand persist 自动从 localStorage 恢复状态
    ↓
checkAuth() 被调用
    ↓
检查 token 和 expiresAt
    ↓
如果存在且未过期 → 调用 API 验证
    ↓
API 返回 valid: true
    ↓
更新 isAuthenticated = true
    ↓
UI 显示用户信息 ✅
```

### 异常流程
```
启动应用
    ↓
localStorage 为空 / token 无效 / API 失败
    ↓
清除所有认证状态
    ↓
UI 显示登录按钮 ❌
```

## 需要检查的文件

1. `/Users/dio/workspace/knowledge-focus/tauri-app/src/lib/auth-store.ts`
   - persist 配置
   - checkAuth() 实现
   
2. `/Users/dio/workspace/knowledge-focus/tauri-app/src/App.tsx`
   - checkAuth() 调用时机
   - initAuthListener() 初始化

3. `/Users/dio/workspace/knowledge-focus/api/user_api.py`
   - validate-token 端点实现

## 下一步

请执行以下操作并报告结果:

1. **登录成功后**,在控制台执行:
   ```javascript
   localStorage.getItem('auth-storage')
   ```
   
2. **重启应用后**,立即在控制台查看:
   - 是否有 `🔍 检查认证状态...` 日志
   - localStorage 中是否还有数据
   
3. **手动调用检查**:
   ```javascript
   await useAuthStore.getState().checkAuth()
   ```
   查看详细日志输出

---

**更新时间**: 2025-10-02  
**状态**: 等待调试反馈
