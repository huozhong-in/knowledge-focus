import build from '@hono/vite-build/cloudflare-pages'
import devServer from '@hono/vite-dev-server'
import adapter from '@hono/vite-dev-server/cloudflare'
import { defineConfig } from 'vite'

export default defineConfig(({ command, mode }) => {
  const isProduction = command === 'build' || mode === 'production';
  
  const config: any = {
    server: {
      port: 60325,
      host: '127.0.0.1'
    },
    plugins: [
      build(),
      devServer({
        adapter,
        entry: isProduction ? 'src/index.tsx' : 'src/index.dev.tsx'
      })
    ],
    resolve: {
      alias: {}
    }
  };

  if (isProduction) {
    // 只在生产构建时,将 better-sqlite3 替换为空模块
    config.resolve.alias['better-sqlite3'] = new URL('./src/database.stub.ts', import.meta.url).pathname;
  }
  // 开发环境不设置别名，使用真正的 better-sqlite3

  return config;
})
