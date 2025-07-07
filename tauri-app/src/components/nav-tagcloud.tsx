import {
  FolderEdit,
  ListIcon,
  MoreHorizontal,
  Pin,
  PinOff,
  type LucideIcon,
} from "lucide-react"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { usePageStore } from "@/App"
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import { useTranslation } from 'react-i18next';

export function NavTagCloud(
//   {
//   tags,
// }: {
//   tags: {
//     id: string;
//     name: string;
//   }[];
// }
) {
  const { isMobile } = useSidebar()
  const { t } = useTranslation();

  return (
    <div />
  )
}
