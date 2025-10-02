import { drizzle as drizzleD1 } from 'drizzle-orm/d1';
import type { Env } from './env';

// 开发环境数据库实例
let devDb: any = null;

/**
 * 获取数据库实例
 * @param env - Cloudflare Workers/Pages 环境对象 (生产环境)
 * @returns Drizzle ORM 实例
 */
export function getDatabase(env?: Env) {
  // 生产环境: 使用 Cloudflare D1
  if (env?.knowledge_focus_db) {
    console.log('[Database] Using Cloudflare D1');
    return drizzleD1(env.knowledge_focus_db);
  }
  
  // 开发环境: 使用 better-sqlite3 (只在真正需要时才加载)
  console.log('[Database] Using better-sqlite3 for development');
  throw new Error('Development database should not be used in Cloudflare Workers environment');
}

// 危险的默认导出 - 移除,因为会在顶层触发 better-sqlite3
// export const db = getDevDb();