import React, { useState, useEffect } from "react"
import {
  MessageCircle,
  Plus,
  Search,
  PanelLeftOpenIcon,
  MoreHorizontal,
} from "lucide-react"
import { Button } from "@/components/ui/button"
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
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { UserProfileMenu } from "./UserProfileMenu"
import { ScrollArea } from "@/components/ui/scroll-area"
import { NavTagCloud } from "./nav-tagcloud"
import { ChatSession, getSessions, groupSessionsByTime } from "./lib/chat-session-api"
import { useAppStore } from "./main" // 新增：引入AppStore以获取API就绪状态

interface AppSidebarProps extends React.ComponentProps<typeof Sidebar> {
  currentSessionId?: number
  onSessionSwitch?: (session: ChatSession) => void
  onCreateSession?: () => void // 修改为不接收参数的函数
  refreshTrigger?: number // 新增：刷新触发器，每次数值改变都会刷新列表
}

export function AppSidebar({ currentSessionId, onSessionSwitch, onCreateSession, refreshTrigger, ...props }: AppSidebarProps) {
  const [searchOpen, setSearchOpen] = useState(false)
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const { state, toggleSidebar } = useSidebar()
  const isCollapsed = state === "collapsed"
  
  // 获取全局AppStore实例
  const appStore = useAppStore()

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

    // 将会话按时间分组
  const sessionsByTime = groupSessionsByTime(sessions).map(group => ({
    ...group,
    chat_sessions: group.chat_sessions.map(item => ({
      ...item,
      icon: MessageCircle,
      isActive: item.session.id === currentSessionId
    }))
  }))
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
              title="新对话"
            >
              <Plus className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              title="搜索"
              onClick={() => setSearchOpen(true)}
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
              <span>新对话</span>
            </Button>
            <Button
              variant="ghost"
              className="flex-1"
              size="sm"
              onClick={() => setSearchOpen(true)}
            >
              <Search className="h-4 w-4" />
              <span>搜索对话</span>
            </Button>
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
                      <SidebarMenuItem key={chat_session.id}>
                        <SidebarMenuButton 
                          asChild
                          isActive={chat_session.isActive}
                        >
                          <button
                            onClick={() => handleSessionClick(chat_session.session)}
                            className="flex flex-col items-start h-auto p-1 w-full text-left"
                          >
                            <div className="flex items-center gap-2 w-full">
                              <chat_session.icon className="h-4 w-4 shrink-0" />
                              <span className="font-medium text-sm truncate">
                                {chat_session.title}
                              </span>
                            </div>
                          </button>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    ))}
                  </SidebarMenu>
                </SidebarGroup>
              ))}
              <Button variant="ghost" className="w-full justify-center mb-2" size="sm">
                <MoreHorizontal className="h-4 w-4" />
                <span>More</span>
              </Button>
            </div>
          </ScrollArea>
        )}
      </SidebarContent>

      <SidebarFooter>
        <UserProfileMenu />
      </SidebarFooter>

      {/* Search Dialog */}
      <CommandDialog open={searchOpen} onOpenChange={setSearchOpen}>
        <CommandInput placeholder="搜索任务..." />
        <CommandList>
          <CommandEmpty>未找到任务。</CommandEmpty>
          <CommandGroup heading="任务列表">
            {sessionsByTime.flatMap((timeGroup) =>
              timeGroup.chat_sessions.map((chat_session) => (
                <CommandItem
                  key={chat_session.id}
                  onSelect={() => setSearchOpen(false)}
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
      </CommandDialog>
    </Sidebar>
  )
}
