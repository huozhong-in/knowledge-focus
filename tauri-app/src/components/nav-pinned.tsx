import {
  FolderEdit,
  ListIcon,
  MoreHorizontal,
  Pin,
  PinOff,
  type LucideIcon,
} from "lucide-react"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { usePageStore } from "@/App"
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"

export function NavPinned({
  folders: folders,
}: {
  folders: {
    name: string
    url: string
    icon: LucideIcon
    pageId?: string
  }[]
}) {
  const { isMobile } = useSidebar()

  return (
    <SidebarGroup className="group-data-[collapsible=icon]:hidden mt-2 mb-1">
      <SidebarGroupLabel className="text-whiskey-600 font-medium px-3">PINNED<Pin className="mr-2" /></SidebarGroupLabel>
      <SidebarMenu className="px-1">
        {folders.map((item) => (
          <SidebarMenuItem key={item.name}>
            <SidebarMenuButton asChild className="text-whiskey-700 hover:bg-whiskey-100 hover:text-whiskey-800">
              <a href={item.url} onClick={(e) => {
                if (item.pageId) {
                  e.preventDefault();
                  // 使用usePageStore来切换页面
                  usePageStore.getState().setPage(item.pageId, "PINNED", item.name);
                }
              }}>
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
                  <ListIcon className="text-whiskey-500" />
                  <span className="text-whiskey-800">View File</span>
                </DropdownMenuItem>
                <DropdownMenuItem className="hover:bg-whiskey-100 focus:bg-whiskey-100">
                  <FolderEdit className="text-whiskey-500" />
                  <span className="text-whiskey-800">Edit</span>
                </DropdownMenuItem>
                <DropdownMenuSeparator className="bg-whiskey-200" />
                <DropdownMenuItem className="hover:bg-whiskey-100 focus:bg-whiskey-100">
                  <PinOff className="text-whiskey-500" />
                  <span className="text-whiskey-800">Unpin</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        ))}
        <SidebarMenuItem>
          <SidebarMenuButton 
            className="text-whiskey-500 hover:bg-whiskey-100 hover:text-whiskey-600"
            onClick={() => {
              // 使用usePageStore来切换页面到HomeWiseFolders
              usePageStore.getState().setPage("home-wisefolders", "Home", "Wise Folders");
            }}
          >
            <MoreHorizontal className="text-whiskey-400" />
            <span>更多</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarGroup>
  )
}
