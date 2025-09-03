import { create } from 'zustand';
import { invoke } from "@tauri-apps/api/core";

// 标签数据类型
interface TagItem {
  id: number;
  name: string;
  weight: number;
  type: string;
}

// API返回的标签云数据格式
interface TagCloudResponse {
  success: boolean;
  data: TagItem[];
  error_type: string | null;
  message: string | null;
}

interface TagCloudState {
  tags: TagItem[];
  loading: boolean;
  error: string | null;
  errorType: string | null; // 新增：错误类型
  lastFetchTime: number;
  isRequesting: boolean;
  
  // 方法
  fetchTagCloud: (force?: boolean) => Promise<void>;
  clearCache: () => void;
  setError: (error: string | null, errorType?: string | null) => void;
}

const CACHE_DURATION = 30000; // 30秒缓存时间

export const useTagCloudStore = create<TagCloudState>((set, get) => ({
  tags: [],
  loading: false,
  error: null,
  errorType: null,
  lastFetchTime: 0,
  isRequesting: false,

  fetchTagCloud: async (force = false) => {
    const state = get();
    const now = Date.now();
    
    // 检查缓存（除非强制刷新）
    if (!force && (now - state.lastFetchTime < CACHE_DURATION)) {
      console.log('📋 使用缓存的标签云数据，剩余缓存时间:', Math.ceil((CACHE_DURATION - (now - state.lastFetchTime)) / 1000), '秒');
      return;
    }
    
    // 检查是否正在请求中
    if (state.isRequesting) {
      console.log('⏳ 标签云数据正在请求中，跳过重复请求');
      return;
    }
    
    try {
      set({ isRequesting: true, loading: true, error: null, errorType: null });
      
      console.log('📡 开始获取标签云数据 (全局存储)');
      const response = await invoke<TagCloudResponse>('get_tag_cloud_data', { limit: 100 });
      console.log('✅ 接收到标签云响应 (全局存储):', response);
      
      if (response.success) {
        set({ 
          tags: response.data, 
          lastFetchTime: now,
          loading: false,
          isRequesting: false,
          error: null,
          errorType: null
        });
        console.log('✅ 成功设置标签云数据:', response.data.length, '个标签');
      } else {
        // 处理不同类型的错误
        let errorMessage = response.message || '获取标签云数据失败';
        
        if (response.error_type === 'model_not_configured') {
          errorMessage = '未配置文件标签生成模型';
        }
        
        set({ 
          error: errorMessage,
          errorType: response.error_type,
          tags: [],
          loading: false, 
          isRequesting: false 
        });
        console.log('❌ 标签云数据获取失败:', errorMessage, '错误类型:', response.error_type);
      }
    } catch (error) {
      console.error('❌ Error fetching tag cloud data (全局存储):', error);
      set({ 
        error: '网络请求失败',
        errorType: 'network_error',
        tags: [],
        loading: false, 
        isRequesting: false 
      });
    }
  },

  clearCache: () => {
    set({ lastFetchTime: 0 });
  },

  setError: (error: string | null, errorType: string | null = null) => {
    set({ error, errorType });
  }
}));
