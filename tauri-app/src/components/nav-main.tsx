"use client"

import { ChevronRight, type LucideIcon } from "lucide-react"
import { usePageStore } from "@/App"

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "@/components/ui/sidebar"

export function NavMain({
  items,
}: {
  items: {
    title: string
    url: string
    icon?: LucideIcon
    isActive?: boolean
  }[]
}) {
  const setPage = usePageStore(state => state.setPage);
  const currentPage = usePageStore(state => state.currentPage);

  return (
    <SidebarMenu className="px-1">
      
    </SidebarMenu>
  )
}
