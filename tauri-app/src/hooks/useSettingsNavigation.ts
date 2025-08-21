import { useSettingsStore } from '@/App'

export type SettingsPage = 
  | "general"
  | "authorization" 
  | "file_recognition"
  | "aimodels"
  | "theme"
  | "about"

/**
 * 设置页面导航 Hook
 * 提供便捷的方法来打开设置对话框的特定页面
 */
export function useSettingsNavigation() {
  const { openSettingsPage } = useSettingsStore()

  const openSettings = (page: SettingsPage = "general") => {
    openSettingsPage(page)
  }

  const openGeneralSettings = () => openSettings("general")
  const openAuthorizationSettings = () => openSettings("authorization")  
  const openFileRecognitionSettings = () => openSettings("file_recognition")
  const openAIModelsSettings = () => openSettings("aimodels")
  const openThemeSettings = () => openSettings("theme")
  const openAboutPage = () => openSettings("about")

  return {
    openSettings,
    openGeneralSettings,
    openAuthorizationSettings,
    openFileRecognitionSettings,
    openAIModelsSettings,
    openThemeSettings,
    openAboutPage,
  }
}
