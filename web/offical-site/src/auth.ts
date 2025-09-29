import { betterAuth } from "better-auth"
import { tauri } from "@daveyplate/better-auth-tauri/plugin"
import { drizzleAdapter } from "better-auth/adapters/drizzle"
import { db } from "./database"
import { user, session, account, verification } from "./auth-schema"

export const auth = betterAuth({
  database: drizzleAdapter(db, {
    provider: "sqlite",
    schema: {
      user,
      session,
      account,
      verification,
    },
  }),

  socialProviders: {
    google: {
      prompt: "select_account",
      clientId: process.env.GOOGLE_CLIENT_ID as string,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET as string,
    },
    github: {
      clientId: process.env.GITHUB_CLIENT_ID as string,
      clientSecret: process.env.GITHUB_CLIENT_SECRET as string,
    },
  },

  plugins: [
    tauri({
      scheme: "knowledge-focus", // 你的App scheme
      callbackURL: "/dashboard",
      successText: "登录成功！请返回应用。",
      debugLogs: true
    })
  ],
  
  // 自定义用户模型支持VIP状态
  user: {
    additionalFields: {
      vipLevel: {
        type: "string",
        defaultValue: "free"
      },
      vipExpiresAt: {
        type: "date",
        required: false
      }
    }
  }
})
