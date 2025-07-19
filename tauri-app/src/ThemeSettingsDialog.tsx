import React from "react";
import { Settings } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import ThemeControlPanel from "@/tweakcn/components/editor/theme-control-panel";
import { useEditorStore } from "@/tweakcn/store/editor-store";
import { useTheme } from "@/tweakcn/components/theme-provider";
import { ThemeStyles } from "@/tweakcn/types/theme";

interface ThemeSettingsDialogProps {
  children?: React.ReactNode;
}

export function ThemeSettingsDialog({ children }: ThemeSettingsDialogProps) {
  const { themeState, setThemeState } = useEditorStore();
  const { theme } = useTheme();

  return (
    <Dialog>
      <DialogTrigger asChild>
        {children || (
          <Button variant="ghost" size="sm" className="w-full justify-start">
            <Settings className="h-4 w-4 mr-2" />
            主题设置
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-w-4xl max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>主题设置</DialogTitle>
          <DialogDescription>
            自定义您的主题颜色、字体和样式设置
          </DialogDescription>
        </DialogHeader>
        <div className="flex-1 min-h-0" style={{ height: '500px' }}>
          <ThemeControlPanel
            styles={themeState.styles}
            currentMode={theme}
            onChange={(newStyles: ThemeStyles) => {
              setThemeState({ ...themeState, styles: newStyles });
            }}
            themePromise={Promise.resolve(null)}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
