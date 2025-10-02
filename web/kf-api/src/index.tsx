// 生产环境入口点 - 仅用于 Cloudflare Workers/Pages

// 对于开发环境，请直接使用 index.dev.tsx
// 对于生产环境，使用此文件的默认导出

// 在生产构建中，不导出 app (避免导入开发模块)
export const app = null;

// Cloudflare Workers/Pages 生产环境导出
export default {
  async fetch(request: Request, env: any) {
    console.log('[Production] Handling request in Cloudflare Workers');
    try {
      const prodModule = await import('./index.prod');
      return prodModule.default.fetch(request, env);
    } catch (error) {
      console.error('[Production] Failed to load production module:', error);
      return new Response(`Internal Server Error: ${error}`, { status: 500 });
    }
  }
};