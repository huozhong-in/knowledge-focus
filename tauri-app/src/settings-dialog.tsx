import { useState, useCallback } from "react";
import { openPath } from '@tauri-apps/plugin-opener';
import { 
  Settings, 
  Cpu, 
  Globe, 
  Info, 
  Palette,
  Shield,
  Network
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
} from "@/components/ui/sidebar";

import SettingsAuthorization from "./settings-authorization";
import SettingsLocalModels from "./settings-local-models";
import SettingsGeneral from "./settings-general";
import SettingsBusinessApis from "./settings-business-apis";
import SettingsAbout from "./settings-about";
import SettingsTheme from "./settings-theme-content";

type SettingsPage = 
  | "general" 
  | "theme" 
  | "authorization" 
  | "local-models" 
  | "business-apis" 
  | "about";

interface SettingsDialogProps {
  children: React.ReactNode;
}

export function SettingsDialog({ children }: SettingsDialogProps) {
  const [open, setOpen] = useState(false);
  const [currentPage, setCurrentPage] = useState<SettingsPage>("general");

  const handleExternalLink = async (url: string) => {
    try {
      await openPath(url);
    } catch (error) {
      console.error("Failed to open external link:", error);
      // 可以添加toast通知用户
    }
  };

  const handlePageChange = (page: SettingsPage) => {
    try {
      setCurrentPage(page);
    } catch (error) {
      console.error("Failed to change page:", error);
    }
  };

  const settingsPages = [
    {
      id: "general" as const,
      label: "通用设置",
      icon: Settings,
      group: "应用设置"
    },
    {
      id: "theme" as const,
      label: "主题设置", 
      icon: Palette,
      group: "应用设置"
    },
    {
      id: "authorization" as const,
      label: "授权管理",
      icon: Shield,
      group: "应用设置"
    },
    {
      id: "local-models" as const,
      label: "本地模型",
      icon: Cpu,
      group: "AI 模型"
    },
    {
      id: "business-apis" as const,
      label: "在线模型",
      icon: Network,
      group: "AI 模型"
    },
    {
      id: "about" as const,
      label: "关于应用",
      icon: Info,
      group: "关于"
    }
  ];

  const externalLinks = [
    {
      label: "在线文档",
      icon: Globe,
      url: "https://knowledge-focus.huozhong.in",
      group: "帮助"
    },
    {
      label: "反馈建议",
      icon: Globe,
      url: "https://github.com/huozhong-in/knowledge-focus/issues",
      group: "帮助"
    }
  ];

  const renderCurrentPage = () => {
    switch (currentPage) {
      case "general":
        return (
          <div className="p-6">
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-medium">通用设置</h3>
                <p className="text-sm text-muted-foreground">配置应用的基本选项</p>
              </div>
              <SettingsGeneral />
            </div>
          </div>
        );
      case "theme":
        return (
          <div className="p-6">
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-medium">主题设置</h3>
                <p className="text-sm text-muted-foreground">自定义应用外观和主题</p>
              </div>
              <SettingsTheme />
            </div>
          </div>
        );
      case "authorization":
        return (
          <div className="p-6">
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-medium">授权管理</h3>
                <p className="text-sm text-muted-foreground">管理文件访问权限和授权设置</p>
              </div>
              <SettingsAuthorization />
            </div>
          </div>
        );
      case "local-models":
        return (
          <div className="p-6">
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-medium">本地模型</h3>
                <p className="text-sm text-muted-foreground">配置本地 AI 模型设置</p>
              </div>
              <SettingsLocalModels />
            </div>
          </div>
        );
      case "business-apis":
        return (
          <div className="p-6">
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-medium">在线模型</h3>
                <p className="text-sm text-muted-foreground">配置在线 AI 模型 API</p>
              </div>
              <SettingsBusinessApis />
            </div>
          </div>
        );
      case "about":
        return (
          <div className="p-6">
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-medium">关于应用</h3>
                <p className="text-sm text-muted-foreground">应用信息和版本详情</p>
              </div>
              <SettingsAbout />
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  // 按组分组设置页面
  const groupedSettings = settingsPages.reduce((acc, page) => {
    if (!acc[page.group]) {
      acc[page.group] = [];
    }
    acc[page.group].push(page);
    return acc;
  }, {} as Record<string, typeof settingsPages>);

  // 按组分组外部链接
  const groupedLinks = externalLinks.reduce((acc, link) => {
    if (!acc[link.group]) {
      acc[link.group] = [];
    }
    acc[link.group].push(link);
    return acc;
  }, {} as Record<string, typeof externalLinks>);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogHeader className="sr-only">
        <DialogTitle>应用设置</DialogTitle>
        <DialogDescription>管理应用的各项配置设置</DialogDescription>
      </DialogHeader>
      
      {/* 触发器 */}
      <div onClick={() => setOpen(true)}>
        {children}
      </div>

      <DialogContent 
        className="p-0 w-[85vw] max-w-[1400px] h-[80vh] flex overflow-hidden"
        aria-describedby="settings-description"
        showCloseButton={false}
      >
        <div id="settings-description" className="sr-only">
          管理应用的各项配置设置，包括通用设置、主题、授权管理、AI模型配置等
        </div>
        <SidebarProvider className="min-h-0">
          <div className="flex h-full">
            {/* 左侧导航 */}
            <Sidebar className="w-64 border-r flex-shrink-0 [&_[data-slot=sidebar-container]]:!relative [&_[data-slot=sidebar-container]]:!h-full [&_[data-slot=sidebar-container]]:!inset-y-auto [&_[data-slot=sidebar-container]]:!z-auto [&_[data-slot=sidebar-gap]]:!hidden">
              <SidebarContent>
                <div className="p-4">
                  <h2 className="text-lg font-semibold">应用设置</h2>
                  <p className="text-sm text-muted-foreground">管理应用配置</p>
                </div>
                
                {/* 设置页面 */}
                {Object.entries(groupedSettings).map(([group, pages]) => (
                  <SidebarGroup key={group}>
                    <SidebarGroupLabel>{group}</SidebarGroupLabel>
                    <SidebarGroupContent>
                      <SidebarMenu>
                        {pages.map((page) => (
                          <SidebarMenuItem key={page.id}>
                            <SidebarMenuButton
                              onClick={() => handlePageChange(page.id)}
                              isActive={currentPage === page.id}
                            >
                              <page.icon className="h-4 w-4" />
                              <span>{page.label}</span>
                            </SidebarMenuButton>
                          </SidebarMenuItem>
                        ))}
                      </SidebarMenu>
                    </SidebarGroupContent>
                  </SidebarGroup>
                ))}

                {/* 外部链接 */}
                {Object.entries(groupedLinks).map(([group, links]) => (
                  <SidebarGroup key={group}>
                    <SidebarGroupLabel>{group}</SidebarGroupLabel>
                    <SidebarGroupContent>
                      <SidebarMenu>
                        {links.map((link) => (
                          <SidebarMenuItem key={link.label}>
                            <SidebarMenuButton
                              onClick={() => handleExternalLink(link.url)}
                            >
                              <link.icon className="h-4 w-4" />
                              <span>{link.label}</span>
                            </SidebarMenuButton>
                          </SidebarMenuItem>
                        ))}
                      </SidebarMenu>
                    </SidebarGroupContent>
                  </SidebarGroup>
                ))}
              </SidebarContent>
            </Sidebar>

            {/* 右侧内容区域 */}
            <div className="flex-1 overflow-auto min-w-0 bg-gray-50">
              {renderCurrentPage()}
            </div>
          </div>
        </SidebarProvider>
      </DialogContent>
    </Dialog>
  );
}
