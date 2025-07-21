import { 
  Settings, 
  ChevronsUpDown,
} from "lucide-react";
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { SettingsDialog } from "./settings-dialog";
import { useSettingsStore } from "./App";

export function UserProfileMenu() {
  const { state } = useSidebar();
  const { setSettingsOpen } = useSettingsStore();
  const isCollapsed = state === "collapsed";

  return (
    <SidebarMenu className="px-1">
      <SidebarMenuItem>
        <SettingsDialog>
          <SidebarMenuButton
            size="lg"
            className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
            onClick={() => setSettingsOpen(true)}
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
        </SettingsDialog>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
