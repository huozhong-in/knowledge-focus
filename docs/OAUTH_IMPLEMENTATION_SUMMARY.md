# OAuth 集成实施总结

## 已完成的工作

### 1. 后端数据库和用户管理 ✅

**文件创建/修改：**
- ✅ `api/db_mgr.py` - 添加了 `User` 表定义，包含OAuth相关字段
- ✅ `api/user_mgr.py` - 用户管理器，负责JWT生成、验证和用户CRUD操作
- ✅ `api/user_api.py` - 用户API路由，包含4个端点
- ✅ `api/main.py` - 注册了user_api路由，移除了旧的oauth相关路由

**User表结构：**
```python
- id (主键)
- oauth_provider (google/github)
- oauth_id (OAuth唯一ID, 有唯一索引)
- email (有索引)
- name
- avatar_url
- session_token (JWT)
- token_expires_at
- created_at
- updated_at
```

**API端点：**
1. `GET /api/auth/success` - 接收Better-Auth重定向，保存用户，发送Bridge事件
2. `GET /api/user/profile` - 获取用户信息（需要Bearer token）
3. `POST /api/user/logout` - 退出登录，清除token
4. `POST /api/user/validate-token` - 验证token有效性

### 2. Better-Auth Server配置 ⚠️

**文件修改：**
- ✅ `web/kf-api/src/auth.ts` - 修改了baseURL和redirectURI支持开发/生产环境

**关键改动：**
- 根据 `process.env.NODE_ENV` 动态设置baseURL和redirectURI
- 移除了复杂的hooks配置（需要通过其他方式处理重定向）

**⚠️ 待解决问题：**
Better-Auth 的回调处理需要自定义逻辑来：
1. 在OAuth成功后获取用户信息
2. 构建重定向URL到 Python API (`http://127.0.0.1:60315/api/auth/success`)
3. 附带用户信息作为查询参数

**建议方案：**
修改 `web/kf-api/src/index.tsx` 添加一个中间页面：
```typescript
// 在/oauth-success 端点获取session后，重定向到Python API
app.get('/api/auth/callback-success', async (c) => {
  // 从better-auth session获取用户信息
  const session = await auth.api.getSession({...});
  if (session?.user) {
    const params = new URLSearchParams({
      provider: 'google', // 需要从上下文判断
      oauth_id: session.user.id,
      email: session.user.email,
      name: session.user.name,
      avatar_url: session.user.image || ''
    });
    return c.redirect(`http://127.0.0.1:60315/api/auth/success?${params}`);
  }
})
```

### 3. 前端集成 ⏸️

**需要修改的文件：**
- `tauri-app/src/lib/auth-store.ts` - 登录逻辑
- `tauri-app/src/lib/auth-client.ts` - 可能需要调整

**登录流程调整：**
```typescript
// 当前逻辑：
// 1. 调用 authClient.signIn.oauth2() 获取URL
// 2. 打开浏览器访问Better-Auth

// 需要调整为：
// 1. 直接构建Better-Auth的登录URL
// 2. URL应该指向: https://kf.huozhong.in/api/auth/sign-in/google
// 3. 打开浏览器
// 4. 等待Bridge事件 'oauth-login-success'
// 5. 从事件中获取用户信息和token
// 6. 保存到Zustand store
```

**Bridge事件监听：**
需要在Rust侧监听Python stdout的 `oauth-login-success` 事件，然后通过IPC发送给前端。

## 下一步操作

### 立即需要做的：

1. **安装Python依赖：**
   ```bash
   cd api
   # 安装PyJWT
   uv pip install pyjwt
   ```

2. **更新GCP OAuth配置：**
   添加重定向URI: `http://127.0.0.1:60315/api/auth/success`

3. **修改 Better-Auth Server的回调处理：**
   在 `web/kf-api/src/index.tsx` 中添加自定义回调重定向逻辑

4. **测试Python API：**
   ```bash
   # 启动Python API
   cd api
   python main.py --port 60315
   
   # 手动测试auth/success端点
   curl "http://127.0.0.1:60315/api/auth/success?provider=google&oauth_id=test123&email=test@example.com&name=TestUser&avatar_url=https://example.com/avatar.jpg"
   ```

5. **修改前端登录逻辑：**
   - 更新 `auth-store.ts` 的 login 函数
   - 添加Bridge事件监听

6. **测试Better-Auth Server：**
   ```bash
   cd web/kf-api
   bun run dev  # 应该监听在 60325 端口
   ```

### 测试流程：

1. 启动Python API (60315端口)
2. 启动Better-Auth Server (60325端口)
3. 启动Tauri App开发模式
4. 点击"Google登录"按钮
5. 观察日志：
   - Python API logs: 应该看到 `/api/auth/success` 的请求
   - Rust stdout: 应该看到 Bridge 事件发送
   - Browser console: 查看重定向流程
6. 验证：用户信息是否正确保存并显示在UI

## 技术细节记录

### JWT Secret
⚠️ 当前使用硬编码 secret，生产环境需要从环境变量读取：
```python
# user_mgr.py
JWT_SECRET = "your-secret-key-change-in-production"
```

### Token有效期
- 设置为6个月 (180天)
- 仅在用户重新登录时更新

### 旧文件清理
以下文件可以删除（已从main.py移除引用）：
- `api/oauth_callback_api.py`
- `api/bridge_oauth_api.py`

但建议先保留作为参考，待完整测试通过后再删除。

## 已知问题

1. **Better-Auth的hooks API不确定：**
   - 尝试使用after hooks失败
   - 需要通过其他方式（如自定义端点）处理回调重定向

2. **环境变量管理：**
   - Better-Auth Server 需要 `.env` 文件配置 GOOGLE_CLIENT_ID 等
   - 需要文档说明开发环境配置步骤

3. **跨域问题：**
   - Python API (60315) 接收来自浏览器的重定向请求，可能需要CORS配置
   - 已在main.py配置CORS，但需测试验证

## 文档位置

- 完整进度：`docs/OAUTH_INTEGRATION_PROGRESS.md`
- 产品需求：`docs/PRD.md`
- 之前的尝试：`docs/Better-Auth接入.md` (已过时)
