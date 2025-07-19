import { TooltipWrapper } from "@/tweakcn/components/tooltip-wrapper";
import { Button } from "@/tweakcn/components/ui/button";
import { cn } from "@/tweakcn/lib/utils";
import { PenLine } from "lucide-react";

interface EditButtonProps extends React.ComponentProps<typeof Button> {
  themeId: string;
  onEdit?: (themeId: string) => void;
  isEditing?: boolean;
}

export function EditButton({ themeId, onEdit, isEditing = false, disabled, className, ...props }: EditButtonProps) {
  const handleClick = () => {
    if (onEdit && !disabled && !isEditing) {
      onEdit(themeId);
    }
  };

  return (
    <TooltipWrapper label="Edit theme" asChild>
      <Button
        variant="ghost"
        size="sm"
        className={cn(className)}
        disabled={disabled || isEditing}
        onClick={handleClick}
        {...props}
      >
        <PenLine className="size-3.5" />
        <span className="hidden text-sm md:block">Edit</span>
      </Button>
    </TooltipWrapper>
  );
}
