"use client"

import {
  BadgeCheck,
  Bell,
  ChevronsUpDown,
  CreditCard,
  LogOut,
  Sparkles,
  CircleUserRound,
} from "lucide-react"

import {
  Avatar,
  AvatarFallback,
  AvatarImage,
} from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"

export function NavUser({
  user,
}: {
  user: {
    name: string
    email: string
    avatar: string
  }
}) {
  const { isMobile } = useSidebar()

  return (
    <SidebarMenu className="px-1">
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              className="hover:bg-whiskey-100 bg-whiskey-50 data-[state=open]:bg-whiskey-200 data-[state=open]:text-whiskey-800"
            >
              <Avatar className="h-8 w-8 rounded-lg border-2 border-whiskey-300">
                <AvatarImage src={user.avatar} alt={user.name} />
                <AvatarFallback className="bg-whiskey-100 text-whiskey-500 rounded-lg"><CircleUserRound /></AvatarFallback>
              </Avatar>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-medium text-whiskey-800">{user.name}</span>
                <span className="truncate text-xs text-whiskey-600">{user.email}</span>
              </div>
              <ChevronsUpDown className="ml-auto size-4 text-whiskey-500" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg border-whiskey-200 bg-whiskey-50"
            side={isMobile ? "bottom" : "right"}
            align="end"
            sideOffset={4}
          >
            <DropdownMenuLabel className="p-0 font-normal">
              <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm bg-whiskey-100 rounded-md m-1">
                <Avatar className="h-8 w-8 rounded-lg border-2 border-whiskey-300">
                  <AvatarImage src={user.avatar} alt={user.name} />
                  <AvatarFallback className="bg-whiskey-50 text-whiskey-500 rounded-lg"><CircleUserRound /></AvatarFallback>
                </Avatar>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-medium text-whiskey-800">{user.name}</span>
                  <span className="truncate text-xs text-whiskey-600">{user.email}</span>
                </div>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-whiskey-200" />
            <DropdownMenuGroup>
              <DropdownMenuItem className="text-whiskey-800 hover:bg-whiskey-100 focus:bg-whiskey-100">
                <Sparkles className="text-whiskey-500" />
                升级到专业版
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator className="bg-whiskey-200" />
            <DropdownMenuGroup>
              <DropdownMenuItem className="text-whiskey-800 hover:bg-whiskey-100 focus:bg-whiskey-100">
                <BadgeCheck className="text-whiskey-500" />
                账户设置
              </DropdownMenuItem>
              <DropdownMenuItem className="text-whiskey-800 hover:bg-whiskey-100 focus:bg-whiskey-100">
                <CreditCard className="text-whiskey-500" />
                账单管理
              </DropdownMenuItem>
              <DropdownMenuItem className="text-whiskey-800 hover:bg-whiskey-100 focus:bg-whiskey-100">
                <Bell className="text-whiskey-500" />
                通知中心
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator className="bg-whiskey-200" />
            <DropdownMenuItem className="text-whiskey-800 hover:bg-whiskey-100 focus:bg-whiskey-100">
              <LogOut className="text-whiskey-500" />
              退出登录
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
