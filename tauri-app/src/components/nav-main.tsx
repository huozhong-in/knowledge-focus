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
    items?: {
      title: string
      url: string
      pageId?: string
    }[]
  }[]
}) {
  const setPage = usePageStore(state => state.setPage);
  const currentPage = usePageStore(state => state.currentPage);

  return (
    <SidebarMenu>
      {items?.map((item, index) => (
        <SidebarGroup key={index}>
          <Collapsible defaultOpen={item.isActive} className="group/collapsible">
            <CollapsibleTrigger asChild>
              <SidebarMenuButton>
                {item.icon && <item.icon className="mr-2 h-4 w-4" />}
                {item.title}
                <ChevronRight className="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" />
              </SidebarMenuButton>
            </CollapsibleTrigger>
            <CollapsibleContent asChild>
              <SidebarMenuSub>
                {item.items?.map((subItem, subIndex) => (
                  <SidebarMenuSubItem key={subIndex}>
                    <SidebarMenuSubButton
                      href={subItem.url}
                      isActive={subItem.pageId === currentPage}
                      onClick={(e) => {
                        if (subItem.pageId) {
                          e.preventDefault();
                          setPage(subItem.pageId, item.title, subItem.title);
                        }
                      }}
                      className="hover:!bg-[#FFE4E6] data-[active=true]:!bg-[#FFE4E6]"
                    >
                      {subItem.title}
                    </SidebarMenuSubButton>
                  </SidebarMenuSubItem>
                ))}
              </SidebarMenuSub>
            </CollapsibleContent>
          </Collapsible>
        </SidebarGroup>
      ))}
    </SidebarMenu>
  )
}
