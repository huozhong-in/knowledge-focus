import "./index.css";
import { AppSidebar } from "@/components/app-sidebar"
import { useEffect } from "react";
import { join, appDataDir } from '@tauri-apps/api/path';
import { invoke } from "@tauri-apps/api/core";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Separator } from "@/components/ui/separator"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import HomeDashboard from "./home-dashboard";
import HomeMyFiles from "./home-myfiles";
import HomeInsightCards from "./home-insightcards";
import ModelsLocal from "./models-local";
import ModelsDomestic from "./models-domestic";
import ModelsOverseas from "./models-overseas";
import PromptsLibrary from "./prompts-library";
import SettingsGeneral from "./settings-general";
import SettingsDeveloperZone from "./settings-developerzone";
import { create } from 'zustand';

// 创建一个store来管理页面内容
interface PageState {
  currentPage: string;
  currentTitle: string;
  currentSubtitle: string;
  setPage: (page: string, title: string, subtitle: string) => void;
}

export const usePageStore = create<PageState>((set) => ({
  currentPage: "home-dashboard",
  currentTitle: "Home",
  currentSubtitle: "Dashboard",
  setPage: (page, title, subtitle) => set({ 
    currentPage: page, 
    currentTitle: title,
    currentSubtitle: subtitle 
  }),
}));

export default function Page() {
  const { currentPage, currentTitle, currentSubtitle } = usePageStore();

  // 自动启动API服务
  useEffect(() => {
    const startApiService = async () => {
      try {
        const appDataPath = await appDataDir();
        const dbPath = await join(appDataPath, 'knowledge-focus.db');
        console.log("数据库路径:", dbPath);
        const response = await invoke("start_api_service", {
          port: 60000,
          host: "127.0.0.1",
          db_path: dbPath
        });
        console.log("API服务已自动启动", response);
      } catch (error) {
        console.error("自动启动API服务失败:", error);
      }
    };

    startApiService();

    // 组件卸载时尝试停止API服务
    // return () => {
    //   invoke("stop_api_service").catch(err => {
    //     console.error("停止API服务失败:", err);
    //   });
    // };
  }, []); // 空依赖数组确保只在组件挂载时执行一次

  // 根据currentPage返回对应的组件
  const renderContent = () => {
    switch (currentPage) {
      case "home-dashboard":
        return <HomeDashboard />;
      case "home-insightcards":
        return <HomeInsightCards />;
      case "home-myfiles":
        return <HomeMyFiles />;
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
      case "settings-developerzone":
        return <SettingsDeveloperZone />;
      default:
        return <HomeDashboard />;
    }
  };

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="flex h-16 shrink-0 items-center gap-2 transition-[width,height] ease-linear group-has-[[data-collapsible=icon]]/sidebar-wrapper:h-12">
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
        </header>
        {renderContent()}
      </SidebarInset>
    </SidebarProvider>
  )
}
