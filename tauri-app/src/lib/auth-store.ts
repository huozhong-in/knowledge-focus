import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

interface User {
  id: string;
  oauth_provider: string;
  oauth_id: string;
  email: string;
  name: string;
  avatar_url?: string;
  created_at: string;
  updated_at: string;
}

interface AuthPayload {
  user: User;
  token: string;
  expires_at: string;
}

interface AuthState {
  user: User | null;
  token: string | null;
  tokenExpiresAt: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  
  // Actions
  login: (provider: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  initAuthListener: () => Promise<() => void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      tokenExpiresAt: null,
      isAuthenticated: false,
      isLoading: false,

      // 初始化 OAuth 事件监听器
      initAuthListener: async () => {
        try {
          // 监听来自 Rust 的 OAuth 登录成功事件
          const unlisten = await listen<{ payload: AuthPayload }>(
            "oauth-login-success",
            (event) => {
              console.log("✅ 收到 OAuth 登录成功事件:", event.payload);
              const { user, token, expires_at } = event.payload.payload;

              // 更新状态
              set({
                user,
                token,
                tokenExpiresAt: expires_at,
                isAuthenticated: true,
                isLoading: false,
              });

              console.log("✅ 用户状态已更新:", user);
            }
          );

          console.log("� OAuth 事件监听器已初始化");
          return unlisten; // 返回取消监听函数
        } catch (error) {
          console.error("❌ 初始化 OAuth 监听器失败:", error);
          return () => {}; // 返回空函数作为降级
        }
      },

      login: async (provider: string) => {
        set({ isLoading: true });
        try {
          console.log('🔍 开始登录流程, provider:', provider);
          
          if (await isTauri()) {
            console.log('� Tauri 环境，使用外部浏览器 OAuth');
            
            // 在外部浏览器中打开 OAuth URL
            const oauthUrl = `http://127.0.0.1:60325/start-oauth`;
            console.log('🚀 打开 OAuth 页面:', oauthUrl);
            
            const { open } = await import("@tauri-apps/plugin-shell");
            await open(oauthUrl);
            
            console.log('⏳ 等待 bridge event 返回登录结果...');
            // 注意：isLoading 状态会在收到 bridge event 后更新为 false
          } else {
            console.log('🌐 Web 环境，暂不支持');
            set({ isLoading: false });
          }
        } catch (error) {
          console.error('❌ 登录失败:', error);
          set({ isLoading: false });
        }
      },

      logout: async () => {
        try {
          const token = get().token;
          if (!token) {
            console.log('⚠️ 没有 token，直接清除本地状态');
            set({ 
              user: null, 
              token: null, 
              tokenExpiresAt: null,
              isAuthenticated: false 
            });
            return;
          }

          // 调用 Python API 登出
          const response = await fetch('http://127.0.0.1:60315/api/user/logout', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
          });

          if (!response.ok) {
            console.error('❌ 登出 API 调用失败:', response.status);
          }

          // 无论 API 调用是否成功，都清除本地状态
          set({ 
            user: null, 
            token: null, 
            tokenExpiresAt: null,
            isAuthenticated: false 
          });
          console.log('✅ 已登出');
        } catch (error) {
          console.error('❌ 登出失败:', error);
          // 即使出错也清除本地状态
          set({ 
            user: null, 
            token: null, 
            tokenExpiresAt: null,
            isAuthenticated: false 
          });
        }
      },

      checkAuth: async () => {
        try {
          const token = get().token;
          const expiresAt = get().tokenExpiresAt;

          if (!token || !expiresAt) {
            console.log('⚠️ 没有 token 或过期时间');
            set({ user: null, isAuthenticated: false });
            return;
          }

          // 检查 token 是否过期
          const expiresDate = new Date(expiresAt);
          if (expiresDate < new Date()) {
            console.log('⚠️ Token 已过期');
            set({ 
              user: null, 
              token: null, 
              tokenExpiresAt: null,
              isAuthenticated: false 
            });
            return;
          }

          // 调用 API 验证 token
          const response = await fetch('http://127.0.0.1:60315/api/user/validate-token', {
            method: 'GET',
            headers: {
              'Authorization': `Bearer ${token}`,
            },
          });

          if (!response.ok) {
            console.error('❌ Token 验证失败:', response.status);
            set({ 
              user: null, 
              token: null, 
              tokenExpiresAt: null,
              isAuthenticated: false 
            });
            return;
          }

          const data = await response.json();
          if (data.valid && data.user) {
            set({ 
              user: data.user,
              isAuthenticated: true 
            });
            console.log('✅ Token 有效，用户已认证');
          } else {
            console.log('⚠️ Token 无效');
            set({ 
              user: null, 
              token: null, 
              tokenExpiresAt: null,
              isAuthenticated: false 
            });
          }
        } catch (error) {
          console.error('❌ 检查认证状态失败:', error);
          set({ 
            user: null, 
            token: null, 
            tokenExpiresAt: null,
            isAuthenticated: false 
          });
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ 
        user: state.user,
        token: state.token,
        tokenExpiresAt: state.tokenExpiresAt,
        isAuthenticated: state.isAuthenticated 
      }),
    }
  )
);
