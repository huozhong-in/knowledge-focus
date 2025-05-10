/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    "./src/theme/**/*.{js,ts}",
  ],
  theme: {
    extend: {
      colors: {
        // 添加自定义的威士忌色系
        whiskey: {
          '50': '#fbf7f1',
          '100': '#f5ecdf',
          '200': '#ebd5bd',
          '300': '#deb893',
          '400': '#d29b71',
          '500': '#c57a4a',
          '600': '#b7663f',
          '700': '#985036',
          '800': '#7b4331',
          '900': '#64382a',
          '950': '#351b15',
        },
        // 支持通过 CSS 变量的主题颜色
        background: "var(--background)",
        foreground: "var(--foreground)",
        card: "var(--card)",
        "card-foreground": "var(--card-foreground)",
        border: "var(--border)",
        input: "var(--input)",
        ring: "var(--ring)",
        primary: "var(--primary)",
        "primary-foreground": "var(--primary-foreground)",
        secondary: "var(--secondary)",
        "secondary-foreground": "var(--secondary-foreground)",
        muted: "var(--muted)",
        "muted-foreground": "var(--muted-foreground)",
        accent: "var(--accent)",
        "accent-foreground": "var(--accent-foreground)",
        destructive: "var(--destructive)",
        "destructive-foreground": "var(--destructive-foreground)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
}
