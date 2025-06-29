import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import Backend from 'i18next-http-backend';
// 支持的语言列表 - 只使用简短代码
export const supportedLanguages = ['en', 'zh'];

// 使用默认语言，不再从 Zustand 获取
// 我们将在后面的代码中通过事件订阅来动态更新语言

i18n
  // 使用HTTP后端加载语言文件
  .use(Backend)
  // 仍然使用语言检测器作为备选方案
  .use(LanguageDetector)
  // 将 i18n 实例传递给 react-i18next
  .use(initReactI18next)
  // 初始化 i18next
  // 文档: https://www.i18next.com/overview/configuration-options
  .init({
    backend: {
      // 语言文件的加载路径
      loadPath: '/locales/{{lng}}.json',
    },
    debug: true, // 在开发环境中开启 debug 模式
    fallbackLng: 'en', // 如果检测不到语言，则使用 'en'
    supportedLngs: supportedLanguages,
    // 语言映射配置
    load: 'languageOnly', // 只加载语言代码部分，如 'en' 或 'zh'
    // 不再从 Zustand 获取初始语言，而是使用默认值，稍后会更新
    lng: 'en', // 默认使用英文
    interpolation: {
      escapeValue: false, // react 已经做了 XSS 防护
    },
    // detection options 作为备份
    detection: {
      // 只使用导航器和HTML作为备选检测方法
      order: ['navigator', 'htmlTag'] as const,
      // 不再使用 localStorage 缓存
      caches: [] as const,
    },
  });

// 这个函数将在 main.tsx 中被调用，用来设置与 Zustand 的集成
export function setupI18nWithStore(appStore: any) {
  // 监听 Zustand store 中的语言变化
  appStore.subscribe(
    (state: any, prevState: any) => {
      // 只在语言真正变化时触发
      if (state.language !== prevState.language) {
        console.log(`Language changed in store from ${prevState.language} to ${state.language}`);
        
        // 切换 i18next 语言
        if (i18n.language !== state.language) {
          i18n.changeLanguage(state.language);
        }
      }
    }
  );

  // 反向监听：当 i18next 语言变化时，也更新 Zustand store
  i18n.on('languageChanged', (newLang) => {
    const currentStoreLang = appStore.getState().language;
    
    // 避免循环更新
    if (newLang !== currentStoreLang) {
      console.log(`i18next language changed to ${newLang}, updating store`);
      appStore.getState().setLanguage(newLang);
    }
  });

  // 初始化 i18next 的语言为 store 中的语言
  const initialLanguage = appStore.getState().language;
  if (initialLanguage && i18n.language !== initialLanguage) {
    i18n.changeLanguage(initialLanguage);
  }
};

export default i18n;