import { WiseFolder, WiseFolderFile, WiseFolderCategory } from "../types/wise-folder-types";

const API_BASE_URL = 'http://127.0.0.1:60315';

/**
 * 智慧文件夹服务API接口
 */
export const WiseFoldersService = {
  /**
   * 获取所有智慧文件夹分类
   * @returns 分类列表
   */
  async getCategories(): Promise<WiseFolderCategory[]> {
    try {
      const response = await fetch(`${API_BASE_URL}/wise-folders/categories`);
      
      if (!response.ok) {
        throw new Error(`API返回错误: ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      
      if (!data.success) {
        throw new Error(`API返回错误: ${data.message}`);
      }
      
      return data.categories || [];
    } catch (error) {
      console.error('获取智慧文件夹分类失败:', error);
      throw error;
    }
  },
  
  /**
   * 获取指定分类下的智慧文件夹列表
   * @param categoryType 分类类型
   * @returns 智慧文件夹列表
   */
  async getFoldersByCategory(categoryType: string): Promise<WiseFolder[]> {
    try {
      const response = await fetch(`${API_BASE_URL}/wise-folders/folders/${categoryType}`);
      
      if (!response.ok) {
        throw new Error(`API返回错误: ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      
      if (!data.success) {
        throw new Error(`API返回错误: ${data.message}`);
      }
      
      const folders = data.folders || [];
      return folders.map((folder: any) => ({
        ...folder,
        count: folder.file_count || 0
      }));
    } catch (error) {
      console.error(`获取分类 ${categoryType} 下的智慧文件夹失败:`, error);
      throw error;
    }
  },
  
  /**
   * 获取智慧文件夹中的文件
   * @param folderType 文件夹类型
   * @param criteria 文件夹条件
   * @returns 文件列表
   */
  async getFilesInFolder(folderType: string, criteria: Record<string, any>): Promise<WiseFolderFile[]> {
    try {
      const queryParams = new URLSearchParams();
      queryParams.append('folder_type', folderType);
      queryParams.append('criteria', JSON.stringify(criteria));
      
      const response = await fetch(`${API_BASE_URL}/wise-folders/files?${queryParams.toString()}`);
      
      if (!response.ok) {
        throw new Error(`API返回错误: ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      
      if (!data.success) {
        throw new Error(`API返回错误: ${data.message}`);
      }
      
      return data.files || [];
    } catch (error) {
      console.error('获取智慧文件夹中的文件失败:', error);
      throw error;
    }
  },
  
  /**
   * 获取所有智慧文件夹（旧API，保留向后兼容）
   * @deprecated 使用新的getCategories和getFoldersByCategory方法替代
   * @returns 智慧文件夹列表
   */
  async getWiseFolders(taskId: string = 'all'): Promise<WiseFolder[]> {
    try {
      const response = await fetch(`${API_BASE_URL}/wise-folders/${taskId}`);
      
      if (!response.ok) {
        throw new Error(`API返回错误: ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      
      if (!data.success) {
        throw new Error(`API返回错误: ${data.message}`);
      }
      
      const folders = data.folders || [];
      return folders.map((folder: any) => ({
        ...folder,
        count: folder.file_count || 0
      }));
    } catch (error) {
      console.error('获取智慧文件夹失败:', error);
      throw error;
    }
  },
  
  /**
   * 获取最近的精炼任务ID（旧API，保留向后兼容）
   * @deprecated 新的API不再需要task_id
   * @returns 最近的任务ID，如果获取失败则返回"all"
   */
  async getLatestRefinementTask(): Promise<string> {
    return "all";
  },

  /**
   * 更新缺失的task_id
   * @returns 更新结果
   */
  async updateMissingTaskIds(): Promise<any> {
    try {
      const response = await fetch(`${API_BASE_URL}/wise-folders/update-missing-task-ids`, {
        method: 'POST'
      });
      
      if (!response.ok) {
        throw new Error(`API返回错误: ${response.status} ${response.statusText}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('更新缺失的task_id失败:', error);
      throw error;
    }
  }
};
