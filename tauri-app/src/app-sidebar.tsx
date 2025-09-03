import React, { useState, useEffect } from "react"
import {
  MessageCircle,
  Plus,
  Search,
  PanelLeftOpenIcon,
  MoreHorizontal,
  Edit3,
  Trash2,
  EllipsisVertical,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
  SidebarGroup,
  SidebarGroupLabel,
} from "@/components/ui/sidebar"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { UserProfileMenu } from "./user-profile-menu"
import { ScrollArea } from "@/components/ui/scroll-area"
import { NavTagCloud } from "./nav-tagcloud"
import { ChatSession, getSessions, groupSessionsByTime } from "./lib/chat-session-api"
import { UpdateBadge } from "@/components/UpdateBadge"
import { useUpdater } from "@/hooks/useUpdater"
import { useAppStore } from "./main"
import { AnimatedSessionTitle } from "./components/animated-session-title"
import { useTranslation } from "react-i18next"

interface AppSidebarProps extends React.ComponentProps<typeof Sidebar> {
  currentSessionId?: number
  onSessionSwitch?: (session: ChatSession | null) => void
  onCreateSession?: () => void // 修改为不接收参数的函数
  refreshTrigger?: number // 刷新触发器，每次数值改变都会刷新列表
  newlyGeneratedSessionId?: number | null // 新生成的会话ID，用于显示动画
  onTitleAnimationComplete?: (sessionId: number) => void // 动画完成回调
  onRenameSession?: (sessionId: number, newName: string) => void // 重命名会话回调
  onDeleteSession?: (sessionId: number) => void // 删除会话回调
  searchOpen?: boolean // 外部控制搜索对话框状态
  onSearchOpenChange?: (open: boolean) => void // 外部搜索状态变化回调
}

export function AppSidebar({ 
  currentSessionId, 
  onSessionSwitch, 
  onCreateSession, 
  refreshTrigger, 
  newlyGeneratedSessionId, 
  onTitleAnimationComplete, 
  onRenameSession, 
  onDeleteSession,
  searchOpen: externalSearchOpen,
  onSearchOpenChange,
  ...props 
}: AppSidebarProps) {
  const [searchOpen, setSearchOpen] = useState(false)
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [searchQuery, setSearchQuery] = useState("")
  const { state, toggleSidebar } = useSidebar()
  const isCollapsed = state === "collapsed"
  
  // 初始化更新检查器
  useUpdater()
  
  // 实际的搜索状态，优先使用外部传入的状态
  const actualSearchOpen = externalSearchOpen !== undefined ? externalSearchOpen : searchOpen
  
  // 搜索状态变化处理
  const handleSearchOpenChange = (open: boolean) => {
    if (onSearchOpenChange) {
      onSearchOpenChange(open)
    } else {
      setSearchOpen(open)
    }
    if (!open) {
      setSearchQuery("")
    }
  }
  
  // Dialog 状态管理
  const [renameDialogOpen, setRenameDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [selectedSession, setSelectedSession] = useState<{id: number, name: string} | null>(null)
  const [newSessionName, setNewSessionName] = useState("")
  
  // 获取全局AppStore实例
  const appStore = useAppStore()
  const { t } = useTranslation()

  // 加载会话列表
  const loadSessions = async (search?: string) => {
    try {
      const result = await getSessions(1, 50, search) // 获取前50个会话
      setSessions(result.sessions)
    } catch (error) {
      console.error('Failed to load sessions:', error)
    }
  }

  // 组件挂载时加载会话列表 - 等待API就绪
  useEffect(() => {
    console.log('📋 AppSidebar 组件已挂载, API状态:', appStore.isApiReady, '时间:', new Date().toLocaleTimeString());
    
    // 如果 API 已就绪，立即尝试获取会话列表
    if (appStore.isApiReady) {
      console.log('🚀 组件挂载时尝试获取会话列表');
      loadSessions();
    }
  }, []) // 只在首次挂载时执行

  // 监听API就绪状态变化
  useEffect(() => {
    if (appStore.isApiReady) {
      console.log('🔗 API就绪，尝试获取会话列表');
      loadSessions();
    }
  }, [appStore.isApiReady])

  // 监听刷新触发器变化
  useEffect(() => {
    if (refreshTrigger !== undefined && appStore.isApiReady) {
      console.log('🔄 收到刷新触发器，重新获取会话列表, trigger:', refreshTrigger);
      loadSessions();
    }
  }, [refreshTrigger, appStore.isApiReady])

  // 创建新会话准备
  const handleCreateSession = () => {
    try {
      // 不再立即创建会话，只是通知父组件准备新会话状态
      onCreateSession?.()
    } catch (error) {
      console.error('Failed to prepare new session:', error)
    }
  }

  // 会话点击处理
  const handleSessionClick = (session: ChatSession) => {
    onSessionSwitch?.(session)
  }

  // 重命名会话处理
  const handleRenameSession = async (sessionId: number, currentName: string) => {
    setSelectedSession({id: sessionId, name: currentName})
    setNewSessionName(currentName)
    setRenameDialogOpen(true)
  }

  // 确认重命名
  const confirmRename = async () => {
    if (selectedSession && newSessionName.trim() && newSessionName !== selectedSession.name) {
      try {
        onRenameSession?.(selectedSession.id, newSessionName.trim())
        // 刷新会话列表
        await loadSessions()
      } catch (error) {
        console.error('Failed to rename session:', error)
      }
    }
    setRenameDialogOpen(false)
    setSelectedSession(null)
    setNewSessionName("")
  }

  // 删除会话处理
  const handleDeleteSession = async (sessionId: number, sessionTitle: string) => {
    setSelectedSession({id: sessionId, name: sessionTitle})
    setDeleteDialogOpen(true)
  }

  // 确认删除
  const confirmDelete = async () => {
    if (selectedSession) {
      try {
        onDeleteSession?.(selectedSession.id)
        // 如果是当前会话，切换到默认会话
        if (selectedSession.id === currentSessionId) {
          onSessionSwitch?.(null)
        }
        // 刷新会话列表
        await loadSessions()
      } catch (error) {
        console.error('Failed to delete session:', error)
      }
    }
    setDeleteDialogOpen(false)
    setSelectedSession(null)
  }

    // 将会话按时间分组
  const sessionsByTime = groupSessionsByTime(sessions).map(group => ({
    ...group,
    chat_sessions: group.chat_sessions.map(item => ({
      ...item,
      icon: MessageCircle,
      isActive: item.session.id === currentSessionId
    }))
  }))

  // 过滤搜索结果
  const filteredSessionsByTime = searchQuery 
    ? sessionsByTime.map(group => ({
        ...group,
        chat_sessions: group.chat_sessions.filter(session =>
          session.title.toLowerCase().includes(searchQuery.toLowerCase())
        )
      })).filter(group => group.chat_sessions.length > 0)
    : sessionsByTime
  return (
    <Sidebar variant="sidebar" collapsible="icon" {...props} className="h-full">
      <SidebarHeader>
        <div className="flex items-center gap-2 mt-5">
          <div className="flex aspect-square size-8 items-center justify-center rounded-lg">
            <div className="relative">
              <img
                src="/kf-logo.png"
                className={`w-8 h-8 object-contain transition-opacity duration-200 ${
                  isCollapsed ? "cursor-pointer hover:opacity-60" : ""
                }`}
              />
              {/* 更新提示红点 */}
              <UpdateBadge />
              {isCollapsed && (
                <div
                  className="absolute inset-0 flex items-center justify-center opacity-0 hover:opacity-100 cursor-pointer bg-primary bg-opacity-0 hover:bg-opacity-90 rounded-md transition-all duration-200 backdrop-blur-sm"
                  onClick={toggleSidebar}
                >
                  <PanelLeftOpenIcon className="h-6 w-6 text-primary-foreground drop-shadow-lg" />
                </div>
              )}
            </div>
          </div>
          {!isCollapsed && (
            <>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">KnowledgeFocus</span>
              </div>
              <div>
                <SidebarTrigger className="-ml-1" />
              </div>
            </>
          )}
        </div>

        {/* Tag Cloud - always render but hide when collapsed */}
        <div className={isCollapsed ? "hidden" : "block"}>
          <NavTagCloud />
        </div>

        {/* Buttons - different layout for collapsed/expanded */}
        {isCollapsed ? (
          // Collapsed state - only icons vertically stacked
          <div className="flex flex-col gap-2 p-2 items-center">
            <Button
              variant="default"
              size="icon"
              className="h-8 w-8"
              onClick={handleCreateSession}
              title="{t('APPSIDEBAR.new-chat')}"
            >
              <Plus className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              title={`${t('APPSIDEBAR.search-chat')} (⌘P)`}
              onClick={() => handleSearchOpenChange(true)}
            >
              <Search className="h-4 w-4" />
            </Button>
          </div>
        ) : (
          // Expanded state - full buttons horizontally
          <div className="flex gap-2 p-2 justify-between">
            <Button 
              variant="default" 
              className="flex-1 gap-2" 
              size="sm"
              onClick={handleCreateSession}
            >
              <Plus className="h-4 w-4" />
              <span>{t('APPSIDEBAR.new-chat')}</span>
            </Button>
            <div
              className="flex-1 flex items-center rounded-md border border-input bg-background px-2 text-xs ring-offset-background hover:bg-accent hover:text-accent-foreground cursor-pointer transition-colors h-8"
              onClick={() => handleSearchOpenChange(true)}
            >
              <Search className="h-4 w-4 shrink-0" />
              <div className="grid flex-1 text-left leading-tight">
                <span className="truncate text-[9px]">{t('APPSIDEBAR.search-chat')}</span>
                <span className="truncate text-[9px] text-muted-foreground justify-self-end">Press{" "}
                  <kbd className="bg-muted text-muted-foreground pointer-events-none inline-flex h-4 items-center gap-1 rounded border px-1 font-mono text-[9px] font-medium opacity-100 select-none">
                    <span className="text-[9px]">⌘ P</span>
                  </kbd>
                </span>
              </div>
            </div>
          </div>
        )}
      </SidebarHeader>

      <SidebarContent className="h-full">
        {!isCollapsed && (
          <ScrollArea className="h-full">
            <div className="space-y-1">
              {sessionsByTime.map((timeGroup) => (
                <SidebarGroup key={timeGroup.period}>
                  <SidebarGroupLabel>{timeGroup.period}</SidebarGroupLabel>
                  <SidebarMenu>
                    {timeGroup.chat_sessions.map((chat_session) => (
                      <SidebarMenuItem key={chat_session.id} className={`group`}>
                        <SidebarMenuButton 
                          asChild
                          isActive={chat_session.isActive}
                          onClick={() => handleSessionClick(chat_session.session)}
                          className={`flex items-start h-auto p-1 w-[220px] text-left ${currentSessionId === parseInt(chat_session.id) ? 'bg-sidebar-accent' : ''}`}
                          >
                            <div className="flex flex-row items-center gap-2 w-[220px]">
                              <chat_session.icon className="h-4 w-4 shrink-0" />
                              <AnimatedSessionTitle
                                title={chat_session.title}
                                isNewlyGenerated={newlyGeneratedSessionId === parseInt(chat_session.id)}
                                className="font-medium text-sm truncate cursor-default"
                                onAnimationComplete={() => onTitleAnimationComplete?.(parseInt(chat_session.id))}
                              />
                            </div>
                        </SidebarMenuButton>
                        {/* 浮动工具条 - hover时显示 */}
                        <div key={chat_session.id} className={`absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex gap-0.5`}>
                          <DropdownMenu key={chat_session.id}>
                            <DropdownMenuTrigger>
                              <EllipsisVertical className="h-4 w-4 hover:bg-accent" />
                            </DropdownMenuTrigger>
                            <DropdownMenuContent>
                              <DropdownMenuItem
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRenameSession(parseInt(chat_session.id), chat_session.title);
                                }}
                                className="flex items-center"
                              >
                                <Edit3 className="mr-1 h-4 w-4" />
                                <span className="text-xs">{t('APPSIDEBAR.rename-chat')}</span>
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeleteSession(parseInt(chat_session.id), chat_session.title);
                                }}
                                className="flex items-center"
                              >
                                <Trash2 className="mr-1 h-4 w-4" />
                                <span className="text-xs">{t('APPSIDEBAR.delete-chat')}</span>
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </SidebarMenuItem>
                    ))}
                  </SidebarMenu>
                </SidebarGroup>
              ))}
              <Button variant="ghost" className="w-full justify-center mb-2" size="sm">
                <span className="text-xs">{t('APPSIDEBAR.more')}</span>
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </div>
          </ScrollArea>
        )}
      </SidebarContent>

      <SidebarFooter>
        <UserProfileMenu />
      </SidebarFooter>

      {/* Search Dialog */}
      <Dialog 
        open={actualSearchOpen} 
        onOpenChange={handleSearchOpenChange}
      >
        <DialogContent className="search-command-dialog max-w-2xl">
          <DialogHeader className="sr-only">
            <DialogTitle>{t('APPSIDEBAR.search-chat')}</DialogTitle>
            <DialogDescription>{t('APPSIDEBAR.search')}</DialogDescription>
          </DialogHeader>
          <Command className="[&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group]]:px-2 [&_[cmdk-group]:not([hidden])_~[cmdk-group]]:pt-0 [&_[cmdk-input-wrapper]_svg]:h-5 [&_[cmdk-input-wrapper]_svg]:w-5 [&_[cmdk-input]]:h-12 [&_[cmdk-item]]:px-2 [&_[cmdk-item]]:py-3 [&_[cmdk-item]_svg]:h-5 [&_[cmdk-item]_svg]:w-5">
            <CommandInput 
              placeholder={t('APPSIDEBAR.search')} 
              value={searchQuery}
              onValueChange={setSearchQuery}
            />
            <CommandList>
              <CommandEmpty>{t('APPSIDEBAR.chat-not-found')}</CommandEmpty>
              <CommandGroup heading={t('APPSIDEBAR.chat-list')}>
                {filteredSessionsByTime.flatMap((timeGroup) =>
                  timeGroup.chat_sessions.map((chat_session) => (
                    <CommandItem
                      key={chat_session.id}
                      onSelect={() => {
                        handleSessionClick(chat_session.session)
                        handleSearchOpenChange(false)
                        setSearchQuery("")
                      }}
                    >
                      <chat_session.icon className="mr-2 h-4 w-4" />
                      <div className="flex flex-col">
                        <span className="font-medium">{chat_session.title}</span>
                      </div>
                    </CommandItem>
                  ))
                )}
              </CommandGroup>
            </CommandList>
          </Command>
        </DialogContent>
      </Dialog>
      
      {/* 重命名会话Dialog */}
      <Dialog open={renameDialogOpen} onOpenChange={setRenameDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('APPSIDEBAR.rename-chat')}</DialogTitle>
            <DialogDescription>
              {t('APPSIDEBAR.enter-new-chat-name')}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <Input
              value={newSessionName}
              onChange={(e) => setNewSessionName(e.target.value)}
              placeholder={t('APPSIDEBAR.chat-name')}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  confirmRename()
                }
              }}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setRenameDialogOpen(false)}>
              {t('APPSIDEBAR.cancel')}
            </Button>
            <Button onClick={confirmRename} disabled={!newSessionName.trim()}>
              {t('APPSIDEBAR.confirm')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* 删除会话确认Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('APPSIDEBAR.delete-chat')}</DialogTitle>
            <DialogDescription>
              {t('APPSIDEBAR.confirm-delete-chat', { chatName: selectedSession?.name })}
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              {t('APPSIDEBAR.cancel')}
            </Button>
            <Button variant="destructive" onClick={confirmDelete}>
              {t('APPSIDEBAR.confirm')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Sidebar>
  )
}
