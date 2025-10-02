import { isTauri } from "@tauri-apps/api/core";
import { fetch as tauriFetch } from "@tauri-apps/plugin-http";
import { platform } from "@tauri-apps/plugin-os";
import { createAuthClient } from "better-auth/react";
import { genericOAuthClient } from "better-auth/client/plugins";

// macOS cookies支持：在macOS桌面环境下使用Tauri HTTP插件
export const authClient = createAuthClient({
  baseURL: import.meta.env.MODE === 'development' 
    ? "http://127.0.0.1:60325"  // 开发环境：本地 auth 服务器
    : "https://kf.huozhong.in", // 生产环境：Cloudflare Pages 部署地址
  plugins: [
    genericOAuthClient()
  ],
  fetchOptions: {
    customFetchImpl: (...params) =>
      isTauri() && platform() === "macos" && window.location.protocol === "tauri:"
        ? tauriFetch(...params)
        : fetch(...params)
  }
});