/**
 * Cloudflare Workers/Pages 环境类型定义
 */
export interface Env {
  // Cloudflare D1 数据库绑定
  knowledge_focus_db: D1Database;
  
  // 环境变量
  NODE_ENV?: string;
  GOOGLE_CLIENT_ID?: string;
  GOOGLE_CLIENT_SECRET?: string;
  GITHUB_CLIENT_ID?: string;
  GITHUB_CLIENT_SECRET?: string;
  
  // Better-Auth 会用到的变量
  BETTER_AUTH_SECRET?: string;
  BETTER_AUTH_URL?: string;
  
  // Python API 地址
  PYTHON_API_URL?: string;
}

// Cloudflare Bindings 类型
declare global {
  interface CloudflareBindings extends Env {}
}

export {};
