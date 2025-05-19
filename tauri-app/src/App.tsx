import "./index.css";
import "./theme-whiskey.css"; // 引入威士忌主题
import "./theme/whiskey-colors.css"; // 引入显式定义的威士忌颜色类
import { AppSidebar } from "@/components/app-sidebar"
import { useEffect, useState } from "react";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Separator } from "@/components/ui/separator"
import { Button } from "@/components/ui/button";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { Toaster } from "@/components/ui/sonner";
import { toast } from "sonner";
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
import { create } from 'zustand';
import { useAppStore, ensureDatabaseInitialized } from './main'; // Import Zustand store and DB init function

// 创建一个store来管理页面内容
interface PageState {
  currentPage: string;
  currentTitle: string;
  currentSubtitle: string;
  setPage: (page: string, title: string, subtitle: string) => void;
}

export const usePageStore = create<PageState>((set) => ({
  currentPage: "home-knowledgebase",
  currentTitle: "Home",
  currentSubtitle: "Knowledge Base",
  setPage: (page, title, subtitle) => set({ 
    currentPage: page, 
    currentTitle: title,
    currentSubtitle: subtitle 
  }),
}));

export default function Page() {
  const { currentPage, currentTitle, currentSubtitle } = usePageStore();
  const {
    isFirstLaunchDbCheckPending,
    isDbInitializing,
    dbInitializationError,
    setIsDbInitializing,
    setDbInitializationError,
    setFirstLaunchDbCheckPending,
  } = useAppStore();

  const [apiServiceStarted, setApiServiceStarted] = useState(false);

  // Effect for the entire startup sequence (API + DB init if needed)
  useEffect(() => {
    const startupSequence = async () => {
      if (isFirstLaunchDbCheckPending) {
        setIsDbInitializing(true); // Show full-screen loading for DB init
        setDbInitializationError(null);
        console.log("App.tsx: First launch detected. Starting full initialization sequence.");
      } else {
        console.log("App.tsx: Normal launch. Ensuring API service is running.");
      }

      try {
        // Step 1: 检查 API 服务是否可用
        console.log("App.tsx: Checking API service availability...");
        
        // 跳过调用 start_api_service，直接检测API是否可用
        // FastAPI 服务已经在应用启动时自动启动了
        const maxRetries = 20; // 最多等待20次
        const retryDelay = 500; // 每次等待500ms
        let isApiAvailable = false;
        let retries = 0;
        
        while (retries < maxRetries && !isApiAvailable) {
          console.log(`App.tsx: Checking API availability (attempt ${retries + 1}/${maxRetries})...`);
          try {
            const response = await fetch('http://127.0.0.1:60000/health', { 
              method: 'GET',
              signal: AbortSignal.timeout(2000) // 2秒超时
            });
            
            if (response.ok) {
              console.log("App.tsx: API service is available!");
              isApiAvailable = true;
            } else {
              console.log(`App.tsx: API service responded with status ${response.status}`);
              await new Promise(resolve => setTimeout(resolve, retryDelay));
            }
          } catch (error) {
            console.log(`App.tsx: API service not available yet: ${error}`);
            await new Promise(resolve => setTimeout(resolve, retryDelay));
          }
          retries++;
        }
        
        if (!isApiAvailable) {
          throw new Error(`无法连接到API服务，已尝试${maxRetries}次。请检查API服务是否正确启动。`);
        }
        
        // API服务已确认可用
        setApiServiceStarted(true);

        // Step 2: Initialize Database if it's the first launch
        if (isFirstLaunchDbCheckPending) {
          console.log("App.tsx: API service available. Now initializing database...");
          const dbReady = await ensureDatabaseInitialized(); // This has retries

          if (dbReady) {
            console.log("App.tsx: Database initialization successful.");
            setFirstLaunchDbCheckPending(false); // Clear the flag, init is done for this session
          } else {
            console.error("App.tsx: Database initialization failed after retries.");
            // The alert is already in ensureDatabaseInitialized, but we set error for UI
            setDbInitializationError("数据库关键初始化失败。请检查后台服务并尝试重启应用。");
            setIsDbInitializing(false); // Stop loading
            return; // Stop further sequence
          }
        }
      } catch (error) {
        console.error("App.tsx: Error during API availability check:", error);
        const errorMessage = `API服务不可用: ${error instanceof Error ? error.message : String(error)}`;
        
        if (isFirstLaunchDbCheckPending) {
          setDbInitializationError(errorMessage);
        } else {
          // 非首次启动也需要显示关键错误，并阻止进入主界面
          setDbInitializationError(errorMessage);
          toast.error("API服务不可用，应用无法正常工作。请尝试重启应用。");
        }
        
        // 无论是否首次启动，都将API服务标记为未启动
        setApiServiceStarted(false);
      } finally {
        if (isFirstLaunchDbCheckPending) { // Only manage this loading state if it was a first launch init
          setIsDbInitializing(false); // Stop full-screen loading
        }
      }
    };

    startupSequence();
  }, []); // Run once on mount, reads initial state from Zustand

  // WebSocket connection effect
  useEffect(() => {
    const canConnectWebSocket = apiServiceStarted && !isDbInitializing && !dbInitializationError;

    if (!canConnectWebSocket) {
      console.log("App.tsx: Conditions not met for WebSocket connection (API started:", apiServiceStarted, ", DB initializing:", isDbInitializing, ", DB error:", dbInitializationError,")");
      return;
    }

    console.log("App.tsx: Conditions met. Attempting to connect WebSocket.");
    let wsInstance: WebSocket | null = null;
    
    const connectWebSocket = () => {
      if (wsInstance) {
        wsInstance.onclose = null; 
        wsInstance.close();
      }
      wsInstance = new WebSocket("ws://127.0.0.1:60000/ws");
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
  }, [apiServiceStarted, isDbInitializing, dbInitializationError]); // Re-evaluate when these conditions change


  // Conditional Rendering based on initialization state
  if (isDbInitializing) { // This is true only during first launch's DB init phase
    return (
      <div className="flex items-center justify-center h-screen w-screen bg-background text-foreground">
        <div className="text-center">
          {/* You can add a spinner icon here */}
          <p className="text-xl font-semibold animate-pulse">正在为首次使用准备应用...</p>
          <p className="text-muted-foreground">请稍候，正在初始化数据。</p>
        </div>
      </div>
    );
  }

  if (dbInitializationError) { // This error is critical from first launch
    return (
      <div className="flex flex-col items-center justify-center h-screen w-screen bg-background text-foreground p-4">
        <div className="text-center bg-card p-8 rounded-lg shadow-lg border border-destructive">
          <h2 className="text-2xl font-bold text-destructive mb-4">应用初始化失败</h2>
          <p className="text-card-foreground mb-6">{dbInitializationError}</p>
          <Button onClick={() => window.location.reload()} className="bg-primary hover:bg-primary/90 text-primary-foreground">
            重新加载应用
          </Button>
        </div>
      </div>
    );
  }


  // 根据currentPage返回对应的组件
  const renderContent = () => {
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
      default:
        return <HomeKnowledgeBase />;
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
        <Toaster />
      </SidebarInset>
    </SidebarProvider>
  )
}
