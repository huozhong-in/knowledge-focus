// This file is for TypeScript type augmentation
// It helps with autocompletion and type checking for custom Tailwind CSS classes

// Import the default Tailwind CSS types
import 'tailwindcss/defaultTheme'

// Extend the default Tailwind CSS types
declare module 'tailwindcss/defaultTheme' {
  interface DefaultTheme {
    extend: {
      colors: {
        whiskey: {
          '50': string,
          '100': string,
          '200': string,
          '300': string,
          '400': string,
          '500': string,
          '600': string,
          '700': string,
          '800': string,
          '900': string,
          '950': string,
        },
        // CSS variables
        background: string,
        foreground: string,
        card: string,
        "card-foreground": string,
        border: string,
        input: string,
        ring: string,
        primary: string,
        "primary-foreground": string,
        secondary: string,
        "secondary-foreground": string,
        muted: string,
        "muted-foreground": string,
        accent: string,
        "accent-foreground": string,
        destructive: string,
        "destructive-foreground": string,
      },
      borderRadius: {
        lg: string,
        md: string,
        sm: string,
      },
    }
  }
}
