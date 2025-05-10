import { ColorPalette } from "@/components/color-palette";

/**
 * 主题设置页面
 * 显示当前主题的颜色系统和主题切换选项
 */
function SettingsTheme() {
  return (
    <div className="container mx-auto p-6">
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-3xl font-bold">主题设置</h1>
          <p className="text-muted-foreground">查看和管理应用的颜色主题。</p>
        </div>
        
        {/* 颜色预览 */}
        <ColorPalette />
      </div>
    </div>
  );
}

export default SettingsTheme;
