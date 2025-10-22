// 应用版本配置 - 自动生成，请勿手动编辑
export const APP_VERSION = "0.5.0";

// 版本信息对象
export const VERSION_INFO = {
  version: APP_VERSION,
  environment: import.meta.env.MODE,
} as const;
