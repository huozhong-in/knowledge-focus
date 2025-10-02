/**
 * Stub for better-sqlite3 in production build
 * This file is used to replace better-sqlite3 in Cloudflare Workers environment
 */
export default class Database {
  constructor(_path: string) {
    throw new Error('better-sqlite3 is not available in Cloudflare Workers');
  }
}
