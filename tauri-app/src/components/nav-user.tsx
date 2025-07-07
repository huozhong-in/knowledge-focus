"use client"
import { usePageStore } from "@/App"
import {
  FileBoxIcon,
  Bell,
  ChevronsUpDown,
  Settings2Icon,
  ListTodo,
  BadgeInfoIcon,
  Cog,
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
import { useTranslation } from 'react-i18next';

export function NavUser({
  user,
}: {
  user: {
    name: string
    description: string
    icon: string
  }
}) {
  const { isMobile } = useSidebar()
  const setPage = usePageStore(state => state.setPage);
  const { t } = useTranslation();

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
                <AvatarImage src={user.icon} alt={user.name} />
                <AvatarFallback className="bg-whiskey-100 text-whiskey-500 rounded-lg"><Cog /></AvatarFallback>
              </Avatar>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-medium text-whiskey-800">{user.name}</span>
                <span className="truncate text-xs text-whiskey-600">{user.description}</span>
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
                  <AvatarImage src={user.icon} alt={user.name} />
                  <AvatarFallback className="bg-whiskey-50 text-whiskey-500 rounded-lg"><Cog /></AvatarFallback>
                </Avatar>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-medium text-whiskey-800">{user.name}</span>
                  <span className="truncate text-xs text-whiskey-600">User preferences</span>
                </div>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-whiskey-200" />
            <DropdownMenuGroup>
              <DropdownMenuItem className="text-whiskey-800 hover:bg-whiskey-100 focus:bg-whiskey-100" onClick={() => setPage("home-authorization", t('authorization'),"")}>
                <ListTodo className="text-whiskey-500" />
                Authorization
              </DropdownMenuItem>
              <DropdownMenuItem className="text-whiskey-800 hover:bg-whiskey-100 focus:bg-whiskey-100" onClick={() => setPage("models-local", t('models-local'),"")}>
                <FileBoxIcon className="text-whiskey-500" />
                Models
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator className="bg-whiskey-200" />
            <DropdownMenuGroup>
              <DropdownMenuItem className="text-whiskey-800 hover:bg-whiskey-100 focus:bg-whiskey-100" onClick={() => setPage("settings-general", t('general-subtitle'),"")}>
                <Settings2Icon className="text-whiskey-500" />
                General
              </DropdownMenuItem>
              <DropdownMenuItem className="text-whiskey-800 hover:bg-whiskey-100 focus:bg-whiskey-100">
                <Bell className="text-whiskey-500" />
                通知中心
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator className="bg-whiskey-200" />
            <DropdownMenuItem className="text-whiskey-800 hover:bg-whiskey-100 focus:bg-whiskey-100">
              <BadgeInfoIcon className="text-whiskey-500" />
                About
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
