import { create } from 'zustand';
import { TaggedFile } from '../types/file-types';

// PinnedFile 类型来自 API 响应
interface PinnedFile {
  id: number;
  file_path: string;
  file_name: string;
  pinned_at: string;
  metadata: Record<string, any>;
}

interface FileListState {
  files: TaggedFile[];
  pinnedFiles: Set<number>;
  isLoading: boolean;
  error: string | null;
  
  // Actions
  setFiles: (files: TaggedFile[]) => void;
  addPinnedFile: (fileId: number) => void;
  removePinnedFile: (fileId: number) => void;
  togglePinnedFile: (fileId: number) => void;
  clearAllPinnedFiles: () => void;
  setPinnedFilesByPath: (filePaths: string[]) => void;
  rebuildFromPinnedFiles: (pinnedFiles: PinnedFile[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  getFilteredFiles: () => TaggedFile[];
}

export const useFileListStore = create<FileListState>((set, get) => ({
  files: [],
  pinnedFiles: new Set(),
  isLoading: false,
  error: null,

  setFiles: (files: TaggedFile[]) => set((state) => {
    // 合并新文件和已固定的文件
    const pinnedFiles = state.files.filter(file => 
      state.pinnedFiles.has(file.id) && file.pinned
    );
    
    // 标记新文件中的固定状态
    const updatedFiles = files.map(file => ({
      ...file,
      pinned: state.pinnedFiles.has(file.id)
    }));
    
    // 合并并去重（优先保留最新的文件信息）
    const fileMap = new Map<number, TaggedFile>();
    [...pinnedFiles, ...updatedFiles].forEach(file => {
      fileMap.set(file.id, file);
    });
    
    return {
      files: Array.from(fileMap.values()),
      error: null
    };
  }),

  addPinnedFile: (fileId: number) => set((state) => ({
    pinnedFiles: new Set([...state.pinnedFiles, fileId]),
    files: state.files.map(file => 
      file.id === fileId ? { ...file, pinned: true } : file
    )
  })),

  removePinnedFile: (fileId: number) => set((state) => {
    const newPinnedFiles = new Set(state.pinnedFiles);
    newPinnedFiles.delete(fileId);
    
    return {
      pinnedFiles: newPinnedFiles,
      files: state.files.map(file => 
        file.id === fileId ? { ...file, pinned: false } : file
      )
    };
  }),

  togglePinnedFile: (fileId: number) => {
    const { pinnedFiles } = get();
    if (pinnedFiles.has(fileId)) {
      get().removePinnedFile(fileId);
    } else {
      get().addPinnedFile(fileId);
    }
  },

  clearAllPinnedFiles: () => set((state) => ({
    pinnedFiles: new Set(),
    files: state.files.map(file => ({ ...file, pinned: false }))
  })),

  setPinnedFilesByPath: (filePaths: string[]) => set((state) => {
    const pinnedFileIds = new Set<number>();
    const updatedFiles = state.files.map(file => {
      const isPinned = filePaths.includes(file.path);
      if (isPinned) {
        pinnedFileIds.add(file.id);
      }
      return { ...file, pinned: isPinned };
    });

    return {
      pinnedFiles: pinnedFileIds,
      files: updatedFiles
    };
  }),

  rebuildFromPinnedFiles: (pinnedFiles: PinnedFile[]) => set(() => {
    const pinnedFileIds = new Set<number>();
    
    // 将 PinnedFile 转换为 TaggedFile 格式
    const taggedFiles: TaggedFile[] = pinnedFiles.map((pf, index) => {
      const fileExtension = pf.file_path.split('.').pop() || '';
      // 使用文件路径的哈希作为唯一ID，或者使用索引
      const fileId = Math.abs(pf.file_path.split('').reduce((a, b) => {
        a = ((a << 5) - a) + b.charCodeAt(0);
        return a & a;
      }, 0)) || (1000000 + index); // 确保ID不为0
      
      const taggedFile: TaggedFile = {
        id: fileId,
        path: pf.file_path,
        file_name: pf.file_name,
        extension: fileExtension,
        tags: [],
        pinned: true
      };
      
      pinnedFileIds.add(fileId);
      return taggedFile;
    });

    return {
      files: taggedFiles,
      pinnedFiles: pinnedFileIds,
      error: null
    };
  }),

  setLoading: (loading: boolean) => set({ isLoading: loading }),
  
  setError: (error: string | null) => set({ error }),

  getFilteredFiles: () => {
    const { files } = get();
    return files.sort((a, b) => {
      // 固定的文件排在前面
      if (a.pinned && !b.pinned) return -1;
      if (!a.pinned && b.pinned) return 1;
      return a.file_name.localeCompare(b.file_name);
    });
  }
}));
