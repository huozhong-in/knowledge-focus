import React from "react"
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

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const [searchOpen, setSearchOpen] = React.useState(false)
  const { state, toggleSidebar } = useSidebar()
  const isCollapsed = state === "collapsed"

  // Mock data for tasks organized by time periods
  const mockTasksByTime = [
    {
      period: "Recent",
      tasks: [
        {
          id: "1",
          title: "Project Planning Assistant",
          icon: MessageCircle,
        },
        {
          id: "2",
          title: "Code Review Helper",
          icon: MessageCircle,
        },
        {
          id: "3",
          title: "Bug Analysis Chat",
          icon: MessageCircle,
        },
      ],
    },
    {
      period: "Previous 7 Days",
      tasks: [
        {
          id: "4",
          title: "API Design Discussion",
          icon: MessageCircle,
        },
        {
          id: "5",
          title: "Database Schema Planning",
          icon: MessageCircle,
        },
      ],
    },
    {
      period: "Previous 30 Days",
      tasks: [
        {
          id: "6",
          title: "Architecture Overview",
          icon: MessageCircle,
        },
        {
          id: "7",
          title: "Performance Optimization",
          icon: MessageCircle,
        },
      ],
    },
    {
      period: "Previous Years",
      tasks: [
        {
          id: "8",
          title: "Initial Project Setup",
          icon: MessageCircle,
        },
        {
          id: "9",
          title: "Requirements Analysis",
          icon: MessageCircle,
        },
      ],
    },
  ]

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
                <span className="truncate font-semibold">Knowledge focus</span>
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
            <Button variant="default" className="flex-1 gap-2" size="sm">
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
          <ScrollArea className="h-full">
            <div className="space-y-1">
              {mockTasksByTime.map((timeGroup) => (
                <SidebarGroup key={timeGroup.period}>
                  <SidebarGroupLabel>{timeGroup.period}</SidebarGroupLabel>
                  <SidebarMenu>
                    {timeGroup.tasks.map((task) => (
                      <SidebarMenuItem key={task.id}>
                        <SidebarMenuButton asChild>
                          <a
                            href="#"
                            className="flex flex-col items-start h-auto p-1"
                          >
                            <div className="flex items-center gap-2 w-full">
                              <task.icon className="h-4 w-4 flex-shrink-0" />
                              <span className="font-medium text-sm truncate">
                                {task.title}
                              </span>
                            </div>
                          </a>
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
            {mockTasksByTime.flatMap((timeGroup) =>
              timeGroup.tasks.map((task) => (
                <CommandItem
                  key={task.id}
                  onSelect={() => setSearchOpen(false)}
                >
                  <task.icon className="mr-2 h-4 w-4" />
                  <div className="flex flex-col">
                    <span className="font-medium">{task.title}</span>
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
