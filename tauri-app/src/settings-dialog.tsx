import { useState, useEffect } from "react"
import { useSettingsStore } from "./App"
import { 
  // openPath, 
  openUrl,
} from "@tauri-apps/plugin-opener"
import {
  Settings,
  Cpu,
  Globe,
  Info,
  Palette,
  Shield,
  ArrowUpNarrowWide,
} from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

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
  // SidebarHeader,
} from "@/components/ui/sidebar"
import { ScrollArea } from "./components/ui/scroll-area"
import SettingsGeneral from "./settings-general"
import SettingsAuthorization from "./settings-authorization"
import SettingsFileRecognition from "./settings-file-recognition"
import SettingsAIModels from "./settings-ai-models"
import SettingsTheme from "./settings-theme-content"
import SettingsAbout from "./settings-about"

type SettingsPage =
  | "general"
  | "authorization"
  | "file_recognition"
  | "aimodels"
  | "theme"
  | "about"

interface SettingsDialogProps {
  children?: React.ReactNode
}

export function SettingsDialog({ children }: SettingsDialogProps) {
  const { isSettingsOpen, setSettingsOpen, initialPage, setInitialPage } = useSettingsStore()
  const [currentPage, setCurrentPage] = useState<SettingsPage>("general")

  // 当对话框打开时，设置初始页面
  useEffect(() => {
    if (isSettingsOpen && initialPage) {
      setCurrentPage(initialPage as SettingsPage)
    }
  }, [isSettingsOpen, initialPage])

  // 当对话框关闭时，重置初始页面
  useEffect(() => {
    if (!isSettingsOpen) {
      setInitialPage("general")
    }
  }, [isSettingsOpen, setInitialPage])

  const handleExternalLink = async (url: string) => {
    try {
      await openUrl(url)
    } catch (error) {
      console.error("Failed to open external link:", error)
      // 可以添加toast通知用户
    }
  }

  const handlePageChange = (page: SettingsPage) => {
    try {
      setCurrentPage(page)
    } catch (error) {
      console.error("Failed to change page:", error)
    }
  }

  const settingsPages = [
    {
      id: "general" as const,
      label: "基本设置",
      icon: Settings,
      group: "应用设置",
    },
    {
      id: "authorization" as const,
      label: "授权管理",
      icon: Shield,
      group: "应用设置",
    },
    {
      id: "file_recognition" as const,
      label: "文件识别规则",
      icon: ArrowUpNarrowWide,
      group: "应用设置",
    },
    {
      id: "aimodels" as const,
      label: "AI模型和场景配置",
      icon: Cpu,
      group: "应用设置",
    },
    {
      id: "theme" as const,
      label: "主题设置",
      icon: Palette,
      group: "应用设置",
    },
    {
      id: "about" as const,
      label: "关于应用",
      icon: Info,
      group: "关于",
    },
  ]

  const externalLinks = [
    {
      label: "在线文档",
      icon: Globe,
      url: "https://knowledge-focus.huozhong.in",
      group: "帮助",
    },
    {
      label: "反馈建议",
      icon: Globe,
      url: "https://github.com/huozhong-in/knowledge-focus/issues",
      group: "帮助",
    },
  ]

  const renderCurrentPage = () => {
    switch (currentPage) {
      case "general":
        return (
          <div className="p-6">
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-medium">通用设置</h3>
                <p className="text-sm text-muted-foreground">
                  配置应用的基本选项
                </p>
              </div>
              <SettingsGeneral />
            </div>
          </div>
        )
      case "authorization":
        return (
          <div className="p-6">
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-medium">授权管理</h3>
                <p className="text-sm text-muted-foreground">
                  管理文件访问权限和授权设置
                </p>
              </div>
              <SettingsAuthorization />
            </div>
          </div>
        )
      case "file_recognition":
        return (
          <div className="p-6">
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-medium">文件识别规则</h3>
                <p className="text-sm text-muted-foreground">
                  配置识别携带有知识的文件的规则
                </p>
              </div>
              <SettingsFileRecognition />
            </div>
          </div>
        )
      case "aimodels":
        return (
          <div className="p-6">
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-medium">AI模型和角色配置</h3>
                <p className="text-sm text-muted-foreground">
                  配置AI 模型
                </p>
              </div>
              <SettingsAIModels />
            </div>
          </div>
        )
      case "theme":
        return (
          <div className="p-6">
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-medium">主题设置</h3>
                <p className="text-sm text-muted-foreground">
                  自定义应用外观和主题
                </p>
              </div>
              <SettingsTheme />
            </div>
          </div>
        )
      case "about":
        return (
          <div className="p-6">
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-medium">关于应用</h3>
                <p className="text-sm text-muted-foreground">
                  应用信息和版本详情
                </p>
              </div>
              <SettingsAbout />
            </div>
          </div>
        )
      default:
        return null
    }
  }

  // 按组分组设置页面
  const groupedSettings = settingsPages.reduce((acc, page) => {
    if (!acc[page.group]) {
      acc[page.group] = []
    }
    acc[page.group].push(page)
    return acc
  }, {} as Record<string, typeof settingsPages>)

  // 按组分组外部链接
  const groupedLinks = externalLinks.reduce((acc, link) => {
    if (!acc[link.group]) {
      acc[link.group] = []
    }
    acc[link.group].push(link)
    return acc
  }, {} as Record<string, typeof externalLinks>)

  return (
      <Dialog open={isSettingsOpen} onOpenChange={setSettingsOpen}>
        {/* 触发器 */}
        {children && <div onClick={() => setSettingsOpen(true)}>{children}</div>}

        <DialogContent
          className="overflow-hidden p-0 h-[85vh] w-[85vw] flex"
          aria-describedby="settings-description"
          showCloseButton={true}
        >
          <DialogHeader className="sr-only">
            <DialogTitle>应用设置</DialogTitle>
            <DialogDescription>管理应用的各项配置设置</DialogDescription>
          </DialogHeader>
          <SidebarProvider className="items-start">
            {/* 左侧导航 */}
            <Sidebar collapsible="none" 
              className="w-64 border-r shrink-0 hidden md:flex"
              >
              {/* <SidebarHeader>
                <div className="p-4">
                  <h2 className="text-lg font-semibold">应用设置</h2>
                  <p className="text-sm text-muted-foreground">管理应用配置</p>
                </div>
              </SidebarHeader> */}
              <SidebarContent>
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
            <main className="flex h-[85vh] flex-1 flex-col overflow-hidden">
              <div className="flex flex-1 flex-col overflow-y-auto pt-0">
                <ScrollArea className="h-full">
                  {renderCurrentPage()}
                </ScrollArea>
              </div>
            </main>
          </SidebarProvider>
        </DialogContent>
      </Dialog>
  )
}
