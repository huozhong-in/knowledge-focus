/**
 * 主题变量到 Tailwind 类的映射
 * 这个文件帮助将 CSS 变量与 Tailwind 类对应起来
 * 使主题切换更加容易
 */

import { cn } from "@/lib/utils";

// 根据主题映射类名
export const themeClassMap = {
  // 基础
  background: "bg-background", 
  foreground: "text-foreground",
  card: "bg-card",
  cardForeground: "text-card-foreground",
  
  // 主要色调
  primary: "bg-whiskey-400",
  primaryForeground: "text-whiskey-950",
  
  // 次要色调
  secondary: "bg-whiskey-100", 
  secondaryForeground: "text-whiskey-900",
  
  // 淡色/静音
  muted: "bg-whiskey-50",
  mutedForeground: "text-whiskey-700",
  
  // 强调色
  accent: "bg-whiskey-300",
  accentForeground: "text-whiskey-800",
  
  // 边框与输入
  border: "border-whiskey-200",
  input: "border-whiskey-200",
  ring: "ring-whiskey-500",
};

/**
 * 获取主题类名
 * @param key 主题键
 * @param additionalClasses 额外的类名
 */
export function getThemeClass(key: keyof typeof themeClassMap, additionalClasses?: string): string {
  return cn(themeClassMap[key], additionalClasses);
}

/**
 * 获取威士忌主题的按钮类名
 */
export function getWhiskeyButtonClass(variant: 'default' | 'outline' | 'ghost' | 'link' = 'default'): string {
  switch (variant) {
    case 'outline':
      return cn("border-whiskey-200 hover:bg-whiskey-50 text-whiskey-700");
    case 'ghost':
      return cn("hover:bg-whiskey-100 text-whiskey-700");
    case 'link':
      return cn("text-whiskey-600 underline-offset-4 hover:underline");
    default:
      return cn("bg-whiskey-200 hover:bg-whiskey-300 text-whiskey-900");
  }
}
