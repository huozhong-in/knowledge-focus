import * as React from "react"
import {
  Archive,
  AudioWaveform,
  BookOpen,
  Bot,
  Command,
  Frame,
  GalleryVerticalEnd,
  HomeIcon,
  Image,
  Map,
  PieChart,
  Settings2,
} from "lucide-react"

import { NavMain } from "@/components/nav-main"
import { NavPinned } from "@/components/nav-pinned"
import { NavUser } from "@/components/nav-user"
// import { TeamSwitcher } from "@/components/team-switcher"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar"
import { AskMeForm } from "@/components/askme-form"
import { Switch } from "@/components/ui/switch"
import { useState } from "react"
import { toast } from "sonner"

// This is sample data.
const data = {
  user: {
    name: "Tom Cruise",
    email: "tom.cruise@email.com",
    avatar: "https://pbs.twimg.com/profile_images/603269306026106880/42CwEF4n_x96.jpg",
  },
  teams: [
    {
      name: "Acme Inc",
      logo: GalleryVerticalEnd,
      plan: "Enterprise",
    },
    {
      name: "Acme Corp.",
      logo: AudioWaveform,
      plan: "Startup",
    },
    {
      name: "Evil Corp.",
      logo: Command,
      plan: "Free",
    },
  ],
  navMain: [
    {
      title: "Home",
      url: "#",
      icon: HomeIcon,
      isActive: true,
      items: [
        {
          title: "Knowledge Base",
          url: "#",
          pageId: "home-knowledgebase",
        },
        {
          title: "Wise Folders",
          url: "#",
          pageId: "home-wisefolders",
        },
        {
          title: "Authorization",
          url: "#",
          pageId: "home-authorization",
        },
      ],
    },
    {
      title: "Models",
      url: "#",
      icon: Bot,
      items: [
        {
          title: "Local Models",
          url: "#",
          pageId: "models-local",
        },
        {
          title: "Domestic Models",
          url: "#",
          pageId: "models-domestic",
        },
        {
          title: "Overseas Models",
          url: "#",
          pageId: "models-overseas",
        },
      ],
    },
    {
      title: "Prompts",
      url: "#",
      icon: BookOpen,
      items: [
        {
          title: "Library",
          url: "#",
          pageId: "prompts-library",
        },
      ],
    },
    {
      title: "Settings",
      url: "#",
      icon: Settings2,
      items: [
        {
          title: "General",
          url: "#",
          pageId: "settings-general",
        },
        {
          title: "Theme",
          url: "#",
          pageId: "settings-theme",
        },
        {
          title: "Developer Zone",
          url: "#",
          pageId: "settings-developerzone",
        },
      ],
    },
  ],
}

// Define the simplified pinned folder definitions
const pinnedFolderDefinitions = [
  {
    id: "today", // Simplified ID
    name: "今日更新",
    icon: Frame,
    pageId: "today", // Simplified pageId
  },
  {
    id: "last7days", // Simplified ID
    name: "最近7天",
    icon: PieChart,
    pageId: "last7days", // Simplified pageId
  },
  {
    id: "last30days", // Simplified ID
    name: "最近30天",
    icon: Map,
    pageId: "last30days", // Simplified pageId
  },
  {
    id: "image", // Corresponds to FileType.Image, Simplified ID
    name: "图片文件",
    icon: Image,
    pageId: "image", // Simplified pageId
  },
  {
    id: "audio-video", // Corresponds to FileType.AudioVideo, Simplified ID
    name: "音视频文件",
    icon: AudioWaveform,
    pageId: "audio-video", // Simplified pageId
  },
  {
    id: "archive", // Corresponds to FileType.Archive, Simplified ID
    name: "归档文件",
    icon: Archive,
    pageId: "archive", // Simplified pageId
  },
];


export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { state } = useSidebar()
  const isCollapsed = state === "collapsed"
  const [networkEnabled, setNetworkEnabled] = useState(true)

  // Removed usage of usePinnedFolders hook
  // const { fullDiskFolders, loading: pinnedFoldersLoading } = usePinnedFolders();

  const handleNetworkSwitch = (checked: boolean) => {
    setNetworkEnabled(checked)
    toast.info(checked ? "Network mode enabled" : "Switched to local mode")
  }

  return (
    <Sidebar collapsible="icon" className="bg-whiskey-50 border-r border-whiskey-200" {...props}>
      <SidebarHeader className="border-b border-whiskey-200">
        <div className="flex items-center">
          <img src="/kf-logo.png" className="w-10 h-10 object-contain" alt="Logo" />
          <AskMeForm collapsed={isCollapsed} />
        </div>
        {/* <TeamSwitcher teams={data.teams} /> */}
        <div className="flex items-center justify-between p-2">
          {isCollapsed ? (
            <div className="w-full flex justify-center">
              <Switch
                id="network-switch"
                className="data-[state=checked]:bg-primary border-whiskey-400 transform rotate-90"
                aria-label="Network Switch"
                checked={networkEnabled}
                onCheckedChange={handleNetworkSwitch}
              />
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <span className="text-whiskey-800 text-sm">Network Switch</span>
                <Switch
                  id="network-switch"
                  className="data-[state=checked]:bg-primary border-whiskey-400"
                  aria-label="Network Switch"
                  checked={networkEnabled}
                  onCheckedChange={handleNetworkSwitch}
                />
              </div>
              <div className="text-xs text-whiskey-500">
                {networkEnabled ? 'Online' : 'Offline'}
              </div>
            </>
          )}
        </div>
      </SidebarHeader>
      <SidebarContent className="bg-whiskey-50">
        <NavPinned folders={pinnedFolderDefinitions} />
        <NavMain items={data.navMain} />
      </SidebarContent>
      <SidebarFooter className="border-t border-whiskey-200 mt-auto">
        <NavUser user={data.user} />
      </SidebarFooter>
      <SidebarRail className="hover:after:bg-whiskey-300" />
    </Sidebar>
  )
}
