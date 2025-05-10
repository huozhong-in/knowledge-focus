import {
  Folder,
  Forward,
  MoreHorizontal,
  Trash2,
  type LucideIcon,
} from "lucide-react"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"

export function NavProjects({
  projects,
}: {
  projects: {
    name: string
    url: string
    icon: LucideIcon
  }[]
}) {
  const { isMobile } = useSidebar()

  return (
    <SidebarGroup className="group-data-[collapsible=icon]:hidden mt-2 mb-1">
      <SidebarGroupLabel className="text-whiskey-600 font-medium px-3">智能文件夹</SidebarGroupLabel>
      <SidebarMenu className="px-1">
        {projects.map((item) => (
          <SidebarMenuItem key={item.name}>
            <SidebarMenuButton asChild className="text-whiskey-700 hover:bg-whiskey-100 hover:text-whiskey-800">
              <a href={item.url}>
                <item.icon className="text-whiskey-400" />
                <span>{item.name}</span>
              </a>
            </SidebarMenuButton>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuAction showOnHover className="hover:bg-whiskey-200 text-whiskey-500">
                  <MoreHorizontal />
                  <span className="sr-only">更多</span>
                </SidebarMenuAction>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="w-48 rounded-lg border-whiskey-200 bg-whiskey-50"
                side={isMobile ? "bottom" : "right"}
                align={isMobile ? "end" : "start"}
              >
                <DropdownMenuItem className="hover:bg-whiskey-100 focus:bg-whiskey-100">
                  <Folder className="text-whiskey-500" />
                  <span className="text-whiskey-800">查看文件</span>
                </DropdownMenuItem>
                <DropdownMenuItem className="hover:bg-whiskey-100 focus:bg-whiskey-100">
                  <Forward className="text-whiskey-500" />
                  <span className="text-whiskey-800">分享文件</span>
                </DropdownMenuItem>
                <DropdownMenuSeparator className="bg-whiskey-200" />
                <DropdownMenuItem className="hover:bg-whiskey-100 focus:bg-whiskey-100">
                  <Trash2 className="text-whiskey-500" />
                  <span className="text-whiskey-800">删除文件</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        ))}
        <SidebarMenuItem>
          <SidebarMenuButton className="text-whiskey-500 hover:bg-whiskey-100 hover:text-whiskey-600">
            <MoreHorizontal className="text-whiskey-400" />
            <span>更多</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarGroup>
  )
}
