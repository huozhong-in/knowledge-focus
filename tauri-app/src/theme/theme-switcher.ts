/**
 * 主题切换工具
 * 这个文件提供了主题切换的基础功能，可以在需要时扩展
 */

export type ThemeName = 'whiskey' | 'pink' | 'system';

/**
 * 动态加载主题CSS文件
 * @param theme 主题名称
 */
export function loadThemeCSS(theme: ThemeName): void {
  // 移除现有的主题样式表
  const existingThemeLinks = document.querySelectorAll('link[data-theme]');
  existingThemeLinks.forEach(link => link.remove());

  if (theme === 'system') {
    // 系统主题逻辑可以在这里实现
    // 例如根据操作系统偏好选择亮暗主题
    return;
  }

  // 创建并添加新的主题样式表
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = `/src/theme-${theme}.css`;
  link.dataset.theme = theme;
  document.head.appendChild(link);
}

/**
 * 保存主题偏好到本地存储
 * @param theme 主题名称
 */
export function saveThemePreference(theme: ThemeName): void {
  localStorage.setItem('theme-preference', theme);
}

/**
 * 获取保存的主题偏好
 * @returns 主题名称，如果没有保存过则返回默认值
 */
export function getThemePreference(): ThemeName {
  return (localStorage.getItem('theme-preference') as ThemeName) || 'whiskey';
}

/**
 * 应用主题
 * @param theme 主题名称
 */
export function applyTheme(theme: ThemeName = getThemePreference()): void {
  loadThemeCSS(theme);
  saveThemePreference(theme);
}
