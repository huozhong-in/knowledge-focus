import "./index.css";
import { AppSidebar } from "@/components/app-sidebar"
import { useEffect } from "react";
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
import SettingsBackend from "./settings-backend";
import PlaygroundTesting from "./playground-testing";
import { create } from 'zustand';

// 创建一个store来管理页面内容
interface PageState {
  currentPage: string;
  currentTitle: string;
  currentSubtitle: string;
  setPage: (page: string, title: string, subtitle: string) => void;
}

export const usePageStore = create<PageState>((set) => ({
  currentPage: "home",
  currentTitle: "Building Your Application",
  currentSubtitle: "Data Fetching",
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
        const response = await invoke("start_api_service", {
          port: 60000,
          host: "127.0.0.1"
        });
        console.log("API服务已自动启动", response);
      } catch (error) {
        console.error("自动启动API服务失败:", error);
      }
    };

    startApiService();

    // 组件卸载时尝试停止API服务
    return () => {
      invoke("stop_api_service").catch(err => {
        console.error("停止API服务失败:", err);
      });
    };
  }, []); // 空依赖数组确保只在组件挂载时执行一次

  // 根据currentPage返回对应的组件
  const renderContent = () => {
    switch (currentPage) {
      case "settings-backend":
        return <SettingsBackend />;
      case "playground-testing":
        return <PlaygroundTesting />;
      default:
        return (
          <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
            <div className="grid auto-rows-min gap-4 md:grid-cols-3">
              <div className="aspect-video rounded-xl bg-muted/50" />
              <div className="aspect-video rounded-xl bg-muted/50" />
              <div className="aspect-video rounded-xl bg-muted/50" />
            </div>
            <div className="min-h-[100vh] flex-1 rounded-xl bg-muted/50 md:min-h-min" />
          </div>
        );
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
