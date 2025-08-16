import { ThemeEditorState } from "../types/editor";

// these are common between light and dark modes
// we can assume that light mode's value will be used for dark mode as well
export const COMMON_STYLES = [
  "font-sans",
  "font-serif",
  "font-mono",
  "radius",
  "shadow-opacity",
  "shadow-blur",
  "shadow-spread",
  "shadow-offset-x",
  "shadow-offset-y",
  "letter-spacing",
  "spacing",
];

export const DEFAULT_FONT_SANS =
  "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji'";

export const DEFAULT_FONT_SERIF = 'ui-serif, Georgia, Cambria, "Times New Roman", Times, serif';

export const DEFAULT_FONT_MONO =
  'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace';

// Default light theme styles
export const defaultLightThemeStyles = {
  background: "#fff9f5",
  foreground: "#3d3436",
  card: "#ffffff",
  "card-foreground": "#3d3436",
  popover: "#ffffff",
  "popover-foreground": "#3d3436",
  primary: "#ff7e5f",
  "primary-foreground": "#ffffff",
  secondary: "#ffedea",
  "secondary-foreground": "#b35340",
  muted: "#fff0eb",
  "muted-foreground": "#78716C",
  accent: "#feb47b",
  "accent-foreground": "#3d3436",
  destructive: "#e63946",
  "destructive-foreground": "#ffffff",
  border: "#ffe0d6",
  input: "#ffe0d6",
  ring: "#ff7e5f",
  "chart-1": "#ff7e5f",
  "chart-2": "#feb47b",
  "chart-3": "#ffcaa7",
  "chart-4": "#ffad8f",
  "chart-5": "#ce6a57",
  radius: "0.625rem",
  sidebar: "#fff0eb",
  "sidebar-foreground": "#3d3436",
  "sidebar-primary": "#ff7e5f",
  "sidebar-primary-foreground": "#ffffff",
  "sidebar-accent": "#feb47b",
  "sidebar-accent-foreground": "#3d3436",
  "sidebar-border": "#ffe0d6",
  "sidebar-ring": "#ff7e5f",
  "font-sans": "Montserrat, sans-serif",
  "font-serif": "Merriweather, serif",
  "font-mono": "Ubuntu Mono, monospace",
  "shadow-color": "hsl(0 0% 0%)",
  "shadow-opacity": "0.09",
  "shadow-blur": "12px",
  "shadow-spread": "-3px",
  "shadow-offset-x": "0px",
  "shadow-offset-y": "6px",
  "letter-spacing": "0em",
  spacing: "0.25rem",
};

// Default dark theme styles
export const defaultDarkThemeStyles = {
  ...defaultLightThemeStyles,
  background: "#2a2024",
  foreground: "#f2e9e4",
  card: "#392f35",
  "card-foreground": "#f2e9e4",
  popover: "#392f35",
  "popover-foreground": "#f2e9e4",
  primary: "#ff7e5f",
  "primary-foreground": "#ffffff",
  secondary: "#463a41",
  "secondary-foreground": "#f2e9e4",
  muted: "#392f35",
  "muted-foreground": "#d7c6bc",
  accent: "#feb47b",
  "accent-foreground": "#2a2024",
  destructive: "#e63946",
  "destructive-foreground": "#ffffff",
  border: "#463a41",
  input: "#463a41",
  ring: "#ff7e5f",
  "chart-1": "#ff7e5f",
  "chart-2": "#feb47b",
  "chart-3": "#ffcaa7",
  "chart-4": "#ffad8f",
  "chart-5": "#ce6a57",
  radius: "0.625rem",
  sidebar: "#2a2024",
  "sidebar-foreground": "#f2e9e4",
  "sidebar-primary": "#ff7e5f",
  "sidebar-primary-foreground": "#ffffff",
  "sidebar-accent": "#feb47b",
  "sidebar-accent-foreground": "#2a2024",
  "sidebar-border": "#463a41",
  "sidebar-ring": "#ff7e5f",
  "shadow-color": "hsl(0 0% 0%)",
};

// Default theme state
export const defaultThemeState: ThemeEditorState = {
  preset: "Sunset Horizon",
  styles: {
    light: defaultLightThemeStyles,
    dark: defaultDarkThemeStyles,
  },
  currentMode:
    typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light",
  hslAdjustments: {
    hueShift: 0,
    saturationScale: 1,
    lightnessScale: 1,
  },
};