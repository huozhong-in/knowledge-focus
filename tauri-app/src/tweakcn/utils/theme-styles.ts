import { defaultThemeState } from "@/tweakcn/config/theme";
import { ThemeStyles } from "@/tweakcn/types/theme";

export function mergeThemeStylesWithDefaults(themeStyles: ThemeStyles) {
  const mergedStyles = {
    ...defaultThemeState.styles,
    light: { ...defaultThemeState.styles.light, ...themeStyles.light },
    dark: { ...defaultThemeState.styles.dark, ...themeStyles.dark },
  };
  return mergedStyles;
}
