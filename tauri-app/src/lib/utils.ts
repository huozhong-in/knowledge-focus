import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import Database from '@tauri-apps/plugin-sql';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export async function loadDB() {
  const db = await Database.load('sqlite:knowledge-focus.db');
  await db.execute(`
    CREATE TABLE IF NOT EXISTS settings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      key TEXT NOT NULL UNIQUE,
      value TEXT NOT NULL
    );
  `);
  
  return db;
}
