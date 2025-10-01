# OAuth 集成 - 快速测试指南

## 当前状态

✅ 后端API已完成
⚠️ Better-Auth配置需要调整
⏸️ 前端集成待完成

## 立即行动清单

### 1. 安装Python依赖

```bash
cd /Users/dio/workspace/knowledge-focus/api
uv add pyjwt
```

### 2. 更新GCP OAuth配置

登录 [Google Cloud Console](https://console.cloud.google.com/)，在OAuth 2.0客户端配置中：

**添加重定向URI：**
```
http://127.0.0.1:60315/api/auth/success
```

保存后等待几分钟生效。

### 3. 修改 Better-Auth Server 回调逻辑

编辑文件：`web/kf-api/src/index.tsx`

在现有的 `app.get('/oauth-success', ...)` 端点**之前**添加：

```typescript
// OAuth回调成功后的重定向处理
app.get('/auth-callback-bridge', async (c) => {
  try {
    // 从better-auth获取当前session
    const authRequest = c.req.raw;
    const session = await auth.api.getSession({ 
      headers: authRequest.headers 
    });
    
    if (session?.user) {
      const user = session.user;
      const provider = c.req.query('provider') || 'google';
      
      // 构建重定向到Python API的URL
      const isDev = c.env?.NODE_ENV !== 'production';
      const pythonApiUrl = isDev 
        ? 'http://127.0.0.1:60315/api/auth/success'
        : 'https://你的生产API地址/api/auth/success'; // TODO
      
      const params = new URLSearchParams({
        provider,
        oauth_id: user.id,
        email: user.email,
        name: user.name,
        avatar_url: user.image || ''
      });
      
      return c.redirect(`${pythonApiUrl}?${params.toString()}`);
    } else {
      return c.text('No session found', 401);
    }
  } catch (error) {
    console.error('Auth callback bridge error:', error);
    return c.text('Authentication error', 500);
  }
});
```

然后修改 Google OAuth 的 `callbackURL` 配置，在 `src/auth.ts` 中：

```typescript
// 找到 custom-google 配置，添加 callbackURL
{
  providerId: "custom-google",
  // ... 其他配置
  callbackURL: "/auth-callback-bridge?provider=google",
}
```

### 4. 测试Python API端点

启动Python API：

```bash
cd /Users/dio/workspace/knowledge-focus/api
python main.py --port 60315 --db-path ~/Library/Application\ Support/knowledge-focus.huozhong.in/knowledge-focus.db
```

在另一个终端测试：

```bash
# 测试auth/success端点
curl "http://127.0.0.1:60315/api/auth/success?provider=google&oauth_id=test123&email=test@example.com&name=TestUser&avatar_url=https://example.com/avatar.jpg"
```

你应该看到一个HTML页面返回，并且Python日志中显示：

```
收到OAuth成功回调: provider=google, email=test@example.com
用户信息已更新: test@example.com, User ID: 1
OAuth登录成功事件已发送: user_id=1, email=test@example.com
```

检查数据库：

```bash
sqlite3 ~/Library/Application\ Support/knowledge-focus.huozhong.in/knowledge-focus.db
sqlite> select * from t_users;
```

### 5. 启动Better-Auth Server

```bash
cd /Users/dio/workspace/knowledge-focus/web/kf-api

# 确保.env文件包含：
# GOOGLE_CLIENT_ID=你的客户端ID
# GOOGLE_CLIENT_SECRET=你的客户端密钥

bun run dev
```

应该在 `http://127.0.0.1:60325` 启动。

测试访问：`http://127.0.0.1:60325/`

### 6. 手动测试完整流程

由于前端集成未完成，可以手动测试：

1. 打开浏览器访问：`http://127.0.0.1:60325/api/auth/sign-in/google`
2. 完成Google OAuth授权
3. 观察重定向流程
4. 最终应该看到Python API返回的成功页面
5. 检查数据库确认用户已保存

### 7. 前端集成（下一步）

需要修改 `tauri-app/src/lib/auth-store.ts`：

```typescript
login: async (provider: string) => {
  set({ isLoading: true });
  try {
    const isDev = import.meta.env.DEV;
    const authUrl = isDev 
      ? `http://127.0.0.1:60325/api/auth/sign-in/${provider}`
      : `https://kf.huozhong.in/api/auth/sign-in/${provider}`;
    
    // 打开外部浏览器
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    await openUrl(authUrl);
    
    // 等待Bridge事件通知登录成功
    // TODO: 添加事件监听逻辑
  } catch (error) {
    console.error('登录失败:', error);
  } finally {
    set({ isLoading: false });
  }
}
```

并添加Rust IPC事件监听：

```typescript
// 在组件挂载时监听
useEffect(() => {
  const unlisten = await listen('oauth-login-success', (event) => {
    const userData = event.payload;
    // 更新store
    set({
      user: userData.user,
      isAuthenticated: true
    });
    // 保存token到localStorage或其他地方
  });
  
  return () => unlisten();
}, []);
```

## 调试技巧

### 查看Python日志

```bash
tail -f ~/Library/Application\ Support/knowledge-focus.huozhong.in/logs/api_*.log
```

### 查看数据库内容

```bash
sqlite3 ~/Library/Application\ Support/knowledge-focus.huozhong.in/knowledge-focus.db

# 查看用户表
.schema t_users
select * from t_users;

# 查看token
select id, email, substr(session_token, 1, 50) as token_preview from t_users;
```

### 检查Bridge事件

在Python API的stdout中搜索：

```
[BRIDGE_EVENT]
```

## 常见问题

**Q: Python API启动失败？**
A: 检查端口60315是否被占用，或数据库路径是否正确

**Q: Better-Auth Server无法启动？**
A: 检查.env文件是否配置正确，bun依赖是否安装

**Q: Google OAuth返回错误？**
A: 检查GCP配置的重定向URI是否正确，等待几分钟让配置生效

**Q: 看不到Bridge事件？**
A: 确保Python API在Tauri作为sidecar运行，或者检查bridge_events.py的实现

## 下次任务

1. 完成Better-Auth的回调重定向逻辑
2. 前端添加事件监听和状态更新
3. 测试完整的端到端流程
4. 添加错误处理和用户友好提示
