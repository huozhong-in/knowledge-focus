import * as React from "react"
import {
  Archive,
  AudioWaveform,
  BookOpen,
  Bot,
  Frame,
  HomeIcon,
  Image,
  Map,
  PieChart,
  Settings2,
} from "lucide-react"

import { NavMain } from "@/components/nav-main"
import { NavPinned } from "@/components/nav-pinned"
// import { NavUser } from "@/components/nav-user"
// import { TeamSwitcher } from "@/components/team-switcher"
import {
  Sidebar,
  SidebarContent,
  // SidebarFooter,
  SidebarHeader,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar"
import { AskMeForm } from "@/components/askme-form"
import { Switch } from "@/components/ui/switch"
import { useState } from "react"
import { toast } from "sonner"
import { useTranslation } from 'react-i18next';

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { state } = useSidebar()
  const isCollapsed = state === "collapsed"
  const [networkEnabled, setNetworkEnabled] = useState(true)
  const handleNetworkSwitch = (checked: boolean) => {
    setNetworkEnabled(checked)
    toast.info(checked ? t('network-mode-enabled') : t('switched-to-local-mode'))
  }
  const { t } = useTranslation();
  const data = {
    // user: {
    //   name: "Tom Cruise",
    //   email: "tom.cruise@email.com",
    //   avatar: "https://pbs.twimg.com/profile_images/603269306026106880/42CwEF4n_x96.jpg",
    // },
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
        title: t('home'),
        url: "#",
        icon: HomeIcon,
        isActive: true,
        items: [
          {
            title: t('knowledge-base'),
            url: "#",
            pageId: "home-knowledgebase",
          },
          {
            title: t('wise-folders'),
            url: "#",
            pageId: "home-wisefolders",
          },
          {
            title: t('authorization'),
            url: "#",
            pageId: "home-authorization",
          },
        ],
      },
      {
        title: t('models'),
        url: "#",
        icon: Bot,
        items: [
          {
            title: t('models-local'),
            url: "#",
            pageId: "models-local",
          },
          {
            title: t('models-domestic'),
            url: "#",
            pageId: "models-domestic",
          },
          {
            title: t('models-international'),
            url: "#",
            pageId: "models-international",
          },
        ],
      },
      {
        title: t('prompts'),
        url: "#",
        icon: BookOpen,
        items: [
          {
            title: t('library'),
            url: "#",
            pageId: "prompts-library",
          },
          {
            title: t('mcp-hub'),
            url: "#",
            pageId: "prompts-mcp-hub",
          },
        ],
      },
      {
        title: t('settings'),
        url: "#",
        icon: Settings2,
        items: [
          {
            title: t('general'),
            url: "#",
            pageId: "settings-general",
          },
          {
            title: t('theme'),
            url: "#",
            pageId: "settings-theme",
          },
          {
            title: t('developer-zone'),
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
      name: t('today-updates'),
      icon: Frame,
      pageId: "today", // Simplified pageId
    },
    {
      id: "last7days", // Simplified ID
      name: t('last-7-days'),
      icon: PieChart,
      pageId: "last7days", // Simplified pageId
    },
    {
      id: "last30days", // Simplified ID
      name: t('last-30-days'),
      icon: Map,
      pageId: "last30days", // Simplified pageId
    },
    {
      id: "image", // Corresponds to FileType.Image, Simplified ID
      name: t('image-files'),
      icon: Image,
      pageId: "image", // Simplified pageId
    },
    {
      id: "audio-video", // Corresponds to FileType.AudioVideo, Simplified ID
      name: t('audio-video-files'),
      icon: AudioWaveform,
      pageId: "audio-video", // Simplified pageId
    },
    {
      id: "archive", // Corresponds to FileType.Archive, Simplified ID
      name: t('archive-files'),
      icon: Archive,
      pageId: "archive", // Simplified pageId
    },
  ];

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
                aria-label={t('network-switch')}
                checked={networkEnabled}
                onCheckedChange={handleNetworkSwitch}
              />
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <span className="text-whiskey-800 text-sm">{t('network-switch')}</span>
                <Switch
                  id="network-switch"
                  className="data-[state=checked]:bg-primary border-whiskey-400"
                  aria-label={t('network-switch')}
                  checked={networkEnabled}
                  onCheckedChange={handleNetworkSwitch}
                />
              </div>
              <div className="text-xs text-whiskey-500">
                {networkEnabled ? t('online') : t('offline')}
              </div>
            </>
          )}
        </div>
      </SidebarHeader>
      <SidebarContent className="bg-whiskey-50">
        <NavPinned folders={pinnedFolderDefinitions} />
        <NavMain items={data.navMain} />
      </SidebarContent>
      {/* <SidebarFooter className="border-t border-whiskey-200 mt-auto">
        <NavUser user={data.user} />
      </SidebarFooter> */}
      <SidebarRail className="hover:after:bg-whiskey-300" />
    </Sidebar>
  )
}
