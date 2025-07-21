import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useEditorStore } from "@/tweakcn/store/editor-store";
import { Theme } from "@/tweakcn/types/theme";
import { Check, X } from "lucide-react";

interface ThemeEditActionsProps {
  theme: Theme;
  disabled?: boolean;
}

const ThemeEditActions: React.FC<ThemeEditActionsProps> = ({ theme, disabled = false }) => {
  const { themeState, applyThemePreset } = useEditorStore();

  const handleThemeEditCancel = () => {
    applyThemePreset(themeState?.preset || "default");
  };

  const handleThemeEditSave = () => {
    // NO-OP
  };

  return (
    <>
      <div className="bg-card/80 text-card-foreground flex items-center">
        <div className="flex min-h-14 flex-1 items-center gap-2 px-4">
          <div className="flex animate-pulse items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-blue-500" />
            <span className="text-card-foreground/60 text-sm font-medium">Editing</span>
          </div>
          <span className="max-w-56 truncate px-2 text-sm font-semibold">{theme.name}</span>
        </div>

        <Separator orientation="vertical" className="bg-border h-8" />

        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-14 shrink-0 rounded-none"
                onClick={handleThemeEditCancel}
                disabled={disabled}
              >
                <X className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Cancel changes</TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <Separator orientation="vertical" className="bg-border h-8" />

        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-14 shrink-0 rounded-none"
                onClick={handleThemeEditSave}
                disabled={disabled}
              >
                <Check className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Save changes</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </>
  );
};

export default ThemeEditActions;
