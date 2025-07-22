import { create } from 'zustand';
import { invoke } from "@tauri-apps/api/core";

// 标签数据类型
interface TagItem {
  id: number;
  name: string;
  weight: number;
  type: string;
}

interface TagCloudState {
  tags: TagItem[];
  loading: boolean;
  error: string | null;
  lastFetchTime: number;
  isRequesting: boolean;
  
  // 方法
  fetchTagCloud: (force?: boolean) => Promise<void>;
  clearCache: () => void;
  setError: (error: string | null) => void;
}

const CACHE_DURATION = 30000; // 30秒缓存时间

export const useTagCloudStore = create<TagCloudState>((set, get) => ({
  tags: [],
  loading: false,
  error: null,
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
      set({ isRequesting: true, loading: true, error: null });
      
      console.log('📡 开始获取标签云数据 (全局存储)');
      const tagData = await invoke<TagItem[]>('get_tag_cloud_data', { limit: 100 });
      console.log('✅ 成功获取标签云数据 (全局存储):', tagData.length);
      
      set({ 
        tags: tagData, 
        lastFetchTime: now,
        loading: false,
        isRequesting: false 
      });
    } catch (error) {
      console.error('❌ Error fetching tag cloud data (全局存储):', error);
      set({ 
        error: '获取标签数据失败', 
        loading: false, 
        isRequesting: false 
      });
    }
  },

  clearCache: () => {
    set({ lastFetchTime: 0 });
  },

  setError: (error: string | null) => {
    set({ error });
  }
}));
