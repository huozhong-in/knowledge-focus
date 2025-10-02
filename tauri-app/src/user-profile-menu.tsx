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
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { SettingsDialog } from "./settings-dialog";
import { useSettingsStore } from "./App";
import { useTranslation } from "react-i18next";
import { UpdateBadge } from "@/components/UpdateBadge";
import { useAuthStore } from "@/lib/auth-store";

export function UserProfileMenu() {
  const { state } = useSidebar();
  const { setSettingsOpen } = useSettingsStore();
  const { user, isAuthenticated } = useAuthStore();
  const isCollapsed = state === "collapsed";
  const { t } = useTranslation();

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SettingsDialog>
          <SidebarMenuButton
            size="lg"
            className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground relative"
            onClick={() => setSettingsOpen(true)}
          >
            <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
              {isAuthenticated && user ? (
                <Avatar className="size-8 rounded-lg">
                  <AvatarImage src={user.avatar_url || ''} alt={user.name} />
                  <AvatarFallback className="text-xs">
                    {user.name.charAt(0).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
              ) : (
                <Settings className="h-4 w-4" />
              )}
            </div>
            {/* 更新提示红点 */}
            <UpdateBadge />
            {!isCollapsed && (
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-medium">
                  {isAuthenticated && user ? user.name : t('APPSIDEBAR.settings')}
                </span>
                <span className="truncate text-xs text-muted-foreground justify-self-end">
                  <>Press{" "}
                    <kbd className="bg-muted text-muted-foreground pointer-events-none inline-flex h-5 items-center gap-1 rounded border px-1.5 font-mono text-[10px] font-medium opacity-100 select-none">
                      <span className="text-xs">⌘ ,</span>
                    </kbd>
                  </>
                </span>
              </div>
            )}
            {!isCollapsed && <ChevronsUpDown className="ml-auto size-4" />}
          </SidebarMenuButton>
        </SettingsDialog>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
