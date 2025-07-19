import { TooltipWrapper } from "@/tweakcn/components/tooltip-wrapper";
import { Button } from "@/tweakcn/components/ui/button";
import { cn } from "@/tweakcn/lib/utils";
import { Heart, Loader2 } from "lucide-react";

interface SaveButtonProps extends React.ComponentProps<typeof Button> {
  isSaving: boolean;
}

export function SaveButton({ isSaving, disabled, className, ...props }: SaveButtonProps) {
  return (
    <TooltipWrapper label="Save theme" asChild>
      <Button
        variant="ghost"
        size="sm"
        className={cn(className)}
        disabled={isSaving || disabled}
        {...props}
      >
        {isSaving ? <Loader2 className="size-3.5 animate-spin" /> : <Heart className="size-3.5" />}
        <span className="hidden text-sm md:block">Save</span>
      </Button>
    </TooltipWrapper>
  );
}
