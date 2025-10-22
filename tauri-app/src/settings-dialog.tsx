import { useState, useEffect } from "react"
import { useSettingsStore, SETTINGS_PAGES } from "./App"
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
import { UpdateBadge } from "@/components/UpdateBadge"
import { useAppStore } from "./main"
import { useTranslation } from "react-i18next"

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
  const { updateAvailable } = useAppStore()
  const { t } = useTranslation()

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
      id: SETTINGS_PAGES.GENERAL,
      label: t('SETTINGS.general.name'),
      icon: Settings,
      group: t('APPSIDEBAR.settings'),
    },
    {
      id: SETTINGS_PAGES.AUTHORIZATION,
      label: t('SETTINGS.authorization.name'),
      icon: Shield,
      group: t('APPSIDEBAR.settings'),
    },
    {
      id: SETTINGS_PAGES.FILE_RECOGNITION,
      label: t('SETTINGS.file-recognition.name'),
      icon: ArrowUpNarrowWide,
      group: t('APPSIDEBAR.settings'),
    },
    {
      id: SETTINGS_PAGES.AI_MODELS,
      label: t('SETTINGS.aimodels.name'),
      icon: Cpu,
      group: t('APPSIDEBAR.settings'),
    },
    {
      id: SETTINGS_PAGES.THEME,
      label: t('SETTINGS.theme.name'),
      icon: Palette,
      group: t('APPSIDEBAR.settings'),
    },
    {
      id: SETTINGS_PAGES.ABOUT,
      label: t('SETTINGS.about.name'),
      icon: Info,
      group: "about",
    },
  ]

  const externalLinks = [
    {
      label: t('SETTINGS.online-documents.name'),
      icon: Globe,
      url: "https://kf.huozhong.in",
      group: "help",
    },
    {
      label: t('SETTINGS.feedback.name'),
      icon: Globe,
      url: "https://github.com/huozhong-in/knowledge-focus/issues",
      group: "help",
    },
    {
      label: t('SETTINGS.privacy-policy.name'),
      icon: Globe,
      url: "https://kf.huozhong.in/privacy-policy",
      group: "help",
    },
    {
      label: t('SETTINGS.terms-of-service.name'),
      icon: Globe,
      url: "https://kf.huozhong.in/terms-of-service",
      group: "help",
    },
  ]

  const renderCurrentPage = () => {
    switch (currentPage) {
      case "general":
        return (
          <div className="p-6">
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-medium">{t('SETTINGS.general.name')}</h3>
                <p className="text-sm text-muted-foreground">
                  {t('SETTINGS.general.description')}
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
                <h3 className="text-lg font-medium">{t('SETTINGS.authorization.name')}</h3>
                <p className="text-sm text-muted-foreground">
                  {t('SETTINGS.authorization.description')}
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
                <h3 className="text-lg font-medium">{t('SETTINGS.file-recognition.name')}</h3>
                <p className="text-sm text-muted-foreground">
                  {t('SETTINGS.file-recognition.description')}
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
                <h3 className="text-lg font-medium">{t('SETTINGS.aimodels.name')}</h3>
                <p className="text-sm text-muted-foreground">
                  {t('SETTINGS.aimodels.description')}
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
                <h3 className="text-lg font-medium">{t('SETTINGS.theme.name')}</h3>
                <p className="text-sm text-muted-foreground">
                  {t('SETTINGS.theme.description')}
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
                <h3 className="text-lg font-medium">{t('SETTINGS.about.name')}</h3>
                <p className="text-sm text-muted-foreground">
                  {t('SETTINGS.about.description')}
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
          className="overflow-hidden p-0 h-[85vh] w-[85vw] max-w-[85vw] flex"
          aria-describedby="settings-description"
        >
          <DialogHeader className="sr-only">
            <DialogTitle>{t('SETTINGS.name')}</DialogTitle>
            <DialogDescription>{t('SETTINGS.description')}</DialogDescription>
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
                              className={page.id === SETTINGS_PAGES.ABOUT ? "relative" : ""}
                            >
                              <page.icon className="h-4 w-4" />
                              <span>{page.label}</span>
                              {/* 在about项上显示更新红点 */}
                              {page.id === SETTINGS_PAGES.ABOUT && updateAvailable && (
                                <UpdateBadge />
                              )}
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
