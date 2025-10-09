import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface VectorizationState {
  [filePath: string]: {
    status: 'queued' | 'processing' | 'completed' | 'failed'
    progress: number // 0-100
    taskId?: string
    stage?: string // queued, parsing, chunking, vectorizing, completed, failed
    message?: string
    error?: {
      message: string
      helpLink?: string
      errorCode?: string
    }
    createdAt: number // 用于排队顺序
    lastUpdated: number
    parentChunksCount?: number
    childChunksCount?: number
  }
}

interface VectorizationStore {
  files: VectorizationState
  
  // 操作方法
  setFileStatus: (filePath: string, status: VectorizationState[string]['status']) => void
  setFileProgress: (filePath: string, progress: number, stage?: string, message?: string, taskId?: string) => void
  setFileStarted: (filePath: string, taskId: string) => void
  setFileCompleted: (filePath: string, taskId: string, parentCount?: number, childCount?: number) => void
  setFileFailed: (filePath: string, taskId: string, error: VectorizationState[string]['error']) => void
  removeFile: (filePath: string) => void
  clearAll: () => void
  
  // 查询方法
  getFileStatus: (filePath: string) => VectorizationState[string] | undefined
  getProcessingFiles: () => string[]
  getQueuedFiles: () => string[]
  getCompletedFiles: () => string[]
  getFailedFiles: () => string[]
}

export const useVectorizationStore = create<VectorizationStore>()(
  persist(
    (set, get) => ({
      files: {},
      
      setFileStatus: (filePath, status) =>
        set((state) => ({
          files: {
            ...state.files,
            [filePath]: {
              ...state.files[filePath],
              status,
              lastUpdated: Date.now(),
            },
          },
        })),
      
      setFileProgress: (filePath, progress, stage, message, taskId) =>
        set((state) => ({
          files: {
            ...state.files,
            [filePath]: {
              ...state.files[filePath],
              status: state.files[filePath]?.status === 'queued' ? 'processing' as const : state.files[filePath]?.status || 'processing' as const,
              progress,
              stage,
              message,
              taskId: taskId || state.files[filePath]?.taskId, // 更新taskId或保持原值
              lastUpdated: Date.now(),
            },
          },
        })),
      
      setFileStarted: (filePath, taskId) =>
        set((state) => ({
          files: {
            ...state.files,
            [filePath]: {
              status: 'queued' as const,
              progress: 0,
              taskId,
              stage: 'queued',
              message: 'waiting for processing',
              createdAt: state.files[filePath]?.createdAt || Date.now(),
              lastUpdated: Date.now(),
            },
          },
        })),
      
      setFileCompleted: (filePath, taskId, parentCount, childCount) =>
        set((state) => ({
          files: {
            ...state.files,
            [filePath]: {
              ...state.files[filePath],
              status: 'completed' as const,
              progress: 100,
              taskId,
              stage: 'completed',
              message: 'completed',
              parentChunksCount: parentCount,
              childChunksCount: childCount,
              lastUpdated: Date.now(),
            },
          },
        })),
      
      setFileFailed: (filePath, taskId, error) =>
        set((state) => ({
          files: {
            ...state.files,
            [filePath]: {
              ...state.files[filePath],
              status: 'failed' as const,
              taskId,
              stage: 'failed',
              message: error?.message || 'failed',
              error,
              lastUpdated: Date.now(),
            },
          },
        })),
      
      removeFile: (filePath) =>
        set((state) => {
          const newFiles = { ...state.files }
          delete newFiles[filePath]
          return { files: newFiles }
        }),
      
      clearAll: () => set({ files: {} }),
      
      // 查询方法
      getFileStatus: (filePath) => get().files[filePath],
      
      getProcessingFiles: () =>
        Object.keys(get().files).filter(
          (filePath) => get().files[filePath].status === 'processing'
        ),
      
      getQueuedFiles: () =>
        Object.keys(get().files).filter(
          (filePath) => get().files[filePath].status === 'queued'
        ),
      
      getCompletedFiles: () =>
        Object.keys(get().files).filter(
          (filePath) => get().files[filePath].status === 'completed'
        ),
      
      getFailedFiles: () =>
        Object.keys(get().files).filter(
          (filePath) => get().files[filePath].status === 'failed'
        ),
    }),
    {
      name: 'vectorization-store',
      // 只持久化文件状态，不持久化progress（会通过事件实时更新）
      partialize: (state) => ({
        files: Object.fromEntries(
          Object.entries(state.files).map(([key, value]) => [
            key,
            {
              ...value,
              progress: value.status === 'completed' ? 100 : 0, // 重置progress
              stage: value.status === 'completed' ? 'completed' : undefined,
              message: undefined, // 重置message
            },
          ])
        ),
      }),
    }
  )
)
