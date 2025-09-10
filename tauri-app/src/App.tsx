import "./index.css"
import "./tweakcn/app/globals.css"
import { useEffect, useState } from "react"
import { create } from "zustand"
import { load } from '@tauri-apps/plugin-store'
import { appDataDir, join } from '@tauri-apps/api/path'
import { listen } from '@tauri-apps/api/event'
import { useAppStore } from "./main"
import { Toaster } from "@/components/ui/sonner"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { SidebarProvider } from "@/components/ui/sidebar"
import { AppSidebar } from "./app-sidebar"
import { AppWorkspace } from "./app-workspace"
import IntroDialog from "./intro-dialog"
import { useBridgeEvents } from "@/hooks/useBridgeEvents"
import { useVectorizationStore } from "@/stores/useVectorizationStore"
import { ChatSession, createSmartSession, pinFile, updateSession, deleteSession, getPinnedFiles } from "./lib/chat-session-api"

// 设置页面名称枚举常量
export const SETTINGS_PAGES = {
  GENERAL: "general",
  AUTHORIZATION: "authorization", 
  FILE_RECOGNITION: "file_recognition",
  AI_MODELS: "aimodels",
  THEME: "theme",
  ABOUT: "about"
} as const

export type SettingsPageId = typeof SETTINGS_PAGES[keyof typeof SETTINGS_PAGES]

// 创建一个store来管理设置对话框状态
interface SettingsState {
  isSettingsOpen: boolean
  initialPage: SettingsPageId
  setSettingsOpen: (open: boolean) => void
  setInitialPage: (page: SettingsPageId) => void
  openSettingsPage: (page: SettingsPageId) => void
}

export const useSettingsStore = create<SettingsState>((set) => ({
  isSettingsOpen: false,
  initialPage: SETTINGS_PAGES.GENERAL,
  setSettingsOpen: (open) => set({ isSettingsOpen: open }),
  setInitialPage: (page) => set({ initialPage: page }),
  openSettingsPage: (page) => set({ isSettingsOpen: true, initialPage: page }),
}))

// ==================== 工具函数 ====================

// 保存最近使用的会话ID到Tauri Store
async function saveLastUsedSession(sessionId: number): Promise<void> {
  try {
    const appDataPath = await appDataDir()
    const storePath = await join(appDataPath, 'settings.json')
    const store = await load(storePath, { autoSave: false })
    
    await store.set('lastUsedSessionId', sessionId)
    await store.save()
    console.log('Last used session saved to settings.json:', sessionId)
  } catch (error) {
    console.error('Failed to save last used session:', error)
  }
}

// 从Tauri Store读取最近使用的会话ID
async function getLastUsedSession(): Promise<number | null> {
  try {
    const appDataPath = await appDataDir()
    const storePath = await join(appDataPath, 'settings.json')
    const store = await load(storePath, { autoSave: false })
    
    const sessionId = await store.get('lastUsedSessionId') as number | null
    console.log('Last used session loaded from settings.json:', sessionId)
    return sessionId
  } catch (error) {
    console.error('Failed to load last used session:', error)
    return null
  }
}

export default function Page() {
  const {
    isFirstLaunch,
    // isInitializing,
    initializationError,
    setIsInitializing,
    setInitializationError,
    isApiReady, // Get global API ready state
    setApiReady, // Get action to set API ready state
  } = useAppStore()

  const { openSettingsPage } = useSettingsStore()
  const [showIntroDialog, setShowIntroDialog] = useState(false)

  // 会话状态管理
  const [currentSession, setCurrentSession] = useState<ChatSession | null>(null)
  const [currentSessionId, setCurrentSessionId] = useState<number | null>(null)
  
  // 新生成会话状态（用于控制标题动画）
  const [newlyGeneratedSessionId, setNewlyGeneratedSessionId] = useState<number | null>(null)
  
  // 临时Pin文件状态（在会话创建前临时保存）
  const [tempPinnedFiles, setTempPinnedFiles] = useState<Array<{
    file_path: string
    file_name: string
    metadata?: Record<string, any>
  }>>([])
  
  // 聊天重置触发器
  const [chatResetTrigger, setChatResetTrigger] = useState(0)
  
  // Sidebar刷新触发器
  const [sidebarRefreshTrigger, setSidebarRefreshTrigger] = useState(0)
  
  // 搜索对话框状态
  const [searchOpen, setSearchOpen] = useState(false)

  // 获取向量化store的actions
  const vectorizationStore = useVectorizationStore()

  // 恢复最近使用的会话
  const restoreLastUsedSession = async () => {
    if (!isApiReady) return
    
    try {
      const lastSessionId = await getLastUsedSession()
      if (lastSessionId) {
        // 尝试从API获取会话信息
        const { getSessions } = await import('./lib/chat-session-api')
        const result = await getSessions(1, 50) // 获取会话列表
        const session = result.sessions.find(s => s.id === lastSessionId)
        
        if (session) {
          setCurrentSession(session)
          setCurrentSessionId(session.id)
          
          // 加载会话的Pin文件
          try {
            const pinnedFiles = await getPinnedFiles(session.id)
            
            // 重建文件列表，只显示Pin文件
            const { useFileListStore } = await import('./lib/fileListStore')
            useFileListStore.getState().rebuildFromPinnedFiles(pinnedFiles)
            
            console.log('Restored last used session:', session.name, session.id, `with ${pinnedFiles.length} pinned files`)
          } catch (error) {
            console.error('Failed to load pinned files for restored session:', error)
            // 如果加载失败，清空文件列表
            const { useFileListStore } = await import('./lib/fileListStore')
            useFileListStore.getState().rebuildFromPinnedFiles([])
            console.log('Restored last used session:', session.name, session.id)
          }
        } else {
          console.log('Last used session not found:', lastSessionId)
        }
      }
    } catch (error) {
      console.error('Failed to restore last used session:', error)
    }
  }

  // API就绪后恢复最近会话
  useEffect(() => {
    if (isApiReady) {
      restoreLastUsedSession()
    }
  }, [isApiReady])

  // 会话处理函数
  const handleSessionSwitch = async (session: ChatSession | null) => {
    try {
      if (!session) {
        // 如果session为null，清空当前会话
        setCurrentSession(null)
        setCurrentSessionId(null)
        
        // 清空文件列表（没有选择会话）
        const { useFileListStore } = await import('./lib/fileListStore')
        useFileListStore.getState().rebuildFromPinnedFiles([])
        return
      }
      
      setCurrentSession(session)
      setCurrentSessionId(session.id)
      
      // 清空临时Pin文件（切换到已存在的会话）
      setTempPinnedFiles([])
      
      // 加载会话的Pin文件并重建文件列表
      try {
        const pinnedFiles = await getPinnedFiles(session.id)
        
        // 重建文件列表，只显示Pin文件
        const { useFileListStore } = await import('./lib/fileListStore')
        useFileListStore.getState().rebuildFromPinnedFiles(pinnedFiles)
        
        console.log(`Loaded ${pinnedFiles.length} pinned files for session:`, session.name)
      } catch (error) {
        console.error('Failed to load pinned files for session:', error)
        // 如果加载Pin文件失败，清空文件列表
        const { useFileListStore } = await import('./lib/fileListStore')
        useFileListStore.getState().rebuildFromPinnedFiles([])
      }
      
      // 保存到Tauri Store
      await saveLastUsedSession(session.id)
      
      console.log('Switched to session:', session.name, session.id)
    } catch (error) {
      console.error('Failed to switch session:', error)
    }
  }

  // 创建新会话的处理（仅设置为准备状态，实际创建延迟到第一条消息）
  const handleCreateSession = async () => {
    try {
      // 清空当前会话状态，准备新会话
      setCurrentSession(null)
      setCurrentSessionId(null)
      
      // 清空文件列表（新会话没有Pin文件）
      const { useFileListStore } = await import('./lib/fileListStore')
      useFileListStore.getState().rebuildFromPinnedFiles([])
      
      // 触发聊天组件重置
      setChatResetTrigger(prev => prev + 1)
      
      // 保持临时Pin文件不变，它们将在第一条消息时绑定到新会话
      console.log('Prepared for new session creation (delayed until first message)')
    } catch (error) {
      console.error('Failed to prepare new session:', error)
    }
  }

  // 重命名会话处理函数
  const handleRenameSession = async (sessionId: number, newName: string): Promise<void> => {
    try {
      await updateSession(sessionId, newName)
      
      // 如果重命名的是当前会话，更新当前会话状态
      if (currentSession && currentSession.id === sessionId) {
        setCurrentSession({ ...currentSession, name: newName })
      }
      
      // 触发侧边栏刷新
      setSidebarRefreshTrigger(prev => prev + 1)
      
      console.log('Session renamed successfully:', newName)
    } catch (error) {
      console.error('Failed to rename session:', error)
      throw error
    }
  }

  // 删除会话处理函数
  const handleDeleteSession = async (sessionId: number): Promise<void> => {
    try {
      await deleteSession(sessionId)
      
      // 如果删除的是当前会话，清空当前会话状态
      if (currentSession && currentSession.id === sessionId) {
        setCurrentSession(null)
        setCurrentSessionId(null)
      }
      
      // 触发侧边栏刷新
      setSidebarRefreshTrigger(prev => prev + 1)
      
      console.log('Session deleted successfully')
    } catch (error) {
      console.error('Failed to delete session:', error)
      throw error
    }
  }
  
  // 处理会话更新（例如进入/退出共读模式）
  const handleSessionUpdate = (updatedSession: ChatSession) => {
    setCurrentSession(updatedSession)
    // 会话ID不变，无需更新currentSessionId
    console.log('会话已更新:', updatedSession)
  }

  // 实际创建会话（在用户发送第一条消息时调用）
  const createSessionFromMessage = async (firstMessageContent: string): Promise<ChatSession> => {
    try {
      // 使用LLM生成智能会话名称
      const newSession = await createSmartSession(firstMessageContent)
      
      // 设置为当前会话
      setCurrentSession(newSession)
      setCurrentSessionId(newSession.id)
      
      // 标记为新生成的会话，用于sidebar的打字机效果
      setNewlyGeneratedSessionId(newSession.id)
      
      // 将临时Pin文件绑定到新会话
      if (tempPinnedFiles.length > 0) {
        for (const file of tempPinnedFiles) {
          try {
            await pinFile(newSession.id, file.file_path, file.file_name, file.metadata)
          } catch (error) {
            console.error('Failed to bind temp pinned file to new session:', error)
          }
        }
        // 清空临时Pin文件
        setTempPinnedFiles([])
      }
      
      // 保存到Tauri Store
      await saveLastUsedSession(newSession.id)
      
      // 触发sidebar刷新列表
      setSidebarRefreshTrigger(prev => prev + 1)
      
      console.log('Created new session:', newSession.name, newSession.id)
      return newSession
    } catch (error) {
      console.error('Failed to create session from message:', error)
      throw error
    }
  }

  // 添加临时Pin文件
  const addTempPinnedFile = (filePath: string, fileName: string, metadata?: Record<string, any>) => {
    setTempPinnedFiles(prev => [...prev, { file_path: filePath, file_name: fileName, metadata }])
  }

  // 移除临时Pin文件
  const removeTempPinnedFile = (filePath: string) => {
    setTempPinnedFiles(prev => prev.filter(file => file.file_path !== filePath))
  }

  // 处理会话标题动画完成
  const handleTitleAnimationComplete = (sessionId: number) => {
    if (newlyGeneratedSessionId === sessionId) {
      setNewlyGeneratedSessionId(null)
    }
  }

  // 添加键盘快捷键监听
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // 检测 Cmd+, (macOS) 或 Ctrl+, (Windows/Linux)
      if ((event.metaKey || event.ctrlKey) && event.key === ',') {
        event.preventDefault()
        openSettingsPage(SETTINGS_PAGES.GENERAL)
      }
      // 检测 Cmd+P (macOS) 或 Ctrl+P (Windows/Linux)
      else if ((event.metaKey || event.ctrlKey) && event.key === 'p') {
        event.preventDefault()
        setSearchOpen(true)
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [openSettingsPage])

  // 监听菜单事件
  useEffect(() => {
    let unlistenFn: (() => void) | undefined

    listen("menu-settings", (event) => {
      const page = event.payload as string
      console.log("收到菜单设置事件，要打开的页面:", page)
      openSettingsPage(page === SETTINGS_PAGES.ABOUT ? SETTINGS_PAGES.ABOUT : SETTINGS_PAGES.GENERAL)
    })
      .then((fn) => {
        unlistenFn = fn
      })
      .catch((err) => {
        console.error("监听菜单事件失败:", err)
      })

    return () => {
      if (unlistenFn) {
        unlistenFn()
      }
    }
  }, [openSettingsPage])

  // * 监听来自Rust的IPC事件
  useBridgeEvents(
    {
      'api-ready': (payload: any) => {
        console.log("App.tsx: Received 'api-ready' event from backend.", payload)
        setApiReady(true) // Update global state so all components can react
      },
      'model-validation-failed': (payload: any) => {
        console.warn("App.tsx: Model validation failed:", payload)
        
        const { provider_type, model_id, role_type, available_models, error_message } = payload
        
        // 显示详细的错误toast
        toast.error(
          `模型配置错误: ${error_message}`,
          {
            description: `角色: ${role_type} | 提供商: ${provider_type} | 模型: ${model_id}${available_models?.length > 0 ? `\n可用模型: ${available_models.slice(0, 5).join(', ')}${available_models.length > 5 ? '...' : ''}` : ''}`,
            duration: 8000,
            action: {
              label: "打开设置",
              onClick: () => openSettingsPage(SETTINGS_PAGES.AI_MODELS)
            }
          }
        )
      },
      'tagging-model-missing': (payload: any) => {
        console.warn("App.tsx: Tagging model missing:", payload)
        
        const { message } = payload
        
        // 显示标签模型缺失的错误toast
        toast.error(
          `标签生成模型未配置`,
          {
            description: message || '无法生成文件标签，请配置标签生成相关的AI模型',
            duration: 8000,
            action: {
              label: "配置模型",
              onClick: () => openSettingsPage(SETTINGS_PAGES.AI_MODELS)
            }
          }
        )
      },
      // 工具通道事件处理
      'tool-call-request': async (payload: any) => {
        console.log("App.tsx: 收到工具调用请求:", payload)
        
        // 动态导入工具通道和工具实现
        const { handleToolCall } = await import('./lib/toolChannel')
        
        // 处理工具调用请求
        await handleToolCall(payload)
      },
      // 多模态向量化事件处理
      'multivector-progress': (payload: any) => {
        // console.log("App.tsx: Multivector progress:", payload)
        const { file_path, task_id, current, total, percentage, stage, message } = payload
        if (file_path) {
          const progressValue = percentage || (total > 0 ? Math.round((current / total) * 100) : 0)
          vectorizationStore.setFileProgress(file_path, progressValue, stage, message, task_id)
        }
      },
      'multivector-completed': (payload: any) => {
        // console.log("App.tsx: Multivector completed:", payload)
        const { file_path, task_id, parent_chunks_count, child_chunks_count } = payload
        if (file_path) {
          vectorizationStore.setFileCompleted(file_path, task_id, parent_chunks_count, child_chunks_count)
          
          // 显示成功toast
          toast.success(
            `文档向量化完成`,
            {
              description: `${file_path.split('/').pop()} • ${parent_chunks_count || 0}个父块 • ${child_chunks_count || 0}个子块`,
              duration: 4000
            }
          )
        }
      },
      'multivector-failed': (payload: any) => {
        console.warn("App.tsx: Multivector failed:", payload)
        const { file_path, task_id, error_message, help_link, error_code } = payload
        if (file_path) {
          vectorizationStore.setFileFailed(file_path, task_id, {
            message: error_message || '向量化失败',
            helpLink: help_link,
            errorCode: error_code
          })
          
          // 显示错误toast
          toast.error(
            `文档向量化失败`,
            {
              description: `${file_path.split('/').pop()}: ${error_message}`,
              duration: 6000,
              action: help_link ? {
                label: "获取帮助",
                onClick: () => window.open(help_link, '_blank')
              } : undefined
            }
          )
        }
      },
      // // RAG相关事件处理
      // 'rag-retrieval-result': (payload: any) => {
      //   console.log("App.tsx: RAG检索结果:", payload)
      //   // RAG数据将传递给RagLocal组件进行显示
      //   // 这里可以做一些全局状态管理，比如记录最近的RAG活动
      // },
      // 'rag-progress': (payload: any) => {
      //   console.log("App.tsx: RAG处理进度:", payload)
      //   // 可以在这里显示RAG处理的进度提示
      // },
      // 'rag-error': (payload: any) => {
      //   console.warn("App.tsx: RAG处理错误:", payload)
      //   const { error_message, stage } = payload
        
      //   toast.error(
      //     `知识检索失败`,
      //     {
      //       description: `${stage ? `[${stage}] ` : ''}${error_message}`,
      //       duration: 5000
      //     }
      //   )
      // }
    },
    { showToasts: false, logEvents: true }
  )

  // 始终显示 IntroDialog 作为 splash 屏幕，直到 API 就绪
  useEffect(() => {
    // 总是在启动时显示 IntroDialog，会根据 isFirstLaunch 和 isApiReady 决定行为:
    // - 如果 API 未就绪：显示加载状态
    // - 如果 API 就绪且不是首次启动：自动关闭对话框，显示主界面
    // - 如果 API 就绪且是首次启动：启用"开始使用"按钮，用户手动关闭
    setShowIntroDialog(true)
    console.log("App.tsx: IntroDialog 已设置为显示，等待 API 就绪")
  }, [])

  useEffect(() => {
    const startupSequence = async () => {
      // 日志首次启动状态
      console.log(
        `App.tsx: ${isFirstLaunch ? "First launch" : "Normal launch"} detected.`
      )
      console.log("App.tsx: Waiting for API ready signal from backend...")

      try {
        // 健康检查移到这里只作为后备方案，不会与全局状态冲突
        // 仅在 API 超时未就绪时才会使用健康检查来判断状态
        if (!isApiReady) {
          console.log(
            "App.tsx: Performing backup health check after 5 seconds..."
          )
          // 等待5秒，给予后端足够时间发送 api-ready 事件
          await new Promise((resolve) => setTimeout(resolve, 5000))

          // 如果仍然没有收到 api-ready 信号，尝试主动健康检查
          if (!useAppStore.getState().isApiReady) {
            console.log(
              "App.tsx: No api-ready event received, performing health check..."
            )
            try {
              const response = await fetch("http://127.0.0.1:60315/health", {
                method: "GET",
                signal: AbortSignal.timeout(2000),
              })

              if (response.ok) {
                console.log(
                  "App.tsx: Health check successful, manually setting API ready."
                )
                setApiReady(true)
              }
            } catch (error) {
              console.log(`App.tsx: Health check failed: ${error}`)
              // 不抛出错误，让应用继续显示等待状态
            }
          }
        }
      } catch (error) {
        console.error("App.tsx: Error during startup sequence:", error)
        const errorMessage = `API服务不可用: ${
          error instanceof Error ? error.message : String(error)
        }`

        setInitializationError(errorMessage)
        setApiReady(false)
        toast.error("API服务不可用，应用无法正常工作。请尝试重启应用。")
      } finally {
        // 无论结果如何，最终都设置为非初始化状态
        setIsInitializing(false)
      }
    }
    // 这里不再需要条件判断，因为 IntroDialog 会负责显示加载状态
    startupSequence()
  }, [isFirstLaunch, setIsInitializing, setInitializationError, setApiReady])

  if (initializationError) {
    // 初始化错误
    return (
      <div className="flex flex-col items-center justify-center h-screen w-screen bg-background text-foreground p-4">
        <div className="text-center bg-card p-8 rounded-lg shadow-lg border border-destructive">
          <h2 className="text-2xl font-bold text-destructive mb-4">
            应用初始化失败
          </h2>
          <p className="text-card-foreground mb-6">{initializationError}</p>
          <Button
            onClick={() => window.location.reload()}
            className="bg-primary hover:bg-primary/90 text-primary-foreground"
          >
            重新加载应用
          </Button>
        </div>
      </div>
    )
  }

  return (
    <SidebarProvider>
        <AppSidebar 
          currentSessionId={currentSessionId ?? undefined}
          onSessionSwitch={handleSessionSwitch}
          onCreateSession={handleCreateSession}
          refreshTrigger={sidebarRefreshTrigger}
          newlyGeneratedSessionId={newlyGeneratedSessionId}
          onTitleAnimationComplete={handleTitleAnimationComplete}
          onRenameSession={handleRenameSession}
          onDeleteSession={handleDeleteSession}
          searchOpen={searchOpen}
          onSearchOpenChange={setSearchOpen}
        />
          {isApiReady ? (
            <AppWorkspace 
              currentSession={currentSession}
              currentSessionId={currentSessionId}
              tempPinnedFiles={tempPinnedFiles}
              onCreateSessionFromMessage={createSessionFromMessage}
              onAddTempPinnedFile={addTempPinnedFile}
              onRemoveTempPinnedFile={removeTempPinnedFile}
              chatResetTrigger={chatResetTrigger}
              onSessionUpdate={handleSessionUpdate}
            />
          ) : (
            <div className="flex flex-1 items-center justify-center">
              <div className="relative w-10 h-10">
                <svg className="animate-spin" viewBox="0 0 24 24" fill="none" stroke="#D29B71" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="12" y1="2" x2="12" y2="6"></line>
                  <line x1="12" y1="18" x2="12" y2="22"></line>
                  <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line>
                  <line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line>
                  <line x1="2" y1="12" x2="6" y2="12"></line>
                  <line x1="18" y1="12" x2="22" y2="12"></line>
                  <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line>
                  <line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line>
                </svg>
              </div>
            </div>
          )}
          <IntroDialog
            open={showIntroDialog}
            onOpenChange={setShowIntroDialog}
          />
          <Toaster />
    </SidebarProvider>
  )
}
