// 应用版本配置 - 自动生成，请勿手动编辑
export const APP_VERSION = "0.2.0";
export const BUILD_DATE = "2025-09-03";
export const BUILD_TIME = "2025-09-03T08:10:48Z";

// 版本信息对象
export const VERSION_INFO = {
  version: APP_VERSION,
  buildDate: BUILD_DATE,
  buildTime: BUILD_TIME,
  environment: import.meta.env.MODE,
} as const;
