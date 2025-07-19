import { TooltipWrapper } from "@/tweakcn/components/tooltip-wrapper";
import { Button } from "@/tweakcn/components/ui/button";
import { cn } from "@/tweakcn/lib/utils";
import { RefreshCw } from "lucide-react";

interface ResetButtonProps extends React.ComponentProps<typeof Button> {}

export function ResetButton({ className, ...props }: ResetButtonProps) {
  return (
    <TooltipWrapper label="Reset to preset defaults" asChild>
      <Button variant="ghost" size="sm" className={cn(className)} {...props}>
        <RefreshCw className="size-3.5" />
        <span className="hidden text-sm md:block">Reset</span>
      </Button>
    </TooltipWrapper>
  );
}
