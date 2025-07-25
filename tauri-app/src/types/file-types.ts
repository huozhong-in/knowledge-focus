export interface FileScreeningResult {
  id: number;
  file_path: string;
  file_name: string;
  file_size: number;
  extension?: string;
  file_hash?: string;
  created_time?: string;
  modified_time: string;
  accessed_time?: string;
  category_id?: number;
  matched_rules?: number[];
  extra_metadata?: Record<string, any>;
  labels?: string[];
  status: string;
  error_message?: string;
  task_id?: number;
  created_at: string;
  updated_at: string;
}

export interface FileCategory {
  id: number;
  name: string;
  description?: string;
  icon?: string;
  created_at: string;
  updated_at: string;
}

export interface WiseFolderFile {
  id: number;
  file_path: string;
  file_name: string;
  extension?: string;
  modified_time: string;
  category_id?: number;
  file_size: number;
}

export interface TaggedFile {
  id: number;
  path: string;
  file_name: string;
  extension?: string;
  tags?: string[];
  pinned?: boolean;
}
