import { create } from 'zustand';
import { TaggedFile } from '../types/file-types';

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
