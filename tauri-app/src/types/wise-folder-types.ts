/**
 * 智慧文件夹分类
 */
export interface WiseFolderCategory {
  type: string;
  name: string;
  icon: string;
  description: string;
  folder_count: number;
}

/**
 * 智慧文件夹类型
 */
export interface WiseFolder {
  id: string;
  name: string;
  type: string;
  icon?: string;
  description?: string;
  count: number;
  file_count?: number;
  criteria: Record<string, any>;
}

/**
 * 智慧文件夹中的文件
 */
export interface WiseFolderFile {
  id: number;
  screening_id: number;
  file_path: string;
  file_name: string;
  extension?: string;
  file_size: number;
  created_time?: string;
  modified_time: string;
  category_id?: number;
  category_name?: string;
  project_id?: number;
  project_name?: string;
  labels?: string[];
  extra_metadata?: Record<string, any>;
  features?: Record<string, any>;
}

/**
 * 关联文件信息
 */
export interface RelatedFile {
  refine_id: number;
  file_path: string;
  relation_type?: string; // 可选的关系类型描述
}

/**
 * 相似文件信息
 */
export interface SimilarFile {
  refine_id: number;
  file_path: string;
  similarity: number;
  reason: string;
}
