import { Search } from "lucide-react"
import { cn } from "@/lib/utils"
import { Label } from "@/components/ui/label"
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarInput,
} from "@/components/ui/sidebar"

interface SearchFormProps extends React.ComponentProps<"form"> {
  collapsed?: boolean
}

export function SearchForm({ collapsed, className, ...props }: SearchFormProps) {
  if (collapsed) {
    return null
  }

  return (
    <form className={cn("w-full", className)} {...props}>
      <SidebarGroup className="py-0">
        <SidebarGroupContent className="relative">
          <Label htmlFor="search" className="sr-only">
            搜索
          </Label>
          <SidebarInput
            id="search"
            placeholder="搜索内容..."
            className="pl-6 border-whiskey-300 focus-visible:ring-whiskey-400 bg-whiskey-100 placeholder:text-whiskey-500 text-whiskey-800"
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
