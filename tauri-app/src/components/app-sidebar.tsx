import * as React from "react"
import {
  AudioWaveform,
  BookOpen,
  Bot,
  Command,
  Frame,
  GalleryVerticalEnd,
  HomeIcon,
  Map,
  PieChart,
  Settings2,
} from "lucide-react"

import { NavMain } from "@/components/nav-main"
import { NavProjects } from "@/components/nav-projects"
import { NavUser } from "@/components/nav-user"
// import { TeamSwitcher } from "@/components/team-switcher"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
  useSidebar
} from "@/components/ui/sidebar"
import { SearchForm } from "@/components/search-form"

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
          title: "Dashboard",
          url: "#",
          pageId: "home-dashboard",
        },
        {
          title: "Insight Cards",
          url: "#",
          pageId: "home-insightcards",
        },
        {
          title: "My Files",
          url: "#",
          pageId: "home-myfiles",
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
          title: "Developer Zone",
          url: "#",
          pageId: "settings-developerzone",
        },
      ],
    },
  ],
  projects: [
    {
      name: "今天修改的文件",
      url: "#",
      icon: Frame,
    },
    {
      name: "近7天修改的文件",
      url: "#",
      icon: PieChart,
    },
    {
      name: "近30天修改的文件",
      url: "#",
      icon: Map,
    },
  ],
}

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { state } = useSidebar()
  const isCollapsed = state === "collapsed"

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <div className="flex items-center ">
          <img src="/kf-logo.png" className="w-10 h-10 object-contain" alt="Logo" />
          <SearchForm collapsed={isCollapsed} />
        </div>
      {/* <TeamSwitcher teams={data.teams} /> */}
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={data.navMain} />
        <NavProjects projects={data.projects} />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={data.user} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
