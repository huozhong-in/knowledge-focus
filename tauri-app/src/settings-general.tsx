import React from 'react';
import { useState, useEffect } from 'react';
import LanguageSwitcher from '@/language-switcher';
import AuthSection from '@/components/AuthSection';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, Check, AlertCircle } from "lucide-react";
import { useTranslation } from 'react-i18next';

export default function SettingsGeneral() {
  const [proxyUrl, setProxyUrl] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; content: string } | null>(null);
  const { t } = useTranslation();
  const instructions = t('SETTINGS.general.proxy-settings-instruction');
  // 将字符串按 '\n' 分割成数组，并为每一行或中间插入 <br />
  const formattedInstructions = instructions.split('\n').map((line, index, array) => (
    <React.Fragment key={index}>
      {line}
      {/* 如果不是最后一行，则添加一个换行符 */}
      {index < array.length - 1 && <br />}
    </React.Fragment>
  ));

  // 获取代理配置
  const fetchProxyConfig = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('http://127.0.0.1:60315/system-config/proxy');
      const data = await response.json();
      
      if (data.success) {
        setProxyUrl(data.config.value || '');
      } else {
        setMessage({ type: 'error', content: data.error || t('SETTINGS.general.fetch-proxy-failed') });
      }
    } catch (error) {
      console.error('获取代理配置失败:', error);
      setMessage({ type: 'error', content: t('SETTINGS.general.fetch-proxy-failed') });
    } finally {
      setIsLoading(false);
    }
  };

  // 保存代理配置
  const saveProxyConfig = async () => {
    setIsSaving(true);
    setMessage(null);
    
    try {
      const response = await fetch('http://127.0.0.1:60315/system-config/proxy', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          value: proxyUrl.trim()
        }),
      });
      
      const data = await response.json();
      
      if (data.success) {
        setMessage({ type: 'success', content: t('SETTINGS.general.save-proxy-success') });
      } else {
        setMessage({ type: 'error', content: data.error || t('SETTINGS.general.save-proxy-failed') });
      }
    } catch (error) {
      console.error('保存代理配置失败:', error);
      setMessage({ type: 'error', content: t('SETTINGS.general.save-proxy-failed') });
    } finally {
      setIsSaving(false);
    }
  };

  // 组件挂载时获取配置
  useEffect(() => {
    fetchProxyConfig();
  }, []);

  return (
    <div className="flex flex-col gap-6 w-full">
      <AuthSection />
      
      <Card className="w-full">
        <CardHeader>
          <CardTitle>UI Language</CardTitle>
          <CardDescription>Select the language for the application interface</CardDescription>
        </CardHeader>
        <CardContent>
          <LanguageSwitcher />
        </CardContent>
      </Card>
      
      <Card className="w-full">
        <CardHeader>
          <CardTitle>{t('SETTINGS.general.proxy-settings')}</CardTitle>
          <CardDescription>{t('SETTINGS.general.proxy-settings-description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <Label htmlFor="proxy-url">{t('SETTINGS.general.proxy-url')}</Label>
                <Input
                  id="proxy-url"
                  type="text"
                  placeholder="例如: http://127.0.0.1:7890"
                  value={proxyUrl}
                  onChange={(e) => setProxyUrl(e.target.value)}
                  disabled={isSaving}
                />
                <p className="text-sm text-muted-foreground">
                  {formattedInstructions}
                </p>
              </div>
              
              <Separator />
              
              <div className="flex items-center justify-between">
                <Button 
                  onClick={saveProxyConfig} 
                  disabled={isSaving}
                  className="flex items-center gap-2"
                >
                  {isSaving ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {t('SETTINGS.general.saving')}
                    </>
                  ) : (
                    <>
                      <Check className="h-4 w-4" />
                      {t('SETTINGS.general.save_button')}
                    </>
                  )}
                </Button>
              </div>
              
              {message && (
                <Alert variant={message.type === 'error' ? 'destructive' : 'default'}>
                  {message.type === 'error' ? (
                    <AlertCircle className="h-4 w-4" />
                  ) : (
                    <Check className="h-4 w-4" />
                  )}
                  <AlertDescription>{message.content}</AlertDescription>
                </Alert>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
