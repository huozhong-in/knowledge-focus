import { TooltipWrapper } from "@/tweakcn/components/tooltip-wrapper";
import { Button } from "@/tweakcn/components/ui/button";
import { cn } from "@/tweakcn/lib/utils";
import { Loader2, Share2 } from "lucide-react";

interface ShareButtonProps extends React.ComponentProps<typeof Button> {
  isSharing?: boolean;
}

export function ShareButton({
  onClick,
  isSharing,
  disabled,
  className,
  ...props
}: ShareButtonProps) {
  return (
    <TooltipWrapper label="Share theme" asChild>
      <Button
        variant="ghost"
        size="sm"
        className={cn(className)}
        onClick={onClick}
        disabled={isSharing || disabled}
        {...props}
      >
        {isSharing ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : (
          <Share2 className="size-3.5" />
        )}
        <span className="hidden text-sm md:block">Share</span>
      </Button>
    </TooltipWrapper>
  );
}
