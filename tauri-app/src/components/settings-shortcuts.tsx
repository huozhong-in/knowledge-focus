import { Button } from "@/components/ui/button"
import { Settings, Cpu, Shield, Palette, Info } from "lucide-react"
import { useSettingsNavigation } from "@/hooks/useSettingsNavigation"

/**
 * 演示组件：展示如何使用设置导航功能
 * 这个组件可以放在任何需要快速跳转到设置页面的地方
 */
export function SettingsShortcuts() {
  const { 
    openGeneralSettings,
    openAuthorizationSettings,
    openAIModelsSettings,
    openThemeSettings,
    openAboutPage 
  } = useSettingsNavigation()

  return (
    <div className="flex flex-wrap gap-2 p-4">
      <Button
        variant="outline"
        size="sm"
        onClick={openGeneralSettings}
        className="flex items-center gap-1"
      >
        <Settings className="h-3 w-3" />
        基本设置
      </Button>

      <Button
        variant="outline"
        size="sm"
        onClick={openAIModelsSettings}
        className="flex items-center gap-1"
      >
        <Cpu className="h-3 w-3" />
        AI模型配置
      </Button>

      <Button
        variant="outline"
        size="sm"
        onClick={openAuthorizationSettings}
        className="flex items-center gap-1"
      >
        <Shield className="h-3 w-3" />
        授权管理
      </Button>

      <Button
        variant="outline"
        size="sm"
        onClick={openThemeSettings}
        className="flex items-center gap-1"
      >
        <Palette className="h-3 w-3" />
        主题设置
      </Button>

      <Button
        variant="outline"
        size="sm"
        onClick={openAboutPage}
        className="flex items-center gap-1"
      >
        <Info className="h-3 w-3" />
        关于应用
      </Button>
    </div>
  )
}
