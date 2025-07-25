import "./index.css"
import "./tweakcn/app/globals.css"
import { useEffect, useState } from "react"
import { create } from "zustand"
import { useAppStore } from "./main"
import { Toaster } from "@/components/ui/sonner"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { SidebarProvider } from "@/components/ui/sidebar"
import { AppSidebar } from "./app-sidebar"
import { AppWorkspace } from "./app-workspace"
import IntroDialog from "./intro-dialog"
import { SettingsDialog } from "./settings-dialog"
import { useBridgeEvents } from "@/hooks/useBridgeEvents"

// 创建一个store来管理页面内容
interface PageState {
  currentPage: string
  currentTitle: string
  currentSubtitle: string
  setPage: (page: string, title: string, subtitle: string) => void
}

export const usePageStore = create<PageState>((set) => ({
  currentPage: "new_task", // 默认为new_task页面，会在组件中根据是否首次启动进行调整
  currentTitle: "新建任务",
  currentSubtitle: "新建数据任务",
  setPage: (page, title, subtitle) =>
    set({
      currentPage: page,
      currentTitle: title,
      currentSubtitle: subtitle,
    }),
}))

// 创建一个store来管理设置对话框状态
interface SettingsState {
  isSettingsOpen: boolean
  initialPage: string
  setSettingsOpen: (open: boolean) => void
  setInitialPage: (page: string) => void
}

export const useSettingsStore = create<SettingsState>((set) => ({
  isSettingsOpen: false,
  initialPage: "general",
  setSettingsOpen: (open) => set({ isSettingsOpen: open }),
  setInitialPage: (page) => set({ initialPage: page }),
}))

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

  const { setSettingsOpen } = useSettingsStore()
  const [showIntroDialog, setShowIntroDialog] = useState(false)

  // 添加键盘快捷键监听
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // 检测 Cmd+, (macOS) 或 Ctrl+, (Windows/Linux)
      if ((event.metaKey || event.ctrlKey) && event.key === ',') {
        event.preventDefault()
        setSettingsOpen(true)
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [setSettingsOpen])

  // 监听菜单事件
  // useEffect(() => {
  //   let unlistenFn: (() => void) | undefined

  //   listen("menu-settings", (event) => {
  //     const page = event.payload as string
  //     console.log("收到菜单设置事件，要打开的页面:", page)
  //     setSettingsOpen(true)
  //     setInitialPage(page === "about" ? "about" : "general")
  //   })
  //     .then((fn) => {
  //       unlistenFn = fn
  //     })
  //     .catch((err) => {
  //       console.error("监听菜单事件失败:", err)
  //     })

  //   return () => {
  //     if (unlistenFn) {
  //       unlistenFn()
  //     }
  //   }
  // }, [setSettingsOpen, setInitialPage])

  // Listen for 'api-ready' event from backend ONCE using useBridgeEvents
  // 这是应用中唯一需要监听 api-ready 事件的地方
  useBridgeEvents(
    {
      'api-ready': (payload: any) => {
        console.log("App.tsx: Received 'api-ready' event from backend.", payload)
        setApiReady(true) // Update global state so all components can react
      }
    },
    { showToasts: false, logEvents: true }
  )

  // Fallback: 如果5秒内没有收到api-ready事件，自动设置为就绪
  // useEffect(() => {
  //   const fallbackTimer = setTimeout(() => {
  //     if (!useAppStore.getState().isApiReady) {
  //       console.warn("App.tsx: Fallback - No 'api-ready' event received. Setting API ready after timeout.")
  //       setApiReady(true)
  //     }
  //   }, 5000) // 5-second fallback delay

  //   return () => {
  //     clearTimeout(fallbackTimer)
  //   }
  // }, [setApiReady])

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
        <AppSidebar />
          {isApiReady ? (
            <AppWorkspace />
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
      {/* 全局设置对话框，可通过快捷键打开 */}
      <SettingsDialog />
    </SidebarProvider>
  )
}
