import { invoke } from '@tauri-apps/api/core';

// 文件信息类型
export interface FileInfo {
  file_path: string;
  file_name: string;
  file_size: number;
  extension?: string;
  created_time?: string;
  modified_time: string;
  category_id?: number;
}

// 时间范围枚举
export enum TimeRange {
  Today = 'today',
  Last7Days = 'last7days',
  Last30Days = 'last30days',
}

// 文件类型枚举
export enum FileType {
  Image = 'image',
  AudioVideo = 'audio-video',
  Archive = 'archive',
  Document = 'document',
  All = 'all',
}

/**
 * 文件扫描服务 - 使用Rust直接扫描文件系统
 */
export const FileScannerService = {
  /**
   * 按时间范围扫描文件
   * @param timeRange 时间范围
   * @returns 文件信息列表
   */
  async scanFilesByTimeRange(timeRange: TimeRange): Promise<FileInfo[]> {
    try {
      return await invoke<FileInfo[]>('scan_files_by_time_range', { timeRange });
    } catch (error) {
      console.error('按时间范围扫描文件失败:', error);
      throw error;
    }
  },

  /**
   * 按文件类型扫描文件
   * @param fileType 文件类型
   * @returns 文件信息列表
   */
  async scanFilesByType(fileType: FileType): Promise<FileInfo[]> {
    try {
      return await invoke<FileInfo[]>('scan_files_by_type', { fileType });
    } catch (error) {
      console.error('按文件类型扫描文件失败:', error);
      throw error;
    }
  },

  /**
   * 格式化文件大小
   * @param bytes 字节数
   * @returns 格式化后的文件大小字符串
   */
  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
  }
};
