"use client";

import { cn } from "@/tweakcn/lib/utils";
import { ComponentProps, forwardRef } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

export const TooltipWrapper = forwardRef<
  React.ElementRef<typeof TooltipTrigger>,
  ComponentProps<typeof TooltipTrigger> & {
    label: string;
    command?: React.ReactNode;
  }
>(({ label, command, className, children, asChild, ...props }, ref) => {
  return (
    <Tooltip key={label}>
      <TooltipTrigger ref={ref} asChild={asChild} className={cn(className)} {...props}>
        {children}
      </TooltipTrigger>

      <TooltipContent>
        <span className="flex items-center gap-[1ch]">
          {label}
          {command && (
            <kbd className="bg-muted text-muted-foreground flex items-center gap-[0.5ch] rounded px-1.5 py-0.5 font-mono text-xs [&>svg]:size-3">
              {command}
            </kbd>
          )}
        </span>
      </TooltipContent>
    </Tooltip>
  );
});

TooltipWrapper.displayName = "TooltipWrapper";
