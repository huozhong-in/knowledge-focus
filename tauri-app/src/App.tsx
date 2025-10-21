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
import { SidebarProvider } from "@/components/ui/sidebar"
import { AppSidebar } from "./app-sidebar"
import { AppWorkspace } from "./app-workspace"
import Splash from "./splash"
import { useBridgeEvents } from "@/hooks/useBridgeEvents"
import { useVectorizationStore } from "@/stores/useVectorizationStore"
import { ChatSession, createSmartSession, pinFile, updateSession, deleteSession, getPinnedFiles } from "./lib/chat-session-api"
import { useAuthStore } from "@/lib/auth-store"

// 环境配置
const isDevelopment = import.meta.env.MODE === 'development';
const AUTH_BASE_URL = isDevelopment 
  ? 'http://127.0.0.1:60325'  // 开发环境：本地 auth 服务器
  : 'https://kf.huozhong.in'; // 生产环境：Cloudflare Pages 部署地址

const API_BASE_URL = 'http://127.0.0.1:60315'

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

export default function App() {
  const {
    isApiReady, // Get global API ready state
    setApiReady, // Get action to set API ready state
  } = useAppStore()

  const { openSettingsPage } = useSettingsStore()
  const [showSplash, setShowSplash] = useState(true)
  
  // 认证相关
  const { checkAuth, initAuthListener } = useAuthStore()

  // 监听来自Python后端的OAuth回调事件（替代better-auth-tauri）
  useBridgeEvents({
    'oauth-callback-success': async (payload: any) => {
      console.log("收到OAuth成功回调:", payload);
      toast.success("OAuth认证成功！正在完成登录...");
      
      try {
        // 使用授权码完成认证流程
        const { code, state, provider = 'google' } = payload; // 从 payload 获取 provider，默认为 google
        
        // 调用better-auth的token交换端点
        const response = await fetch(`${AUTH_BASE_URL}/api/auth/callback/${provider}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            code,
            state,
          }),
          credentials: 'include', // 重要：包含cookies
        });
        
        if (response.ok) {
          console.log("Token交换成功");
          toast.success("登录成功！");
          // 重新检查认证状态
          await checkAuth();
        } else {
          throw new Error('Token交换失败');
        }
      } catch (error) {
        console.error("完成OAuth流程时出错:", error);
        toast.error("登录完成失败，请重试");
      }
    },
    
    'oauth-callback-error': (payload: any) => {
      console.error("收到OAuth错误回调:", payload);
      toast.error(`OAuth认证失败: ${payload.error_description || payload.error}`);
    }
  }, { showToasts: false, logEvents: true });

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
  
  // 临时选择的工具状态（在会话创建前临时保存）
  const [tempSelectedTools, setTempSelectedTools] = useState<string[]>([])
  
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
      
      // ⚠️ 延迟检查认证状态，等待 Zustand persist 完成数据水合
      // Zustand persist 从 Tauri Store 加载数据是异步的,需要等待完成
      const timer = setTimeout(() => {
        console.log('🔍 延迟检查认证状态 (等待数据水合完成)...');
        checkAuth();
      }, 100); // 100ms 延迟足够让 persist 完成加载
      
      // 初始化 OAuth 事件监听器
      let unlistenOAuth: (() => void) | null = null
      initAuthListener().then(unlisten => {
        unlistenOAuth = unlisten
      }).catch(err => {
        console.error('Failed to init auth listener:', err)
      })
      
      // 清理函数
      return () => {
        clearTimeout(timer);
        if (unlistenOAuth) {
          unlistenOAuth()
        }
      }
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
      
      // 清空临时工具选择（切换到已存在的会话）
      setTempSelectedTools([])
      
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
        
        // 清空临时工具选择（已经在AiSdkChat中处理了工具应用）
        setTempSelectedTools([])
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

  // 添加临时工具选择
  const addTempSelectedTool = (toolName: string) => {
    setTempSelectedTools(prev => {
      if (!prev.includes(toolName)) {
        return [...prev, toolName]
      }
      return prev
    })
  }

  // 移除临时工具选择
  const removeTempSelectedTool = (toolName: string) => {
    setTempSelectedTools(prev => prev.filter(tool => tool !== toolName))
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
      // 检测 Cmd+, (macOS) 或 Alt+, (Windows/Linux)
      if ((event.metaKey || event.altKey) && event.key === ',') {
        event.preventDefault()
        openSettingsPage(SETTINGS_PAGES.GENERAL)
      }
      // 检测 Cmd+P (macOS) 或 Alt+P (Windows/Linux)
      else if ((event.metaKey || event.altKey) && event.key === 'p') {
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
    let isMounted = true

    const setupListener = async () => {
      try {
        const fn = await listen("menu-settings", (event) => {
          if (!isMounted) return // 组件已卸载，忽略事件
          
          const page = event.payload as string
          console.log("收到菜单设置事件，要打开的页面:", page)
          openSettingsPage(page === SETTINGS_PAGES.ABOUT ? SETTINGS_PAGES.ABOUT : SETTINGS_PAGES.GENERAL)
        })
        
        if (isMounted) {
          unlistenFn = fn
        } else {
          // 如果组件已经卸载，立即清理
          fn()
        }
      } catch (err) {
        if (isMounted) {
          console.error("监听菜单事件失败:", err)
        }
      }
    }

    setupListener()

    return () => {
      isMounted = false
      if (unlistenFn) {
        try {
          unlistenFn()
        } catch (error) {
          // 忽略清理时的错误
        }
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
    },
    { showToasts: false, logEvents: true }
  )

  useEffect(() => {
    const startupSequence = async () => {
      try {
        // 健康检查在这里只作为后备方案，不会与全局状态冲突
        // 仅在始终没收到'api-ready'事件时才进行检查
        console.log(
          "App.tsx: Performing backup health check..."
        )
        const max_retries = 10000
        const retry_interval = 1000
        if (!isApiReady) {
          for (let attempt = 1; attempt <= max_retries; attempt++) {
            const response = await fetch(`${API_BASE_URL}/health`, {
              method: "GET",
              signal: AbortSignal.timeout(2000),
            })
            if (response.ok) {
              console.log("App.tsx: API is ready.")
              setApiReady(true)
              break
            }
            await new Promise((resolve) => setTimeout(resolve, retry_interval))
          }
        }
      } catch (error) {
        console.log("App.tsx: Error during startup sequence:", error)
        // const errorMessage = `API service is unavailable: ${
        //   error instanceof Error ? error.message : String(error)
        // }`
        setApiReady(false)
        // toast.error("API service error", { description: errorMessage, duration: 8000 })
      }
    }
    startupSequence()
  }, [])

  if (showSplash){
    return (
      <Splash setShowSplash={setShowSplash} />
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
        <AppWorkspace 
          currentSession={currentSession}
          currentSessionId={currentSessionId}
          tempPinnedFiles={tempPinnedFiles}
          tempSelectedTools={tempSelectedTools}
          onCreateSessionFromMessage={createSessionFromMessage}
          onAddTempPinnedFile={addTempPinnedFile}
          onRemoveTempPinnedFile={removeTempPinnedFile}
          onAddTempSelectedTool={addTempSelectedTool}
          onRemoveTempSelectedTool={removeTempSelectedTool}
          chatResetTrigger={chatResetTrigger}
          onSessionUpdate={handleSessionUpdate}
        />          
      <Toaster />
    </SidebarProvider>
  )
}
