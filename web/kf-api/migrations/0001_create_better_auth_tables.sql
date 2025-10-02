-- Better-Auth Required Tables for Cloudflare D1
-- Generated for: Knowledge Focus Auth Server
-- Date: 2025-10-02

-- User Table
CREATE TABLE IF NOT EXISTS "user" (
  "id" TEXT PRIMARY KEY NOT NULL,
  "name" TEXT NOT NULL,
  "email" TEXT NOT NULL UNIQUE,
  "email_verified" INTEGER DEFAULT 0 NOT NULL,
  "image" TEXT,
  "created_at" INTEGER DEFAULT (unixepoch()) NOT NULL,
  "updated_at" INTEGER DEFAULT (unixepoch()) NOT NULL
);

-- Session Table
CREATE TABLE IF NOT EXISTS "session" (
  "id" TEXT PRIMARY KEY NOT NULL,
  "expires_at" INTEGER NOT NULL,
  "token" TEXT NOT NULL UNIQUE,
  "created_at" INTEGER DEFAULT (unixepoch()) NOT NULL,
  "updated_at" INTEGER DEFAULT (unixepoch()) NOT NULL,
  "ip_address" TEXT,
  "user_agent" TEXT,
  "user_id" TEXT NOT NULL,
  FOREIGN KEY ("user_id") REFERENCES "user"("id") ON DELETE CASCADE
);

-- Account Table (OAuth Providers)
CREATE TABLE IF NOT EXISTS "account" (
  "id" TEXT PRIMARY KEY NOT NULL,
  "account_id" TEXT NOT NULL,
  "provider_id" TEXT NOT NULL,
  "user_id" TEXT NOT NULL,
  "access_token" TEXT,
  "refresh_token" TEXT,
  "id_token" TEXT,
  "access_token_expires_at" INTEGER,
  "refresh_token_expires_at" INTEGER,
  "scope" TEXT,
  "password" TEXT,
  "created_at" INTEGER DEFAULT (unixepoch()) NOT NULL,
  "updated_at" INTEGER DEFAULT (unixepoch()) NOT NULL,
  FOREIGN KEY ("user_id") REFERENCES "user"("id") ON DELETE CASCADE
);

-- Verification Table (Email Verification, Password Reset, etc.)
CREATE TABLE IF NOT EXISTS "verification" (
  "id" TEXT PRIMARY KEY NOT NULL,
  "identifier" TEXT NOT NULL,
  "value" TEXT NOT NULL,
  "expires_at" INTEGER NOT NULL,
  "created_at" INTEGER DEFAULT (unixepoch()) NOT NULL,
  "updated_at" INTEGER DEFAULT (unixepoch()) NOT NULL
);

-- Indexes for Performance
CREATE INDEX IF NOT EXISTS "idx_session_user_id" ON "session"("user_id");
CREATE INDEX IF NOT EXISTS "idx_session_token" ON "session"("token");
CREATE INDEX IF NOT EXISTS "idx_account_user_id" ON "account"("user_id");
CREATE INDEX IF NOT EXISTS "idx_account_provider" ON "account"("provider_id", "account_id");
CREATE INDEX IF NOT EXISTS "idx_user_email" ON "user"("email");
