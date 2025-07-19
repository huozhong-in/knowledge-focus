import { 
  Settings, 
  Cpu, 
  Globe, 
  Info, 
  Palette,
  ChevronsUpDown,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { ThemeSettingsDialog } from "./ThemeSettingsDialog";
import SettingsAuthorization from "./settings-authorization";
import SettingsLocalModels from "./settings-local-models";

export function UserProfileMenu() {
  const { state } = useSidebar();
  const isCollapsed = state === "collapsed";

  return (
    <SidebarMenu className="px-1">
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
                size="lg"
                className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
            >
              <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                <Settings className="h-4 w-4" />
              </div>
              {!isCollapsed && (
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-medium">Settings</span>
                  <span className="truncate text-xs text-muted-foreground">应用设置</span>
                </div>
              )}
              {!isCollapsed && <ChevronsUpDown className="ml-auto size-4" />}
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent 
            className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg" 
            side={isCollapsed ? "right" : "top"}
            align="end" 
            sideOffset={4}
            forceMount
          >
            <DropdownMenuLabel className="p-0 font-normal">
              <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                  <Settings className="h-4 w-4" />
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-medium">应用设置</span>
                  <span className="truncate text-xs text-muted-foreground">本地应用配置</span>
                </div>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            
            <DropdownMenuGroup>
              <DropdownMenuItem disabled>
                <Settings className="mr-2 h-4 w-4" />
                <span>通用设置</span>
              </DropdownMenuItem>
              
              <ThemeSettingsDialog>
                <DropdownMenuItem onSelect={(e) => e.preventDefault()}>
                <Palette className="mr-2 h-4 w-4" />
                <span>主题设置</span>
                </DropdownMenuItem>
              </ThemeSettingsDialog>
              
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>
                  <Cpu className="mr-2 h-4 w-4" />
                  <span>AI 模型</span>
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent>
                  <DropdownMenuItem disabled>
                    <span>本地模型</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem disabled>
                    <span>在线模型</span>
                  </DropdownMenuItem>
                </DropdownMenuSubContent>
              </DropdownMenuSub>
              </DropdownMenuGroup>
              
              <DropdownMenuSeparator />
              
              <DropdownMenuGroup>
                <DropdownMenuItem>
                  <Info className="mr-2 h-4 w-4" />
                  <span>关于应用</span>
                </DropdownMenuItem>
                <DropdownMenuItem>
                  <Globe className="mr-2 h-4 w-4" />
                  <span>在线文档</span>
                </DropdownMenuItem>
                <DropdownMenuItem>
                  <Globe className="mr-2 h-4 w-4" />
                  <span>反馈建议</span>
                </DropdownMenuItem>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
