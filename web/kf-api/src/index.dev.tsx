import { Hono } from 'hono'
import { cors } from 'hono/cors'

// 开发环境: 使用 better-sqlite3
import { betterAuth } from "better-auth"
import { drizzleAdapter } from "better-auth/adapters/drizzle"
import { drizzle } from 'drizzle-orm/better-sqlite3'
import Database from 'better-sqlite3'
import { user, session, account, verification } from "./auth-schema"

const sqlite = new Database(process.env.DATABASE_URL || 'kfuser.db');
const db = drizzle(sqlite);

export const auth = betterAuth({
  baseURL: "http://127.0.0.1:60325",
  
  database: drizzleAdapter(db, {
    provider: "sqlite",
    schema: { user, session, account, verification },
  }),

  session: {
    updateAge: 24 * 60 * 60, // 24 hours
    expiresIn: 60 * 60 * 24 * 7, // 7 days
  },

  advanced: {
    disableCSRFCheck: true,
    defaultCookieAttributes: {
      sameSite: "lax",
      secure: false,
      httpOnly: true
    }
  },

  socialProviders: {
    google: {
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
      redirectURI: "http://127.0.0.1:60325/api/auth/callback/google",
    },
    github: {
      clientId: process.env.GITHUB_CLIENT_ID!,
      clientSecret: process.env.GITHUB_CLIENT_SECRET!,
      redirectURI: "http://127.0.0.1:60325/api/auth/callback/github",
    },
  },

  trustedOrigins: [
    "http://127.0.0.1:60325",
    "http://127.0.0.1:60315",
    "http://localhost:60325",
    "http://localhost:60315",
    "http://localhost:1420",
  ],
});

const app = new Hono();

// CORS配置
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
  return auth.handler(c.req.raw);
})

// OAuth 启动端点 - GET 版本
app.get('/start-oauth', async (c) => {
  const provider = c.req.query('provider') || 'google';
  console.log('[Start OAuth GET] Rendering auto-submit form for provider:', provider);
  
  return c.html(`
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="utf-8">
        <title>Starting OAuth...</title>
        <style>
          body {
            font-family: system-ui, -apple-system, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
          }
          .container {
            text-align: center;
            padding: 2rem;
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
          }
          .spinner {
            width: 50px;
            height: 50px;
            margin: 0 auto 1rem;
            border: 4px solid rgba(255, 255, 255, 0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 1s linear infinite;
          }
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
          h1 { margin: 0 0 0.5rem; font-size: 1.5rem; }
          p { margin: 0; opacity: 0.9; font-size: 0.875rem; }
        </style>
      </head>
      <body>
        <div class="container">
          <div class="spinner"></div>
          <h1>正在启动 OAuth 登录</h1>
          <p>即将跳转到 ${provider === 'google' ? 'Google' : provider} 授权页面...</p>
        </div>
        
        <form id="oauth-form" action="/start-oauth" method="POST" style="display: none;">
          <input type="hidden" name="providerId" value="${provider}" />
          <input type="hidden" name="callbackURL" value="/auth-callback-bridge" />
        </form>
        
        <script>
          document.getElementById('oauth-form').submit();
        </script>
      </body>
    </html>
  `);
});

// OAuth 启动端点 - POST 版本
app.post('/start-oauth', async (c) => {
  try {
    console.log('[Start OAuth] Initiating OAuth flow...');
    
    const body = await c.req.parseBody();
    const provider = body.providerId as string || 'google';
    const baseCallbackURL = body.callbackURL as string || '/auth-callback-bridge';
    const callbackURL = `${baseCallbackURL}?provider=${encodeURIComponent(provider)}`;
    
    console.log('[Start OAuth] Params:', { provider, callbackURL });
    
    const baseUrl = "http://127.0.0.1:60325";
    const cookies = c.req.header('cookie') || '';
    
    const response = await fetch(`${baseUrl}/api/auth/sign-in/social`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Cookie': cookies,
      },
      body: JSON.stringify({ provider, callbackURL }),
    });
    
    console.log('[Start OAuth] Better-Auth response status:', response.status);
    
    const location = response.headers.get('location');
    if (location) {
      console.log('[Start OAuth] Redirecting to:', location);
      return c.redirect(location);
    }
    
    const contentType = response.headers.get('content-type');
    if (contentType?.includes('application/json')) {
      const data = await response.json() as { url?: string };
      console.log('[Start OAuth] Better-Auth returned:', data);
      
      if (data.url) {
        console.log('[Start OAuth] Redirecting to OAuth URL:', data.url);
        
        const setCookies = response.headers.getSetCookie?.() || [];
        if (setCookies.length > 0) {
          console.log('[Start OAuth] Setting cookies:', setCookies);
          setCookies.forEach(cookie => {
            c.header('Set-Cookie', cookie, { append: true });
          });
        }
        
        return c.redirect(data.url);
      }
    }
    
    return c.json({ error: 'Failed to get OAuth URL', response: await response.text() }, 500);
  } catch (error) {
    console.error('[Start OAuth] Error:', error);
    return c.json({ error: 'Failed to initiate OAuth', details: String(error) }, 500);
  }
});

// OAuth回调桥接端点
app.get('/auth-callback-bridge', async (c) => {
  try {
    console.log('[Auth Bridge] Processing OAuth callback...');
    console.log('[Auth Bridge] Query params:', Object.fromEntries(new URL(c.req.url).searchParams));
    
    const session = await auth.api.getSession({ 
      headers: c.req.raw.headers 
    });
    
    console.log('[Auth Bridge] Session:', session);
    
    if (session?.user) {
      const user = session.user;
      let provider = c.req.query('provider');
      
      if (!provider) {
        console.warn('[Auth Bridge] No provider in URL query, defaulting to unknown');
        provider = 'unknown';
      }
      
      console.log('[Auth Bridge] User authenticated:', {
        provider,
        email: user.email,
        name: user.name
      });
      
      const pythonApiUrl = 'http://127.0.0.1:60315/api/auth/success';
      
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

// OAuth成功页面
app.get('/oauth-success', async (c) => {
  try {
    const provider = c.req.query('provider') || 'unknown';
    console.log('[OAuth Success] Redirecting with provider:', provider);
    
    return c.redirect(`/auth-callback-bridge?provider=${encodeURIComponent(provider)}`);
  } catch (error) {
    console.error('[OAuth Success] Redirect error:', error);
    
    const provider = c.req.query('provider') || 'unknown';
    
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
              window.location.href = '/auth-callback-bridge?provider=${encodeURIComponent(provider)}';
            }, 1000);
          </script>
      </body>
      </html>
    `);
  }
});

// 健康检查
app.get('/health', (c) => {
  return c.json({ 
    status: 'ok', 
    env: 'development',
    database: 'better-sqlite3'
  });
});

// 根路由
app.get('/', (c) => {
  return c.json({ 
    message: 'Knowledge Focus Auth Server (Development)',
    env: 'development',
    database: 'better-sqlite3'
  });
});

// 开发环境导出
export { app };

// 开发环境默认导出 (供 vite-dev-server 使用)
export default app;