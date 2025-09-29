import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { auth } from './auth'

const app = new Hono()

// CORS配置 - 允许来自Tauri应用的请求
app.use('*', cors({
  origin: [
    'http://localhost:3000',
    'http://127.0.0.1:3000', 
    'http://localhost:1420',
    'http://127.0.0.1:1420',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'tauri://localhost',
    'https://tauri.localhost'
  ],
  credentials: true,
  allowMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowHeaders: ['Content-Type', 'Authorization', 'X-Requested-With']
}))

// 身份验证路由
app.on(['GET', 'POST'], '/api/auth/*', (c) => auth.handler(c.req.raw))

// 根路由
app.get('/', (c) => {
  return c.html(`
    <!DOCTYPE html>
    <html>
      <head>
        <title>Knowledge Focus Auth Server</title>
      </head>
      <body>
        <h1>Knowledge Focus Auth Server</h1>
        <p>Authentication server is running via Vite dev server on port 5173</p>
        <p>Auth endpoints available at /api/auth/*</p>
      </body>
    </html>
  `)
})

export default app