import { FileScreeningResult, TaggedFile } from "../types/file-types";
import { invoke } from "@tauri-apps/api/core";

const API_BASE_URL = 'http://127.0.0.1:60315';

/**
 * 文件服务API接口
 */
export const FileService = {
  /**
   * 获取文件筛选结果
   * @param limit 最大返回结果数量
   * @param categoryId 可选的分类ID筛选
   * @param timeRange 可选的时间范围筛选
   * @returns 文件筛选结果
   */
  async getFileScreeningResults(
    limit: number = 1000, 
    categoryId?: number, 
    timeRange?: string
  ): Promise<FileScreeningResult[]> {
    // 构建查询参数
    const queryParams = new URLSearchParams();
    queryParams.append('limit', limit.toString());
    
    if (categoryId) {
      queryParams.append('category_id', categoryId.toString());
    }
    
    if (timeRange) {
      queryParams.append('time_range', timeRange);
    }
    
    try {
      const response = await fetch(`${API_BASE_URL}/file-screening/results?${queryParams.toString()}`);
      
      if (!response.ok) {
        throw new Error(`API返回错误: ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      
      if (!data.success) {
        throw new Error(`API返回错误: ${data.message}`);
      }
      
      return data.data;
    } catch (error) {
      console.error('获取文件筛选结果失败:', error);
      throw error;
    }
  },
  
  /**
   * 获取文件分类列表
   */
  async getFileCategories() {
    try {
      const response = await fetch(`${API_BASE_URL}/file-categories`);
      
      if (!response.ok) {
        throw new Error(`API返回错误: ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      
      if (!data.success) {
        throw new Error(`API返回错误: ${data.message}`);
      }
      
      return data.data;
    } catch (error) {
      console.error('获取文件分类失败:', error);
      throw error;
    }
  },

  /**
   * 按标签搜索文件
   * @param tagNames 标签名称列表
   * @param operator 操作符: AND或OR
   * @returns 匹配的文件列表
   */
  async searchFilesByTags(
    tagNames: string[], 
    operator: string = 'AND'
  ): Promise<TaggedFile[]> {
    try {
      const files = await invoke<TaggedFile[]>('search_files_by_tags', {
        tag_names: tagNames,
        operator
      });
      return files;
    } catch (error) {
      console.error('按标签搜索文件失败:', error);
      throw error;
    }
  }
};
