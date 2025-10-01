import { betterAuth } from "better-auth"
import { createAuthMiddleware } from "better-auth/api"
import { drizzleAdapter } from "better-auth/adapters/drizzle"
import { db } from "./database"
import { user, session, account, verification } from "./auth-schema"

export const auth = betterAuth({
  baseURL: process.env.NODE_ENV === 'production' 
    ? "https://kf.huozhong.in" 
    : "http://127.0.0.1:60325",
  
  database: drizzleAdapter(db, {
    provider: "sqlite",
    schema: {
      user,
      session,
      account,
      verification,
    },
  }),

  session: {
    updateAge: 24 * 60 * 60, // 24 hours
    expiresIn: 60 * 60 * 24 * 7, // 7 days
  },

  advanced: {
    disableCSRFCheck: true,
    defaultCookieAttributes: {
      sameSite: "lax",
      secure: process.env.NODE_ENV === 'production',
      httpOnly: true
    }
  },

  // 使用标准 socialProviders 而不是 genericOAuth
  // 这样 Better-Auth 会正确处理 Google OAuth (不使用 PKCE)
  socialProviders: {
    google: {
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
      redirectURI: process.env.NODE_ENV === 'production'
        ? "https://kf.huozhong.in/api/auth/callback/google"
        : "http://127.0.0.1:60325/api/auth/callback/google",
    },
    github: {
      clientId: process.env.GITHUB_CLIENT_ID as string,
      clientSecret: process.env.GITHUB_CLIENT_SECRET as string,
      redirectURI: process.env.NODE_ENV === 'production'
        ? "https://kf.huozhong.in/api/auth/callback/github"
        : "http://127.0.0.1:60325/api/auth/callback/github",
    },
  },

  trustedOrigins: [
    "http://127.0.0.1:60325",
    "http://127.0.0.1:60315",
    "http://localhost:60325",
    "http://localhost:60315",
    "http://localhost:1420",
    "https://kf.huozhong.in"
  ],
})
