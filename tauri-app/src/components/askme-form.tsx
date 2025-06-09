import { Search } from "lucide-react"
import { cn } from "@/lib/utils"
import { Label } from "@/components/ui/label"
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarInput,
} from "@/components/ui/sidebar"
import { useTranslation } from 'react-i18next';

interface AskMeFormProps extends React.ComponentProps<"form"> {
  collapsed?: boolean
}

export function AskMeForm({ collapsed, className, ...props }: AskMeFormProps) {
  if (collapsed) {
    return null
  }
  const { t } = useTranslation();

  return (
    <form className={cn("w-full", className)} {...props}>
      <SidebarGroup className="py-0">
        <SidebarGroupContent className="relative">
          <Label htmlFor="ask" className="sr-only">
        {t('search-ask')}
          </Label>
          <SidebarInput
        id="ask"
        placeholder={t('search-ask')}
        className="pl-6 border-whiskey-300 focus-visible:ring-whiskey-400 focus-visible:ring-1 focus-visible:ring-opacity-50 focus-visible:border-whiskey-200 bg-whiskey-100 placeholder:text-whiskey-500 text-whiskey-800"
          />
          <Search className="pointer-events-none absolute left-2 top-1/2 size-4 -translate-y-1/2 select-none text-whiskey-400" />
        </SidebarGroupContent>
      </SidebarGroup>
    </form>
    // <p className="text-sm text-muted-foreground w-full flex items-center">
    //   Search{" "}
    //   <kbd className="pointer-events-none inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground opacity-100">
    //     <span className="text-xs">⌘</span>P
    //   </kbd>
    // </p>
  )
}
