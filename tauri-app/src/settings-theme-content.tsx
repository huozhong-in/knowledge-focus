import { useEffect } from "react";
import ThemeControlPanel from "@/tweakcn/components/editor/theme-control-panel";
import { useEditorStore } from "@/tweakcn/store/editor-store";
import { useTheme } from "@/tweakcn/components/theme-provider";
import { ThemeStyles } from "@/tweakcn/types/theme";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function SettingsTheme() {
  const { themeState, setThemeState } = useEditorStore();
  const { theme } = useTheme();

  // 确保组件清理时正确处理资源
  useEffect(() => {
    return () => {
      // 清理函数，确保正确释放资源
    };
  }, []);

  const handleThemeChange = (newStyles: ThemeStyles) => {
    try {
      setThemeState({ ...themeState, styles: newStyles });
    } catch (error) {
      console.error("Failed to update theme:", error);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>主题设置</CardTitle>
        <CardDescription>自定义您的主题颜色、字体和样式设置</CardDescription>
      </CardHeader>
      <CardContent>
        <div >
          <ThemeControlPanel
            styles={themeState.styles}
            currentMode={theme}
            onChange={handleThemeChange}
            themePromise={Promise.resolve(null)}
          />
        </div>
      </CardContent>
    </Card>
  );
}
