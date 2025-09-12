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
  background: "#f1f0e5",
  foreground: "#56453f",
  card: "#f1f0e5",
  "card-foreground": "#56453f",
  popover: "#ffffff",
  "popover-foreground": "#56453f",
  primary: "#a37764",
  "primary-foreground": "#ffffff",
  secondary: "#baab92",
  "secondary-foreground": "#ffffff",
  muted: "#e4c7b8",
  "muted-foreground": "#8a655a",
  accent: "#e4c7b8",
  "accent-foreground": "#56453f",
  destructive: "#1f1a17",
  "destructive-foreground": "#ffffff",
  border: "#baab92",
  input: "#baab92",
  ring: "#a37764",
  "chart-1": "#a37764",
  "chart-2": "#8a655a",
  "chart-3": "#c39e88",
  "chart-4": "#baab92",
  "chart-5": "#a28777",
  radius: "0.5rem",
  sidebar: "#ebdacb",
  "sidebar-foreground": "#56453f",
  "sidebar-primary": "#a37764",
  "sidebar-primary-foreground": "#ffffff",
  "sidebar-accent": "#c39e88",
  "sidebar-accent-foreground": "#ffffff",
  "sidebar-border": "#a28777",
  "sidebar-ring": "#a37764",
  "font-sans": "DM Sans, sans-serif",
  "font-serif": "Georgia, serif",
  "font-mono": "Menlo, monospace",
  "shadow-color": "hsl(20 18% 51%)",
  "shadow-opacity": "0.11",
  "shadow-blur": "4px",
  "shadow-spread": "-1px",
  "shadow-offset-x": "2px",
  "shadow-offset-y": "2px",
  "letter-spacing": "0em",
  spacing: "0.25rem",
};

// Default dark theme styles
export const defaultDarkThemeStyles = {
  ...defaultLightThemeStyles,
  background: "#2d2521",
  foreground: "#f1f0e5",
  card: "#3c332e",
  "card-foreground": "#f1f0e5",
  popover: "#3c332e",
  "popover-foreground": "#f1f0e5",
  primary: "#c39e88",
  "primary-foreground": "#2d2521",
  secondary: "#8a655a",
  "secondary-foreground": "#f1f0e5",
  muted: "#56453f",
  "muted-foreground": "#c5aa9b",
  accent: "#baab92",
  "accent-foreground": "#2d2521",
  destructive: "#e57373",
  "destructive-foreground": "#2d2521",
  border: "#56453f",
  input: "#56453f",
  ring: "#c39e88",
  "chart-1": "#c39e88",
  "chart-2": "#baab92",
  "chart-3": "#a37764",
  "chart-4": "#8a655a",
  "chart-5": "#a28777",
  radius: "0.5rem",
  sidebar: "#1f1a17",
  "sidebar-foreground": "#f1f0e5",
  "sidebar-primary": "#c39e88",
  "sidebar-primary-foreground": "#1f1a17",
  "sidebar-accent": "#baab92",
  "sidebar-accent-foreground": "#1f1a17",
  "sidebar-border": "#56453f",
  "sidebar-ring": "#c39e88",
  "shadow-color": "hsl(20 18% 30%)",
};

// Default theme state
export const defaultThemeState: ThemeEditorState = {
  preset: "Mocha Mousse",
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