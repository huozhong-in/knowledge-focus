import * as React from "react"
import {
  PlusIcon,
  SearchIcon,
  ListIcon,
  PanelLeftOpenIcon,
} from "lucide-react"

import { NavMain } from "@/components/nav-main"
import { NavTagCloud } from "@/components/nav-tagcloud"
import { NavSettings } from "@/components/nav-settings"
// import { TeamSwitcher } from "@/components/nav-team-switcher"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar"
import {
  // SidebarInset,
  // SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
// import { Switch } from "@/components/ui/switch"
import { useState } from "react"
import { toast } from "sonner"
import { useTranslation } from 'react-i18next';

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { state, toggleSidebar } = useSidebar()
  const isCollapsed = state === "collapsed"
  const { t } = useTranslation();
  const data = {
    userSettings: {
      name: "Settings",
      description: "authorization and models",
      icon: "/settings.png",
    },
    // teams: [
    //   {
    //     name: "Acme Inc",
    //     logo: GalleryVerticalEnd,
    //     plan: "Enterprise",
    //   },
    //   {
    //     name: "Acme Corp.",
    //     logo: AudioWaveform,
    //     plan: "Startup",
    //   },
    //   {
    //     name: "Evil Corp.",
    //     logo: Command,
    //     plan: "Free",
    //   },
    // ],
    navMain: [
      {
        title: t('new_task'),
        url: "#",
        icon: PlusIcon,
        isActive: true,
      },
      {
        title: t('search_tasks'),
        url: "#",
        icon: SearchIcon,
      },
      {
        title: t('task_list'),
        url: "#",
        icon: ListIcon,
      },
    ],
  }

  return (
    <Sidebar collapsible="icon" className="bg-whiskey-50 border-r border-whiskey-200" {...props}>
      <SidebarHeader className="border-b border-whiskey-200">
        <div className="flex items-center justify-between w-full">
          <div className="relative">
            <img 
              src="/kf-logo.png" 
              className={`w-10 h-10 object-contain ${isCollapsed ? "cursor-pointer" : ""}`} 
              alt="Logo" 
              onClick={isCollapsed ? toggleSidebar : undefined}
            />
            {isCollapsed && 
                <div 
                className="absolute inset-0 flex items-center justify-center opacity-0 hover:opacity-80 cursor-pointer bg-white bg-opacity-0 hover:bg-opacity-70 rounded-md transition-all" 
                onClick={toggleSidebar}
                >
                <PanelLeftOpenIcon className="h-10 w-10 p-2 text-whiskey-600" />
                </div>
            }
          </div>
          {!isCollapsed && <SidebarTrigger />}
        </div>
        {/* <TeamSwitcher teams={data.teams} /> */}
      </SidebarHeader>
      <SidebarContent className="bg-whiskey-50">
        <NavTagCloud />
        <NavMain items={data.navMain} />
      </SidebarContent>
      <SidebarFooter className="border-t border-whiskey-200 mt-auto">
        <NavSettings config_item={data.userSettings} />
      </SidebarFooter>
      <SidebarRail className="hover:after:bg-whiskey-300" />
    </Sidebar>
  )
}
