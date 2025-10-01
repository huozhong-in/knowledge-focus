import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { auth } from './auth'

const app = new Hono<{ Bindings: CloudflareBindings }>();

// CORS配置 - 允许来自Tauri应用的请求
app.use('*', cors({
  origin: [
    'http://localhost:3000',
    'http://127.0.0.1:3000', 
    'http://localhost:1420',
    'http://127.0.0.1:1420',
    'http://localhost:60325',
    'http://127.0.0.1:60325',
    'tauri://localhost',
    'https://tauri.localhost'
  ],
  credentials: true,
  allowMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowHeaders: ['Content-Type', 'Authorization', 'X-Requested-With', 'Platform']
}))

// 身份验证路由
app.on(['GET', 'POST'], '/api/auth/*', (c) => {
  console.log('Auth request:', c.req.method, c.req.url);
  console.log('Headers:', Object.fromEntries(c.req.raw.headers.entries()));
  return auth.handler(c.req.raw);
})

// OAuth 启动端点 - 处理表单提交并转发到 Better-Auth
app.post('/start-oauth', async (c) => {
  try {
    console.log('[Start OAuth] Initiating OAuth flow...');
    
    // 从表单获取参数
    const body = await c.req.parseBody();
    const provider = body.providerId as string || 'google';  // 改名为 provider
    const callbackURL = body.callbackURL as string || '/auth-callback-bridge';
    
    console.log('[Start OAuth] Params:', { provider, callbackURL });
    
    // 调用 Better-Auth 的标准 social provider 端点
    const baseUrl = process.env.NODE_ENV === 'production' 
      ? 'https://kf.huozhong.in' 
      : 'http://127.0.0.1:60325';
    
    // 转发所有 cookies
    const cookies = c.req.header('cookie') || '';
    
    // 使用标准的 social provider 端点
    const response = await fetch(`${baseUrl}/api/auth/sign-in/social`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Cookie': cookies,
      },
      body: JSON.stringify({
        provider,  // 'google' 或其他 provider
        callbackURL,
      }),
    });
    
    console.log('[Start OAuth] Better-Auth response status:', response.status);
    
    // 如果是重定向响应
    const location = response.headers.get('location');
    if (location) {
      console.log('[Start OAuth] Redirecting to:', location);
      return c.redirect(location);
    }
    
    // 如果是 JSON 响应
    const contentType = response.headers.get('content-type');
    if (contentType?.includes('application/json')) {
      const data = await response.json() as { url?: string; redirect?: boolean };
      console.log('[Start OAuth] Better-Auth returned:', data);
      
      if (data.url) {
        console.log('[Start OAuth] Redirecting to OAuth URL:', data.url);
        
        // 复制所有 set-cookie headers
        const setCookies = response.headers.getSetCookie?.() || [];
        const headers: Record<string, string> = {};
        
        if (setCookies.length > 0) {
          console.log('[Start OAuth] Setting cookies:', setCookies);
          // Hono 中设置多个 cookies 需要逐个设置
          setCookies.forEach(cookie => {
            const [nameValue] = cookie.split(';');
            const [name, value] = nameValue.split('=');
            c.header('Set-Cookie', cookie, { append: true });
          });
        }
        
        return c.redirect(data.url);
      }
    }
    
    // 其他情况返回错误
    const text = await response.text();
    console.error('[Start OAuth] Unexpected response:', text);
    return c.json({ error: 'Unexpected response from Better-Auth', response: text }, 500);
    
  } catch (error) {
    console.error('[Start OAuth] Error:', error);
    return c.json({ 
      error: 'Failed to start OAuth', 
      details: error instanceof Error ? error.message : String(error) 
    }, 500);
  }
});

// Forward OAuth request to Better-Auth's sign-in endpoint
app.post('/login-google', async (c) => {
  try {
    // Use Better-Auth's social provider endpoint
    const baseUrl = process.env.NODE_ENV === 'production' 
      ? 'https://kf.huozhong.in' 
      : 'http://127.0.0.1:60325';
    
    const response = await fetch(`${baseUrl}/api/auth/sign-in/social`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        provider: 'google',  // 改为 provider
        callbackURL: '/auth-callback-bridge',
      }),
    });
    
    // Better-Auth should return a redirect response
    if (response.status === 302 || response.headers.get('location')) {
      const location = response.headers.get('location');
      console.log('[Login Google] Better-Auth redirecting to:', location);
      return c.redirect(location || '/');
    }
    
    // Try to parse response
    const text = await response.text();
    console.log('[Login Google] Better-Auth response:', text);
    
    try {
      const data = JSON.parse(text) as { url?: string; error?: string };
      if (data.url) {
        console.log('[Login Google] Better-Auth URL:', data.url);
        return c.redirect(data.url);
      }
      return c.json({ error: 'No redirect URL from Better-Auth', response: data }, 500);
    } catch {
      return c.json({ error: 'Invalid response from Better-Auth', response: text }, 500);
    }
  } catch (error) {
    console.error('[Login Google] Error:', error);
    return c.json({ error: 'Failed to initiate OAuth', details: String(error) }, 500);
  }
});

// OAuth回调成功后的桥接端点 - 将用户信息重定向到Python API
app.get('/auth-callback-bridge', async (c) => {
  try {
    console.log('[Auth Bridge] Processing OAuth callback...');
    
    // 从better-auth获取当前session
    const authRequest = c.req.raw;
    const session = await auth.api.getSession({ 
      headers: authRequest.headers 
    });
    
    console.log('[Auth Bridge] Session:', session);
    
    if (session?.user) {
      const user = session.user;
      const provider = c.req.query('provider') || 'google';
      
      console.log('[Auth Bridge] User authenticated:', {
        provider,
        email: user.email,
        name: user.name
      });
      
      // 构建重定向到Python API的URL
      const isDev = process.env.NODE_ENV !== 'production';
      const pythonApiUrl = isDev 
        ? 'http://127.0.0.1:60315/api/auth/success'
        : 'https://你的生产API地址/api/auth/success'; // TODO: 配置生产环境
      
      const params = new URLSearchParams({
        provider,
        oauth_id: user.id,
        email: user.email,
        name: user.name,
        avatar_url: user.image || ''
      });
      
      const redirectUrl = `${pythonApiUrl}?${params.toString()}`;
      console.log('[Auth Bridge] Redirecting to:', redirectUrl);
      
      return c.redirect(redirectUrl);
    } else {
      console.error('[Auth Bridge] No session found');
      return c.text('No session found. Please try logging in again.', 401);
    }
  } catch (error) {
    console.error('[Auth Bridge] Error:', error);
    return c.text('Authentication error occurred. Please try again.', 500);
  }
});

// OAuth成功页面 - 自动重定向到Python API
app.get('/oauth-success', async (c) => {
  try {
    // 直接重定向到桥接端点
    return c.redirect('/auth-callback-bridge?provider=google');
  } catch (error) {
    console.error('[OAuth Success] Redirect error:', error);
    return c.html(`
      <!DOCTYPE html>
      <html>
      <head>
          <title>OAuth Success - Knowledge Focus</title>
          <meta charset="utf-8">
      </head>
      <body>
          <h1>登录成功</h1>
          <p>正在跳转...</p>
          <script>
            setTimeout(() => {
              window.location.href = '/auth-callback-bridge?provider=google';
            }, 1000);
          </script>
      </body>
      </html>
    `)
  }
})

// 根路由
app.get('/', (c) => {
  return c.html(`
    <!DOCTYPE html>
    <html>
      <head>
        <title>Knowledge Focus Auth Server</title>
        <style>
          body { font-family: system-ui; padding: 2rem; max-width: 800px; margin: 0 auto; }
          h1 { color: #667eea; }
          .endpoint { background: #f7fafc; padding: 1rem; margin: 0.5rem 0; border-radius: 8px; }
          .method { display: inline-block; padding: 0.25rem 0.5rem; background: #667eea; color: white; border-radius: 4px; font-size: 0.875rem; margin-right: 0.5rem; }
          button { background: #48bb78; color: white; border: none; padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; font-size: 1rem; }
          button:hover { background: #38a169; }
          code { background: #e2e8f0; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.875rem; }
          .result { margin-top: 1rem; padding: 0.5rem; background: #fff5f5; border-left: 3px solid #f56565; border-radius: 4px; font-size: 0.875rem; }
          .success { background: #f0fff4; border-left-color: #48bb78; }
          .form-method { background: #fef5e7; padding: 1rem; border-left: 3px solid #f39c12; }
          .form-method button { background: #f39c12; }
          .form-method button:hover { background: #d68910; }
        </style>
      </head>
      <body>
        <h1>Knowledge Focus Auth Server</h1>
        <p>Authentication server is running on port 60325</p>
        
        <h2>🔥 正确的 OAuth 流程 (使用表单提交):</h2>
        
        <div class="endpoint form-method">
          <p><strong>✅ 推荐方法: 使用服务端转发</strong></p>
          <p>服务端转发到 Better-Auth,然后重定向到 Google</p>
          <form action="/start-oauth" method="POST" style="margin-top: 1rem;">
            <input type="hidden" name="providerId" value="google" />
            <input type="hidden" name="callbackURL" value="/auth-callback-bridge" />
            <button type="submit">🚀 Login with Google</button>
          </form>
        </div>
        
        <hr style="margin: 2rem 0;">
        
        <h2>调试方法 (使用 Fetch API):</h2>
        
        <div class="endpoint">
          <button onclick="startOAuth()">Login with Google (Fetch API)</button>
          <div id="result"></div>
        </div>
        
        <div class="endpoint">
          <strong>Debug Log:</strong>
          <pre id="debug" style="background: #2d3748; color: #e2e8f0; padding: 0.5rem; border-radius: 4px; overflow-x: auto; font-size: 0.75rem;">Waiting for test...</pre>
        </div>
        
        <script>
          async function startOAuth() {
            const resultDiv = document.getElementById('result');
            const debugDiv = document.getElementById('debug');
            
            resultDiv.innerHTML = '<p>Starting OAuth...</p>';
            resultDiv.className = 'result';
            
            let debugLog = '';
            function log(msg) {
              debugLog += msg + '\\n';
              debugDiv.textContent = debugLog;
              console.log(msg);
            }
            
            try {
              log('[1] Sending POST to /api/auth/sign-in/social');
              log('[1] Body: ' + JSON.stringify({
                provider: 'google',
                callbackURL: '/auth-callback-bridge',
              }));
              
              const response = await fetch('/api/auth/sign-in/social', {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({
                  provider: 'google',
                  callbackURL: '/auth-callback-bridge',
                }),
              });
              
              log('[2] Response status: ' + response.status);
              log('[2] Response redirected: ' + response.redirected);
              log('[2] Response type: ' + response.type);
              log('[2] Response URL: ' + response.url);
              
              // 检查 content-type
              const contentType = response.headers.get('content-type') || '';
              log('[3] Content-Type: ' + contentType);
              
              if (response.redirected) {
                log('[4] Following redirect to: ' + response.url);
                resultDiv.innerHTML = '<p class="success">Redirecting to Google OAuth...</p>';
                window.location.href = response.url;
                return;
              }
              
              // 读取响应体
              const text = await response.text();
              log('[5] Response body length: ' + text.length);
              log('[5] Response body preview: ' + text.substring(0, 200));
              
              if (contentType.includes('application/json')) {
                try {
                  const data = JSON.parse(text);
                  log('[6] Parsed JSON: ' + JSON.stringify(data, null, 2));
                  
                  if (data.url) {
                    log('[7] Found redirect URL, navigating...');
                    resultDiv.innerHTML = '<p class="success">Redirecting to: ' + data.url + '</p>';
                    window.location.href = data.url;
                  } else {
                    log('[ERROR] No URL in response');
                    resultDiv.innerHTML = '<p>Error: No redirect URL</p>';
                  }
                } catch (e) {
                  log('[ERROR] Failed to parse JSON: ' + e.message);
                  resultDiv.innerHTML = '<p>Error: Invalid JSON response</p>';
                }
              } else {
                log('[ERROR] Unexpected content type: ' + contentType);
                resultDiv.innerHTML = '<p>Error: Unexpected response type</p>';
              }
              
            } catch (error) {
              log('[FATAL ERROR] ' + error.message);
              log('[STACK] ' + error.stack);
              resultDiv.innerHTML = '<p>Error: ' + error.message + '</p>';
              resultDiv.className = 'result';
            }
          }
        </script>
        
        <p style="margin-top: 2rem; color: #718096; font-size: 0.875rem;">
          <strong>提示:</strong> 使用表单提交方法可以确保 Better-Auth 正确处理 OAuth state 和 CSRF 验证。<br>
          Make sure Python API is running on port 60315.
        </p>
      </body>
    </html>
  `)
})

export default app