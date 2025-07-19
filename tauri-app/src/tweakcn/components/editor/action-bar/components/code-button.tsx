import { TooltipWrapper } from "@/tweakcn/components/tooltip-wrapper";
import { Button } from "@/tweakcn/components/ui/button";
import { cn } from "@/tweakcn/lib/utils";
import { Braces } from "lucide-react";

interface CodeButtonProps extends React.ComponentProps<typeof Button> {}

export function CodeButton({ className, ...props }: CodeButtonProps) {
  return (
    <TooltipWrapper label="View theme code" asChild>
      <Button variant="ghost" size="sm" className={cn(className)} {...props}>
        <Braces className="size-3.5" />
        <span className="hidden text-sm md:block">Code</span>
      </Button>
    </TooltipWrapper>
  );
}
