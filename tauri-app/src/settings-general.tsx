import LanguageSwitcher from '@/language-switcher';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function SettingsGeneral() {
  return (
    <div className="flex flex-col gap-6 w-full">
      <Card className="w-full">
        <CardHeader>
          <CardTitle>语言设置</CardTitle>
          <CardDescription>选择应用界面语言</CardDescription>
        </CardHeader>
        <CardContent>
          <LanguageSwitcher />
        </CardContent>
      </Card>
      
      <Card className="w-full">
        <CardHeader>
          <CardTitle>其他通用设置</CardTitle>
          <CardDescription>更多应用配置选项</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center text-muted-foreground">
            更多设置选项即将推出...
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
