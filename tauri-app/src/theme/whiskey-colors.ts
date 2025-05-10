/**
 * 威士忌颜色变量
 * 基于 tailwind.config.js 中定义的自定义颜色
 */

export const whiskeyColors = {
  50: '#fbf7f1',
  100: '#f5ecdf',
  200: '#ebd5bd',
  300: '#deb893',
  400: '#d29b71',
  500: '#c57a4a',
  600: '#b7663f',
  700: '#985036',
  800: '#7b4331',
  900: '#64382a',
  950: '#351b15',
};

// 导出一些常用颜色别名
export const whiskeyTheme = {
  primary: whiskeyColors[400],
  secondary: whiskeyColors[100],
  accent: whiskeyColors[300], 
  muted: whiskeyColors[50],
  border: whiskeyColors[200],
  ring: whiskeyColors[500],
  text: {
    primary: whiskeyColors[800],
    secondary: whiskeyColors[700],
    muted: whiskeyColors[600],
    light: whiskeyColors[50],
  },
  background: {
    light: whiskeyColors[50],
    card: whiskeyColors[100],
    button: whiskeyColors[200],
    buttonHover: whiskeyColors[300],
  }
};
