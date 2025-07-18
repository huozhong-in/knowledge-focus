import "./index.css";
import "./tweakcn/app/globals.css";
import { useEffect, useState } from "react";
import { create } from 'zustand';
import { useAppStore } from './main';
import { listen } from '@tauri-apps/api/event';
import { Toaster } from "@/components/ui/sonner";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "./AppSidebar";
import { AppWorkspace } from "./AppWorkspace";
import IntroDialog from "./components/intro-dialog";


// 创建一个store来管理页面内容
interface PageState {
  currentPage: string;
  currentTitle: string;
  currentSubtitle: string;
  setPage: (page: string, title: string, subtitle: string) => void;
}

export const usePageStore = create<PageState>((set) => ({
  currentPage: "new_task", // 默认为new_task页面，会在组件中根据是否首次启动进行调整
  currentTitle: "新建任务",
  currentSubtitle: "新建数据任务",
  setPage: (page, title, subtitle) => set({ 
    currentPage: page, 
    currentTitle: title,
    currentSubtitle: subtitle 
  }),
}));

export default function Page() {
  const {
    isFirstLaunch,
    // isInitializing,
    initializationError,
    setIsInitializing,
    setInitializationError,
    isApiReady, // Get global API ready state
    setApiReady,   // Get action to set API ready state
  } = useAppStore();

  const [showIntroDialog, setShowIntroDialog] = useState(false);

  // Listen for 'api-ready' event from backend ONCE
  // 这是应用中唯一需要监听 api-ready 事件的地方
  useEffect(() => {
    console.log("App.tsx: Setting up 'api-ready' event listener.");
    let unlistenFn: (() => void) | undefined;

    listen('api-ready', (event) => {
      console.log("App.tsx: Received 'api-ready' event from backend.", event);
      setApiReady(true); // Update global state so all components can react
    }).then(fn => {
      unlistenFn = fn;
    }).catch(err => {
      console.error("App.tsx: Failed to listen for 'api-ready' event", err);
      // Fallback: if event listening fails, consider API ready after a delay
      setTimeout(() => {
        // Check global state before setting to avoid unnecessary updates
        if (!useAppStore.getState().isApiReady) { 
          console.warn("App.tsx: Fallback - 'api-ready' event listener failed. Setting API ready after timeout.");
          setApiReady(true);
        }
      }, 5000); // 5-second fallback delay
    });

    return () => {
      if (unlistenFn) {
        console.log("App.tsx: Cleaning up 'api-ready' event listener.");
        unlistenFn();
      }
    };
  }, [setApiReady]); // setApiReady is stable, so this runs once

  // 根据是否首次启动设置初始页面, dependent on global isApiReady
  // useEffect(() => {
  //   if (!isApiReady) { // Use global isApiReady
  //     console.log("App.tsx: Global API not ready yet, delaying page initialization");
  //     return;
  //   }

  //   if (isFirstLaunch) {
  //     console.log("App.tsx: First launch & API ready, setting page to authorization");
  //     setPage("settings-authorization", "settings", "授权管理");
  //   } else {
  //     console.log("App.tsx: Normal launch & API ready, setting page to new_task");
  //     setPage("new_task", "新建任务", "新建数据任务");
  //   }
  // }, [isFirstLaunch, setPage, isApiReady]); // Depend on global isApiReady

  // 始终显示 IntroDialog 作为 splash 屏幕，直到 API 就绪
  useEffect(() => {
    // 总是在启动时显示 IntroDialog，会根据 isFirstLaunch 和 isApiReady 决定行为:
    // - 如果 API 未就绪：显示加载状态
    // - 如果 API 就绪且不是首次启动：自动关闭对话框，显示主界面
    // - 如果 API 就绪且是首次启动：启用"开始使用"按钮，用户手动关闭
    setShowIntroDialog(true);
    console.log("App.tsx: IntroDialog 已设置为显示，等待 API 就绪");
  }, []);

  useEffect(() => {
    const startupSequence = async () => {
      // 日志首次启动状态
      console.log(`App.tsx: ${isFirstLaunch ? "First launch" : "Normal launch"} detected.`);
      console.log("App.tsx: Waiting for API ready signal from backend...");
      
      try {
        // 健康检查移到这里只作为后备方案，不会与全局状态冲突
        // 仅在 API 超时未就绪时才会使用健康检查来判断状态
        if (!isApiReady) {
          console.log("App.tsx: Performing backup health check after 5 seconds...");
          // 等待5秒，给予后端足够时间发送 api-ready 事件
          await new Promise(resolve => setTimeout(resolve, 5000));
          
          // 如果仍然没有收到 api-ready 信号，尝试主动健康检查
          if (!useAppStore.getState().isApiReady) {
            console.log("App.tsx: No api-ready event received, performing health check...");
            try {
              const response = await fetch('http://127.0.0.1:60315/health', { 
                method: 'GET',
                signal: AbortSignal.timeout(2000)
              });
              
              if (response.ok) {
                console.log("App.tsx: Health check successful, manually setting API ready.");
                setApiReady(true);
              }
            } catch (error) {
              console.log(`App.tsx: Health check failed: ${error}`);
              // 不抛出错误，让应用继续显示等待状态
            }
          }
        }

      } catch (error) {
        console.error("App.tsx: Error during startup sequence:", error);
        const errorMessage = `API服务不可用: ${error instanceof Error ? error.message : String(error)}`;
        
        setInitializationError(errorMessage);
        setApiReady(false);
        toast.error("API服务不可用，应用无法正常工作。请尝试重启应用。");
      } finally {
        // 无论结果如何，最终都设置为非初始化状态
        setIsInitializing(false);
      }
    };
    // 这里不再需要条件判断，因为 IntroDialog 会负责显示加载状态
    startupSequence();
  }, [isFirstLaunch, setIsInitializing, setInitializationError, setApiReady]);

  if (initializationError) { // 初始化错误
    return (
      <div className="flex flex-col items-center justify-center h-screen w-screen bg-background text-foreground p-4">
        <div className="text-center bg-card p-8 rounded-lg shadow-lg border border-destructive">
          <h2 className="text-2xl font-bold text-destructive mb-4">应用初始化失败</h2>
          <p className="text-card-foreground mb-6">{initializationError}</p>
          <Button onClick={() => window.location.reload()} className="bg-primary hover:bg-primary/90 text-primary-foreground">
            重新加载应用
          </Button>
        </div>
      </div>
    );
  }


  // 根据currentPage返回对应的组件
  // const renderContent = () => {
  //   console.log("App.tsx: Rendering content for page:", currentPage);
    
  //   // 如果API尚未就绪且显示IntroDialog，则返回空内容，避免不必要的组件初始化
  //   if (!isApiReady && showIntroDialog) {
  //     return null;
  //   }
    
  //   switch (currentPage) {
  //     case "home-knowledgebase":
  //       return <AppWorkspace />;
  //     case "home-authorization":
  //       return <SettingsAuthorization />;
  //     case "models-local":
  //       return <SettingsLocalModels />;
  //     default:
  //       // Fallback to a safe page if API is not ready, or a default page
  //       return isApiReady ? <AppWorkspace /> : (
  //         <div className="flex items-center justify-center h-full">
  //           <p>等待API服务就绪...</p>
  //         </div>
  //       );
  //   }
  // };
  return (
    <SidebarProvider>
      <div className="flex h-full">
        <AppSidebar />
        <SidebarInset>
          {isApiReady ? <AppWorkspace /> : <div>等待API服务就绪...</div>}
          <IntroDialog open={showIntroDialog} onOpenChange={setShowIntroDialog} />
          <Toaster />
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
  // return (
  //   <SidebarProvider>
  //     <AppSidebar />
  //     <SidebarInset>
  //       <header className="flex h-16 shrink-0 items-center gap-2 transition-[width,height] ease-linear group-has-[[data-collapsible=icon]]/sidebar-wrapper:h-12">
  //         <div className="flex items-center gap-2 px-4">
  //         </div>
  //       </header>
  //       {renderContent()}
  //       <IntroDialog open={showIntroDialog} onOpenChange={setShowIntroDialog} />
  //       <Toaster />
  //     </SidebarInset>
  //   </SidebarProvider>
  // )
}
