/**
 * 开发环境数据库配置
 * 使用 better-sqlite3 (本地 SQLite 文件)
 */
import { drizzle } from 'drizzle-orm/better-sqlite3';
import Database from 'better-sqlite3';

const sqlite = new Database(process.env.DATABASE_URL || 'kfuser.db');
export const db = drizzle(sqlite);
