import "./index.css";
import "./theme-whiskey.css"; // 引入威士忌主题
import "./theme/whiskey-colors.css"; // 引入显式定义的威士忌颜色类
import { AppSidebar } from "@/components/app-sidebar"
import { useEffect, useState } from "react";
// import {
//   Breadcrumb,
//   BreadcrumbItem,
//   BreadcrumbLink,
//   BreadcrumbList,
//   BreadcrumbPage,
//   BreadcrumbSeparator,
// } from "@/components/ui/breadcrumb"
// import { Separator } from "@/components/ui/separator"
import { Button } from "@/components/ui/button";
import {
  SidebarInset,
  SidebarProvider,
  // SidebarTrigger,
} from "@/components/ui/sidebar"
import { Toaster } from "@/components/ui/sonner";
import { toast } from "sonner";
import IntroDialog from "./components/IntroDialog";
import HomeKnowledgeBase from "./home-knowledgebase";
import HomeAuthorization from "./home-authorization";
import HomeWiseFolders from "./home-wisefolders";
import ModelsLocal from "./models-local";
import ModelsDomestic from "./models-domestic";
import ModelsOverseas from "./models-overseas";
import PromptsLibrary from "./prompts-library";
import SettingsGeneral from "./settings-general";
import SettingsDeveloperZone from "./settings-developerzone";
import SettingsTheme from "./settings-theme";
import { FullDiskFolderView } from './pinned-folders';
import { create } from 'zustand';
import { useAppStore } from './main'; // Correct import
import { listen } from '@tauri-apps/api/event'; // Added for api-ready listener

// 创建一个store来管理页面内容
interface PageState {
  currentPage: string;
  currentTitle: string;
  currentSubtitle: string;
  setPage: (page: string, title: string, subtitle: string) => void;
}

export const usePageStore = create<PageState>((set) => ({
  currentPage: "today", // 默认为today页面，会在组件中根据是否首次启动进行调整
  currentTitle: "今日更新",
  currentSubtitle: "最近修改的文件",
  setPage: (page, title, subtitle) => set({ 
    currentPage: page, 
    currentTitle: title,
    currentSubtitle: subtitle 
  }),
}));

export default function Page() {
  const { currentPage, setPage } = usePageStore();
  const {
    isFirstLaunch,
    isInitializing,
    initializationError,
    setIsInitializing,
    setInitializationError,
    showWelcomeDialog,
    isApiReady, // Get global API ready state
    setApiReady,   // Get action to set API ready state
  } = useAppStore();

  const [apiServiceChecked, setApiServiceChecked] = useState(false); // Tracks if initial API health check is done
  const [showIntroDialog, setShowIntroDialog] = useState(false);

  // Listen for 'api-ready' event from backend ONCE
  useEffect(() => {
    console.log("App.tsx: Setting up 'api-ready' event listener.");
    let unlistenFn: (() => void) | undefined;

    listen('api-ready', (event) => {
      console.log("App.tsx: Received 'api-ready' event from backend.", event);
      setApiReady(true); // Update global state
    }).then(fn => {
      unlistenFn = fn;
    }).catch(err => {
      console.error("App.tsx: Failed to listen for 'api-ready' event", err);
      // Fallback: if event listening fails, consider API ready after a delay
      // This might be hit if the event was emitted before listener was attached
      // Or if there's an issue with Tauri's event system.
      setTimeout(() => {
        // Check global state before setting to avoid unnecessary updates if already true
        if (!useAppStore.getState().isApiReady) { 
          console.warn("App.tsx: Fallback - 'api-ready' event likely missed or listener failed. Setting API ready.");
          setApiReady(true);
        }
      }, 3000); // 3-second fallback delay
    });

    return () => {
      if (unlistenFn) {
        console.log("App.tsx: Cleaning up 'api-ready' event listener.");
        unlistenFn();
      }
    };
  }, [setApiReady]); // setApiReady is stable, so this runs once

  // 根据是否首次启动设置初始页面, dependent on global isApiReady
  useEffect(() => {
    if (!isApiReady) { // Use global isApiReady
      console.log("App.tsx: Global API not ready yet, delaying page initialization");
      return;
    }

    if (isFirstLaunch) {
      console.log("App.tsx: First launch & API ready, setting page to authorization");
      setPage("home-authorization", "Home", "授权管理");
    } else {
      console.log("App.tsx: Normal launch & API ready, setting page to today");
      setPage("today", "今日更新", "最近修改的文件");
    }
  }, [isFirstLaunch, setPage, isApiReady]); // Depend on global isApiReady

  // 当应用成功加载并且需要显示欢迎对话框时，显示 IntroDialog
  useEffect(() => {
    // Ensure API is ready, health check passed, not initializing, no errors, and dialog is requested
    if (apiServiceChecked && isApiReady && !isInitializing && !initializationError && showWelcomeDialog) {
      setShowIntroDialog(true);
    }
  }, [apiServiceChecked, isApiReady, isInitializing, initializationError, showWelcomeDialog]);

  useEffect(() => {
    const startupSequence = async () => {
      // isInitializing is set to true in main.tsx's initializeApp
      // useAppStore.setState({ isInitializing: true }); // This ensures we are in initializing state

      // 检查是否是首次启动
      if (isFirstLaunch) {
        console.log("App.tsx: First launch detected.");
      } else {
        console.log("App.tsx: Normal launch. Ensuring API service is running.");
      }

      try {
        // Step 1: 检查 API 服务是否可用
        console.log("App.tsx: Checking API service health...");
        
        const maxRetries = 20; // 最多等待20次
        const retryDelay = 500; // 每次等待500ms
        let isHealthCheckOk = false;
        let retries = 0;
        
        while (retries < maxRetries && !isHealthCheckOk) {
          console.log(`App.tsx: Checking API health (attempt ${retries + 1}/${maxRetries})...`);
          try {
            const response = await fetch('http://127.0.0.1:60315/health', { 
              method: 'GET',
              signal: AbortSignal.timeout(2000) // 2秒超时
            });
            
            if (response.ok) {
              console.log("App.tsx: API service health check OK!");
              isHealthCheckOk = true;
            } else {
              console.log(`App.tsx: API service health check responded with status ${response.status}`);
              await new Promise(resolve => setTimeout(resolve, retryDelay));
            }
          } catch (error) {
            console.log(`App.tsx: API service health check not ok yet: ${error}`);
            await new Promise(resolve => setTimeout(resolve, retryDelay));
          }
          retries++;
        }
        
        if (!isHealthCheckOk) {
          throw new Error(`无法连接到API服务或服务不健康，已尝试${maxRetries}次。请检查API服务是否正确启动。`);
        }
        
        setApiServiceChecked(true); // Mark that the health check has passed

        // 初始化过程由服务端自动完成
        // The 'api-ready' event listener (setup elsewhere) will set the global isApiReady state.
        // No need to set it directly here.

        if (isFirstLaunch) {
          console.log("App.tsx: API service available. First launch initialization is now handled by the API server.");
          // 注意：我们保留首次启动标记，直到用户完成授权流程后再在授权页面中清除
          // 这样可以确保用户在首次启动时一定会看到授权页面
          // setFirstLaunch(false);
        }
      } catch (error) {
        console.error("App.tsx: Error during API health check:", error);
        const errorMessage = `API服务不可用: ${error instanceof Error ? error.message : String(error)}`;
        
        setApiServiceChecked(false); // API check failed
        setInitializationError(errorMessage);
        setApiReady(false); // Ensure API is marked as not ready globally
        toast.error("API服务不可用，应用无法正常工作。请尝试重启应用。");
      } finally {
        // 无论结果如何，都设置为非初始化状态
        setIsInitializing(false); // Mark initialization phase as complete
      }
    };
    // Only run startupSequence if not already run (e.g. if isInitializing is true from store)
    if (isInitializing) {
        startupSequence();
    }
  }, [isFirstLaunch, setIsInitializing, setInitializationError, setApiReady, isInitializing]); // Added isInitializing

  // WebSocket connection effect
  useEffect(() => {
    const canConnectWebSocket = isApiReady && !isInitializing && !initializationError;

    if (!canConnectWebSocket) {
      console.log("App.tsx: Conditions not met for WebSocket connection (API started:", isApiReady, ", initializing:", isInitializing, ", error:", initializationError,")");
      // Corrected log to use isApiReady
      console.log("App.tsx: Conditions not met for WebSocket connection (isApiReady:", isApiReady, ", initializing:", isInitializing, ", error:", initializationError,")");
      return;
    }

    console.log("App.tsx: Conditions met. Attempting to connect WebSocket.");
    let wsInstance: WebSocket | null = null;
    
    const connectWebSocket = () => {
      if (wsInstance) {
        wsInstance.onclose = null; 
        wsInstance.close();
      }
      wsInstance = new WebSocket("ws://127.0.0.1:60315/ws");
      wsInstance.onopen = (event) => {
        console.log("WebSocket连接已建立", event);
      };
      wsInstance.onmessage = (event) => {
        console.log("收到任务状态更新:", event.data);
        try {
          const notification = JSON.parse(event.data);
          if (notification.status === "completed") {
            toast.success(notification.message);
          } else if (notification.status === "failed") {
            toast.error(notification.message);
          }
        } catch (e) {
          toast.info(event.data);
        }
      };
      wsInstance.onclose = (event) => {
        console.log("WebSocket连接已关闭，尝试重新连接...", event);
        if (wsInstance && document.visibilityState === 'visible') { // Check if still relevant
            setTimeout(() => {
                if (wsInstance) connectWebSocket();
            }, 5000);
        }
      };
      wsInstance.onerror = (error) => {
        console.error("WebSocket错误:", error);
      };
    };

    connectWebSocket();

    return () => {
      console.log("App.tsx: Cleaning up WebSocket connection on effect re-run or unmount.");
      if (wsInstance) {
        wsInstance.onclose = null; // 防止卸载时触发重连
        wsInstance.close();
        wsInstance = null;

      }
    };
  }, [isApiReady, isInitializing, initializationError]); // Depend on global isApiReady


  // Conditional Rendering based on initialization state
  if (isInitializing) { // 首次启动时的初始化阶段
    return (
      <div className="flex items-center justify-center h-screen w-screen bg-background text-foreground">
        <div className="text-center">
          <p className="text-xl font-semibold animate-pulse">正在准备应用...</p>
          <p className="text-muted-foreground">请稍候，正在初始化...</p>
        </div>
      </div>
    );
  }

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
  const renderContent = () => {
    console.log("App.tsx: Rendering content for page:", currentPage);
    // Ensure API is ready before rendering content that might depend on it
    // However, some pages like settings might not need API ready.
    // For now, we'll let individual components handle their "API not ready" state if needed.
    // The FullDiskFolderView already does this.

    switch (currentPage) {
      case "home-knowledgebase":
        return <HomeKnowledgeBase />;
      case "home-wisefolders":
        return <HomeWiseFolders />;
      case "home-authorization":
        return <HomeAuthorization />;
      case "models-local":
        return <ModelsLocal />;
      case "models-domestic":
        return <ModelsDomestic />;
      case "models-overseas":
        return <ModelsOverseas />;
      case "prompts-library":
        return <PromptsLibrary />;
      case "settings-general":
        return <SettingsGeneral />;
      case "settings-theme":
        return <SettingsTheme />;
      case "settings-developerzone":
        return <SettingsDeveloperZone />;
      // Render the single FullDiskFolderView for all pinned folder cases
      case "today":
      case "last7days":
      case "last30days":
      case "image":
      case "audio-video":
      case "archive":
        // Pass the currentPage (which is the folderId) as a prop
        return <FullDiskFolderView folderId={currentPage} />;
      default:
        // Fallback to a safe page if API is not ready, or a default page
        return isApiReady ? <HomeKnowledgeBase /> : (
          <div className="flex items-center justify-center h-full">
            <p>等待API服务就绪...</p>
          </div>
        );
    }
  };

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        {/* <header className="flex h-16 shrink-0 items-center gap-2 transition-[width,height] ease-linear group-has-[[data-collapsible=icon]]/sidebar-wrapper:h-12">
          <div className="flex items-center gap-2 px-4">
            <SidebarTrigger className="-ml-1" />
            <Separator orientation="vertical" className="mr-2 h-4" />
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem className="hidden md:block">
                  <BreadcrumbLink href="#">
                    {currentTitle}
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator className="hidden md:block" />
                <BreadcrumbItem>
                  <BreadcrumbPage>{currentSubtitle}</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </div>
        </header> */}
        {renderContent()}
        <IntroDialog open={showIntroDialog} onOpenChange={setShowIntroDialog} />
        <Toaster />
      </SidebarInset>
    </SidebarProvider>
  )
}
