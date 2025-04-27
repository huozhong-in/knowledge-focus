import * as React from "react"
import {
  AudioWaveform,
  BookOpen,
  Bot,
  Command,
  Frame,
  GalleryVerticalEnd,
  Map,
  PieChart,
  Settings2,
  SquareTerminal,
} from "lucide-react"

import { NavMain } from "@/components/nav-main"
// import { NavProjects } from "@/components/nav-projects"
import { NavUser } from "@/components/nav-user"
import { TeamSwitcher } from "@/components/team-switcher"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
} from "@/components/ui/sidebar"

// This is sample data.
const data = {
  user: {
    name: "GANDAOfoo",
    email: "gandaofoo@gmail.com",
    avatar: "https://pbs.twimg.com/profile_images/1785110422640869376/EJiBMUiv_x96.jpg",
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
      title: "Playground",
      url: "#",
      icon: SquareTerminal,
      isActive: true,
      items: [
        {
          title: "Home",
          url: "#",
        },
        {
          title: "Testing",
          url: "#",
          pageId: "playground-testing"
        },
        {
          title: "Archived",
          url: "#",
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
        },
        {
          title: "Domestic Models",
          url: "#",
        },
        {
          title: "Overseas Models",
          url: "#",
        },
      ],
    },
    {
      title: "Prompts",
      url: "#",
      icon: BookOpen,
      items: [
        {
          title: "Scanner",
          url: "#",
        },
        {
          title: "Crawler",
          url: "#",
        },
        {
          title: "Organizer",
          url: "#",
        },
        {
          title: "Library",
          url: "#",
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
          title: "Backend",
          url: "#",
          pageId: "settings-backend",
        },
        {
          title: "Database",
          url: "#",
          pageId: "settings-database",
        },
        {
          title: "Permissions",
          url: "#",
          pageId: "settings-permissions",
        },
      ],
    },
  ],
  projects: [
    {
      name: "Design Engineering",
      url: "#",
      icon: Frame,
    },
    {
      name: "Sales & Marketing",
      url: "#",
      icon: PieChart,
    },
    {
      name: "Travel",
      url: "#",
      icon: Map,
    },
  ],
}

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <TeamSwitcher teams={data.teams} />
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={data.navMain} />
        {/* <NavProjects projects={data.projects} /> */}
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={data.user} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
