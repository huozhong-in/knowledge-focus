import { Button } from './components/ui/button';
import { useAppStore } from './main';

function LanguageSwitcher() {
  const { language, setLanguage } = useAppStore();

  const changeLanguage = async (lng: string) => {
    // 使用 Zustand store 的 setLanguage 方法
    await setLanguage(lng);
  };

  return (
    <div className="flex gap-4 items-center">
      <Button 
        variant={language === 'en' ? "default" : "outline"}
        onClick={() => changeLanguage('en')} 
        disabled={language === 'en'}
      >
        English
      </Button>
      <Button 
        variant={language === 'zh' ? "default" : "outline"}
        onClick={() => changeLanguage('zh')} 
        disabled={language === 'zh'}
      >
        中文
      </Button>
    </div>
  );
}

export default LanguageSwitcher;
