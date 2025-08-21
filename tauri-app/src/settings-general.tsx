import { useState, useEffect } from 'react';
import LanguageSwitcher from '@/language-switcher';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, Check, AlertCircle } from "lucide-react";

export default function SettingsGeneral() {
  const [proxyUrl, setProxyUrl] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; content: string } | null>(null);

  // 获取代理配置
  const fetchProxyConfig = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('http://127.0.0.1:60315/system-config/proxy');
      const data = await response.json();
      
      if (data.success) {
        setProxyUrl(data.config.value || '');
      } else {
        setMessage({ type: 'error', content: data.error || '获取代理配置失败' });
      }
    } catch (error) {
      console.error('获取代理配置失败:', error);
      setMessage({ type: 'error', content: '网络错误，无法获取代理配置' });
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
        setMessage({ type: 'success', content: '代理配置保存成功' });
      } else {
        setMessage({ type: 'error', content: data.error || '保存代理配置失败' });
      }
    } catch (error) {
      console.error('保存代理配置失败:', error);
      setMessage({ type: 'error', content: '网络错误，无法保存代理配置' });
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
          <CardTitle>代理设置</CardTitle>
          <CardDescription>配置模型API请求使用的代理服务器地址</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>正在加载配置...</span>
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <Label htmlFor="proxy-url">代理服务器地址</Label>
                <Input
                  id="proxy-url"
                  type="text"
                  placeholder="例如: http://127.0.0.1:7890"
                  value={proxyUrl}
                  onChange={(e) => setProxyUrl(e.target.value)}
                  disabled={isSaving}
                />
                <p className="text-sm text-muted-foreground">
                  留空表示不使用代理。支持的格式:<br/>
                  • HTTP代理: http://host:port<br/>
                  • HTTPS代理: https://host:port<br/>
                  • SOCKS5代理: socks5://host:port<br/>
                  • SOCKS5代理(远程DNS): socks5h://host:port
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
                      保存中...
                    </>
                  ) : (
                    <>
                      <Check className="h-4 w-4" />
                      保存配置
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
