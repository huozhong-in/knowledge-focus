import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { load } from "@tauri-apps/plugin-store";
import { appDataDir, join } from "@tauri-apps/api/path";

// 环境配置
const isDevelopment = import.meta.env.MODE === 'development';
const AUTH_BASE_URL = isDevelopment 
  ? 'http://127.0.0.1:60325'  // 开发环境：本地 auth 服务器
  : 'https://kf.huozhong.in'; // 生产环境：Cloudflare Pages 部署地址

const API_BASE_URL = 'http://127.0.0.1:60315'

// 创建自定义存储引擎 (使用与 App.tsx 相同的模式)
const createTauriStorage = () => {
  return {
    getItem: async (name: string): Promise<string | null> => {
      try {
        const appDataPath = await appDataDir();
        const storePath = await join(appDataPath, 'auth.json');
        const store = await load(storePath, { autoSave: false });
        const value = await store.get<string>(name);
        return value ?? null;
      } catch (error) {
        console.error('Failed to get item from Tauri Store:', error);
        return null;
      }
    },
    setItem: async (name: string, value: string): Promise<void> => {
      try {
        const appDataPath = await appDataDir();
        const storePath = await join(appDataPath, 'auth.json');
        const store = await load(storePath, { autoSave: false });
        await store.set(name, value);
        await store.save();
      } catch (error) {
        console.error('Failed to set item in Tauri Store:', error);
      }
    },
    removeItem: async (name: string): Promise<void> => {
      try {
        const appDataPath = await appDataDir();
        const storePath = await join(appDataPath, 'auth.json');
        const store = await load(storePath, { autoSave: false });
        await store.delete(name);
        await store.save();
      } catch (error) {
        console.error('Failed to remove item from Tauri Store:', error);
      }
    },
  };
};

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
  success: boolean;
  user: User;
  token: string;
  token_expires_at: string;
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
          const unlisten = await listen<AuthPayload>(
            "oauth-login-success",
            (event) => {
              console.log("✅ 收到 OAuth 登录成功事件:");
              console.log("   完整事件:", event);
              console.log("   Payload:", event.payload);
              
              // Rust 直接发送 payload,不是嵌套的 payload.payload
              const { user, token, token_expires_at } = event.payload;

              console.log("   解析后 - User:", user);
              console.log("   解析后 - Token:", token?.substring(0, 20) + "...");
              console.log("   解析后 - Expires:", token_expires_at);

              // 更新状态
              set({
                user,
                token,
                tokenExpiresAt: token_expires_at,
                isAuthenticated: true,
                isLoading: false,
              });

              console.log("✅ 用户状态已更新,UI 应该自动刷新");
            }
          );

          console.log("🎧 OAuth 事件监听器已初始化");
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
            const oauthUrl = `${AUTH_BASE_URL}/start-oauth?provider=${provider}`;
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
          const user = get().user;
          
          if (!token || !user) {
            console.log('⚠️ 没有 token 或用户信息，直接清除本地状态');
            set({ 
              user: null, 
              token: null, 
              tokenExpiresAt: null,
              isAuthenticated: false 
            });
            return;
          }

          // 调用 Python API 登出
          const response = await fetch(`${API_BASE_URL}/api/user/logout`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ user_id: user.id }),
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
          const currentUser = get().user;

          console.log('🔍 检查认证状态...');
          console.log('   Token:', token ? `${token.substring(0, 20)}...` : 'null');
          console.log('   ExpiresAt:', expiresAt);
          console.log('   Current User:', currentUser?.email);

          if (!token || !expiresAt) {
            console.log('⚠️ 没有 token 或过期时间，清除认证状态');
            set({ user: null, isAuthenticated: false });
            return;
          }

          // 检查 token 是否过期
          const expiresDate = new Date(expiresAt);
          const now = new Date();
          console.log('   Token 过期时间:', expiresDate.toISOString());
          console.log('   当前时间:', now.toISOString());
          
          if (expiresDate < now) {
            console.log('⚠️ Token 已过期，清除认证状态');
            set({ 
              user: null, 
              token: null, 
              tokenExpiresAt: null,
              isAuthenticated: false 
            });
            return;
          }

          console.log('✅ Token 未过期，调用 API 验证...');
          
          // 调用 API 验证 token (注意: 后端要求 POST 请求)
          const response = await fetch(`${API_BASE_URL}/api/user/validate-token`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ token }),
          });

          console.log('   API 响应状态:', response.status);

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
          console.log('   API 响应数据:', data);
          
          // ⚠️ 后端返回扁平结构: { valid, user_id, email, name, avatar_url }
          // 需要转换为 User 对象格式
          if (data.valid && data.user_id) {
            const validatedUser: User = {
              id: String(data.user_id),
              email: data.email,
              name: data.name,
              avatar_url: data.avatar_url,
              oauth_provider: currentUser?.oauth_provider || 'google', // 保留原有 provider
              oauth_id: currentUser?.oauth_id || '', // 保留原有 oauth_id
              created_at: currentUser?.created_at || new Date().toISOString(),
              updated_at: currentUser?.updated_at || new Date().toISOString(),
            };
            
            set({ 
              user: validatedUser,
              isAuthenticated: true 
            });
            console.log('✅ Token 有效，用户已认证:', validatedUser.email);
          } else {
            console.log('⚠️ Token 无效，清除认证状态');
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
      storage: createJSONStorage(() => createTauriStorage()),
      partialize: (state) => ({ 
        user: state.user,
        token: state.token,
        tokenExpiresAt: state.tokenExpiresAt,
        isAuthenticated: state.isAuthenticated 
      }),
      // 监听数据水合完成事件
      onRehydrateStorage: () => {
        console.log('🔄 开始从 Tauri Store 加载认证数据...');
        
        return (state, error) => {
          if (error) {
            console.error('❌ 从 Tauri Store 加载数据失败:', error);
          } else {
            console.log('✅ 认证数据加载完成:', {
              hasUser: !!state?.user,
              hasToken: !!state?.token,
              email: state?.user?.email
            });
          }
        };
      },
    }
  )
);

// 开发环境下暴露到 window 对象以便调试
if (typeof window !== 'undefined') {
  (window as any).authStore = useAuthStore;
  console.log('🔧 authStore 已暴露到 window.authStore,可以使用 window.authStore.getState() 调试');
}
