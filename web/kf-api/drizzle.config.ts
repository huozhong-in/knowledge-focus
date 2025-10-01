import { defineConfig } from 'drizzle-kit';

export default defineConfig({
  out: './drizzle',
  schema: './src/auth-schema.ts',
  dialect: 'sqlite',
  dbCredentials: {
    url: './kfuser.db',
  },
});