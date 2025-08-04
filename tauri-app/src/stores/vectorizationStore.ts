import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type VectorizationStatus = 'queued' | 'processing' | 'completed' | 'failed'

export interface VectorizationState {
  status: VectorizationStatus
  progress: number // 0-100
  taskId?: string
  stage?: string // parsing, chunking, vectorizing
  message?: string
  error?: {
    message: string
    helpLink?: string
    errorCode?: string
    canRetry: boolean
  }
  createdAt: number // 排队时间
  lastUpdated: number
  parentChunksCount?: number
  childChunksCount?: number
}

interface VectorizationStore {
  // 状态数据：文件路径 -> 向量化状态
  vectorizations: Record<string, VectorizationState>
  
  // Actions
  setVectorizationState: (filePath: string, state: Partial<VectorizationState>) => void
  updateProgress: (filePath: string, progress: number, stage?: string, message?: string) => void
  setStatus: (filePath: string, status: VectorizationStatus, error?: VectorizationState['error']) => void
  setCompleted: (filePath: string, parentChunksCount?: number, childChunksCount?: number) => void
  setFailed: (filePath: string, error: VectorizationState['error']) => void
  removeVectorization: (filePath: string) => void
  clearAll: () => void
  
  // Getters
  getVectorizationState: (filePath: string) => VectorizationState | undefined
  isProcessing: (filePath: string) => boolean
  isCompleted: (filePath: string) => boolean
  isFailed: (filePath: string) => boolean
  getProcessingFiles: () => string[]
  getQueuedFiles: () => string[]
}

export const useVectorizationStore = create<VectorizationStore>()(
  persist(
    (set, get) => ({
      vectorizations: {},
      
      setVectorizationState: (filePath, state) =>
        set((store) => ({
          vectorizations: {
            ...store.vectorizations,
            [filePath]: {
              ...store.vectorizations[filePath],
              ...state,
              lastUpdated: Date.now(),
            },
          },
        })),
      
      updateProgress: (filePath, progress, stage, message) =>
        set((store) => {
          const current = store.vectorizations[filePath]
          return {
            vectorizations: {
              ...store.vectorizations,
              [filePath]: {
                ...current,
                progress: Math.max(0, Math.min(100, progress)),
                stage,
                message,
                lastUpdated: Date.now(),
                status: progress >= 100 ? 'completed' : 'processing' as VectorizationStatus,
              },
            },
          }
        }),
      
      setStatus: (filePath, status, error) =>
        set((store) => ({
          vectorizations: {
            ...store.vectorizations,
            [filePath]: {
              ...store.vectorizations[filePath],
              status,
              error,
              lastUpdated: Date.now(),
            },
          },
        })),
      
      setCompleted: (filePath, parentChunksCount, childChunksCount) =>
        set((store) => ({
          vectorizations: {
            ...store.vectorizations,
            [filePath]: {
              ...store.vectorizations[filePath],
              status: 'completed',
              progress: 100,
              parentChunksCount,
              childChunksCount,
              stage: 'completed',
              message: '向量化完成',
              error: undefined,
              lastUpdated: Date.now(),
            },
          },
        })),
      
      setFailed: (filePath, error) =>
        set((store) => ({
          vectorizations: {
            ...store.vectorizations,
            [filePath]: {
              ...store.vectorizations[filePath],
              status: 'failed',
              error,
              lastUpdated: Date.now(),
            },
          },
        })),
      
      removeVectorization: (filePath) =>
        set((store) => {
          const { [filePath]: removed, ...rest } = store.vectorizations
          return { vectorizations: rest }
        }),
      
      clearAll: () => set({ vectorizations: {} }),
      
      // Getters
      getVectorizationState: (filePath) => get().vectorizations[filePath],
      
      isProcessing: (filePath) => {
        const state = get().vectorizations[filePath]
        return state?.status === 'processing'
      },
      
      isCompleted: (filePath) => {
        const state = get().vectorizations[filePath]
        return state?.status === 'completed'
      },
      
      isFailed: (filePath) => {
        const state = get().vectorizations[filePath]
        return state?.status === 'failed'
      },
      
      getProcessingFiles: () => {
        const { vectorizations } = get()
        return Object.keys(vectorizations).filter(
          (filePath) => vectorizations[filePath].status === 'processing'
        )
      },
      
      getQueuedFiles: () => {
        const { vectorizations } = get()
        return Object.keys(vectorizations)
          .filter((filePath) => vectorizations[filePath].status === 'queued')
          .sort((a, b) => vectorizations[a].createdAt - vectorizations[b].createdAt)
      },
    }),
    {
      name: 'vectorization-store',
      // 只持久化状态数据，不持久化progress（会通过事件更新）
      partialize: (state) => ({
        vectorizations: Object.fromEntries(
          Object.entries(state.vectorizations).map(([filePath, vectorization]) => [
            filePath,
            {
              ...vectorization,
              progress: vectorization.status === 'completed' ? 100 : 0,
            },
          ])
        ),
      }),
    }
  )
)

// 便捷hooks
export const useFileVectorization = (filePath: string) => {
  const store = useVectorizationStore()
  return {
    state: store.getVectorizationState(filePath),
    isProcessing: store.isProcessing(filePath),
    isCompleted: store.isCompleted(filePath),
    isFailed: store.isFailed(filePath),
    updateProgress: (progress: number, stage?: string, message?: string) => 
      store.updateProgress(filePath, progress, stage, message),
    setCompleted: (parentChunksCount?: number, childChunksCount?: number) => 
      store.setCompleted(filePath, parentChunksCount, childChunksCount),
    setFailed: (error: VectorizationState['error']) => 
      store.setFailed(filePath, error),
    remove: () => store.removeVectorization(filePath),
  }
}
