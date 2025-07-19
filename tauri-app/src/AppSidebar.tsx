import React from "react";
import { MessageCircle, Plus, Hash, Search, PanelLeftOpenIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
} from "@/components/ui/sidebar";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { UserProfileMenu } from "./UserProfileMenu";
import { CustomScrollbar } from "./CustomScrollbar";

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const [searchOpen, setSearchOpen] = React.useState(false);
  const { state, toggleSidebar } = useSidebar()
  const isCollapsed = state === "collapsed"
  
  // Mock data for tasks organized by time periods
  const mockTasksByTime = [
    {
      period: "Recent",
      tasks: [
        { id: "1", title: "Project Planning Assistant", preview: "AI助手协助项目规划和任务分配...", icon: MessageCircle },
        { id: "2", title: "Code Review Helper", preview: "代码审查辅助工具，提高代码质量...", icon: MessageCircle },
        { id: "3", title: "Bug Analysis Chat", preview: "智能分析和诊断系统问题...", icon: MessageCircle },
      ]
    },
    {
      period: "Previous 7 Days",
      tasks: [
        { id: "4", title: "API Design Discussion", preview: "API接口设计讨论和优化建议...", icon: MessageCircle },
        { id: "5", title: "Database Schema Planning", preview: "数据库架构设计和表结构规划...", icon: MessageCircle },
      ]
    },
    {
      period: "Previous 30 Days",
      tasks: [
        { id: "6", title: "Architecture Overview", preview: "系统架构概览和技术选型讨论...", icon: MessageCircle },
        { id: "7", title: "Performance Optimization", preview: "性能优化分析和改进建议...", icon: MessageCircle },
      ]
    },
    {
      period: "Previous Years",
      tasks: [
        { id: "8", title: "Initial Project Setup", preview: "项目初始化配置和环境搭建...", icon: MessageCircle },
        { id: "9", title: "Requirements Analysis", preview: "需求分析和功能规格定义...", icon: MessageCircle },
      ]
    }
  ];

  // Mock data for tags
  const mockTags = [
    "数据分析", "文档处理", "知识管理", "AI助手", "自动化", "报告生成"
  ];

  return (
    <Sidebar collapsible="icon" {...props} className="h-full">
      
        <SidebarHeader>
          <div className="flex items-center gap-2 mt-6">
            <div className="flex aspect-square size-8 items-center justify-center rounded-lg">
              <div className="relative">
                <img 
                  src="/kf-logo.png" 
                  className={`w-8 h-8 object-contain transition-opacity duration-200 ${isCollapsed ? "cursor-pointer hover:opacity-60" : ""}`} 
                />
                {isCollapsed && 
                    <div 
                    className="absolute inset-0 flex items-center justify-center opacity-0 hover:opacity-100 cursor-pointer bg-primary bg-opacity-0 hover:bg-opacity-90 rounded-md transition-all duration-200 backdrop-blur-sm" 
                    onClick={toggleSidebar}
                    >
                    <PanelLeftOpenIcon className="h-6 w-6 text-primary-foreground drop-shadow-lg" />
                    </div>
                }
              </div>
            </div>
            {!isCollapsed && (
              <>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">Knowledge focus</span>
                </div>
                <div>
                  <SidebarTrigger className="-ml-1" />
                </div>
              </>
            )}
          </div>

          {/* Tag Cloud - only show when not collapsed */}
          {!isCollapsed && (
            <div className="space-y-2 px-2 py-2">
              <h3 className="text-sm font-medium text-muted-foreground">文件标签云</h3>
              <div className="flex flex-wrap gap-1">
                {mockTags.map((tag) => (
                  <Badge key={tag} variant="secondary" className="text-xs">
                    <Hash className="h-3 w-3 mr-1" />
                    {tag}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          
          {/* Buttons - different layout for collapsed/expanded */}
          {isCollapsed ? (
            // Collapsed state - only icons vertically stacked
            <div className="flex flex-col gap-2 p-2 items-center">
              <Button
                variant="default"
                size="icon"
                className="h-8 w-8"
                title="新数据任务"
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
              >
                <Plus className="h-4 w-4" />
                <span>新数据任务</span>
              </Button>
              <Button
                variant="ghost"
                className="flex-1"
                size="sm"
                onClick={() => setSearchOpen(true)}
              >
                <Search className="h-4 w-4" />
                <span>搜索</span>
              </Button>
            </div>
          )}
        </SidebarHeader>

        <SidebarContent className="h-full">
          {!isCollapsed && (
            <CustomScrollbar>
              <div className="space-y-1">
                {mockTasksByTime.map((timeGroup) => (
                  <SidebarGroup key={timeGroup.period}>
                    <SidebarGroupLabel>{timeGroup.period}</SidebarGroupLabel>
                    <SidebarMenu>
                      {timeGroup.tasks.map((task) => (
                        <SidebarMenuItem key={task.id}>
                          <SidebarMenuButton asChild>
                            <a href="#" className="flex flex-col items-start h-auto p-1">
                              <div className="flex items-center gap-2 w-full">
                                <task.icon className="h-4 w-4 flex-shrink-0" />
                                <span className="font-medium text-sm truncate">{task.title}</span>
                              </div>
                              {/* <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                                {task.preview}
                              </p> */}
                            </a>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      ))}
                    </SidebarMenu>
                  </SidebarGroup>
                ))}
              </div>
            </CustomScrollbar>
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
            {mockTasksByTime.flatMap(timeGroup => 
              timeGroup.tasks.map((task) => (
                <CommandItem key={task.id} onSelect={() => setSearchOpen(false)}>
                  <task.icon className="mr-2 h-4 w-4" />
                  <div className="flex flex-col">
                    <span className="font-medium">{task.title}</span>
                    <span className="text-xs text-muted-foreground">{task.preview}</span>
                  </div>
                </CommandItem>
              ))
            )}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </Sidebar>
  );
}
