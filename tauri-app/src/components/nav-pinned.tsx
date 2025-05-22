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
// Removed import of FullDiskFolder
// import { FullDiskFolder } from "../pinned-folders"

export function NavPinned({
  folders: folders,
}: {
  // Reverted prop type to match the simplified definition
  folders: {
    id: string;
    name: string;
    icon: LucideIcon;
    pageId?: string;
  }[];
}) {
  const { isMobile } = useSidebar()

  return (
    <SidebarGroup className="group-data-[collapsible=icon]:hidden mt-2 mb-1">
      <SidebarGroupLabel className="text-whiskey-600 font-medium px-3">PINNED My Files<Pin className="mr-2" /></SidebarGroupLabel>
      <SidebarMenu className="px-1">
        {folders.map((item) => (
          // Use item.id as the key
          <SidebarMenuItem key={item.id} onClick={(e) => { // Added onClick here
                  e.preventDefault();
                  // 使用usePageStore来切换页面
                  // Use item.pageId for navigation and item.name for display
                  if (item.pageId) {
                    usePageStore.getState().setPage(item.pageId, "PINNED", item.name);
                  }
              }}>
            <SidebarMenuButton> {/* Removed onClick from here */}
              {/* Moved className and onClick to the a tag */}
              <a href="#" className="flex items-center gap-2 text-whiskey-700 hover:bg-whiskey-100 hover:text-whiskey-800"> {/* onClick removed from here */}
                {/* Assuming item.icon is a LucideIcon component */}
                <item.icon className="text-whiskey-400" />
                <span>{item.name}</span> {/* Use item.name for display */}
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
