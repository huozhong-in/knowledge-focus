import { FileInfo } from './file-scanner-service';

const API_BASE_URL = 'http://127.0.0.1:60315';

// 缓存配置
interface CacheEntry<T> {
  data: T;
  timestamp: number;
  queryTimeMs?: number; // API查询耗时（毫秒）
}

// 缓存有效期（毫秒）
const CACHE_TTL = 60 * 1000; // 1分钟缓存
const cacheStore: {
  [key: string]: CacheEntry<any>;
} = {};

/**
 * PinnedFolders服务 - 使用Python API获取粗筛表的结果
 */
export const PinnedFoldersService = {
  /**
   * 按时间范围获取文件
   * @param timeRange 时间范围 ("today", "last7days", "last30days")
   * @param forceRefresh 是否强制刷新缓存
   * @returns 文件信息列表
   */
  async getFilesByTimeRange(timeRange: string, forceRefresh = false): Promise<FileInfo[]> {
    const cacheKey = `time-range-${timeRange}`;
    
    // 检查缓存
    if (!forceRefresh && cacheStore[cacheKey] && (Date.now() - cacheStore[cacheKey].timestamp < CACHE_TTL)) {
      console.log(`[缓存] 使用缓存的时间范围数据: ${timeRange}`);
      return cacheStore[cacheKey].data as FileInfo[];
    }
    
    try {
      const startTime = performance.now();
      const response = await fetch(`${API_BASE_URL}/file-screening/by-time-range/${timeRange}`);
      
      if (!response.ok) {
        throw new Error(`API返回错误: ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      const endTime = performance.now();
      const fetchTimeMs = Math.round(endTime - startTime);
      
      if (!data.success) {
        throw new Error(`API返回错误: ${data.message}`);
      }
      
      // 更新缓存
      cacheStore[cacheKey] = {
        data: data.data,
        timestamp: Date.now(),
        queryTimeMs: data.query_time_ms || fetchTimeMs
      };
      
      const apiTimeMs = data.query_time_ms || '未知';
      console.log(`[API] 获取时间范围数据: ${timeRange}, API耗时: ${apiTimeMs}ms, 总获取耗时: ${fetchTimeMs}ms`);
      
      return data.data as FileInfo[];
    } catch (error) {
      console.error(`按时间范围获取文件失败 (${timeRange}):`, error);
      throw error;
    }
  },

  /**
   * 按分类类型获取文件
   * @param categoryType 分类类型 ("image", "audio-video", "archive", 等)
   * @param forceRefresh 是否强制刷新缓存
   * @returns 文件信息列表
   */
  async getFilesByCategory(categoryType: string, forceRefresh = false): Promise<FileInfo[]> {
    const cacheKey = `category-${categoryType}`;
    
    // 检查缓存
    if (!forceRefresh && cacheStore[cacheKey] && (Date.now() - cacheStore[cacheKey].timestamp < CACHE_TTL)) {
      console.log(`[缓存] 使用缓存的分类数据: ${categoryType}`);
      return cacheStore[cacheKey].data as FileInfo[];
    }
    
    try {
      const startTime = performance.now();
      const response = await fetch(`${API_BASE_URL}/file-screening/by-category/${categoryType}`);
      
      if (!response.ok) {
        throw new Error(`API返回错误: ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      const endTime = performance.now();
      const fetchTimeMs = Math.round(endTime - startTime);
      
      if (!data.success) {
        throw new Error(`API返回错误: ${data.message}`);
      }
      
      // 更新缓存
      cacheStore[cacheKey] = {
        data: data.data,
        timestamp: Date.now(),
        queryTimeMs: data.query_time_ms || fetchTimeMs
      };
      
      const apiTimeMs = data.query_time_ms || '未知';
      console.log(`[API] 获取分类数据: ${categoryType}, API耗时: ${apiTimeMs}ms, 总获取耗时: ${fetchTimeMs}ms`);
      
      return data.data as FileInfo[];
    } catch (error) {
      console.error(`按分类获取文件失败 (${categoryType}):`, error);
      throw error;
    }
  },
  
  /**
   * 清除特定键的缓存
   * @param key 缓存键名或模式
   */
  clearCache(key?: string): void {
    if (key) {
      // 如果提供了键名，尝试精确匹配或模式匹配
      const exactMatch = cacheStore[key];
      if (exactMatch) {
        delete cacheStore[key];
        console.log(`[缓存] 已清除缓存: ${key}`);
        return;
      }
      
      // 模式匹配 - 例如 'time-range-*' 或 'category-*'
      if (key.endsWith('*')) {
        const prefix = key.slice(0, -1);
        let count = 0;
        Object.keys(cacheStore).forEach(k => {
          if (k.startsWith(prefix)) {
            delete cacheStore[k];
            count++;
          }
        });
        console.log(`[缓存] 已清除${count}个匹配 "${prefix}" 的缓存项`);
      }
    } else {
      // 清除所有缓存
      Object.keys(cacheStore).forEach(k => {
        delete cacheStore[k];
      });
      console.log('[缓存] 已清除所有缓存');
    }
  }
};
