import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Download, RefreshCw, CheckCircle, AlertCircle, Wifi } from "lucide-react";
import { VERSION_INFO } from "@/version";
import { useUpdater } from "@/hooks/useUpdater";
import { toast } from "sonner";
import { fetch as tauriFetch } from '@tauri-apps/plugin-http';
import { useState } from 'react';
import { Response } from '@/components/ai-elements/response';

export default function SettingsAbout() {
  const [proxyUrl, setProxyUrl] = useState('http://127.0.0.1:7890');
  const [useProxy, setUseProxy] = useState(false);
  
  const {
    updateAvailable,
    updateVersion,
    updateNotes,
    downloadProgress,
    isDownloading,
    isReadyToInstall,
    lastUpdateCheck,
    updateError,
    checkForUpdates,
    downloadAndInstall,
    restartApp
  } = useUpdater();

  const formatLastCheckTime = (timestamp: number | null) => {
    if (!timestamp) return '从未检查';
    return new Date(timestamp).toLocaleString('zh-CN');
  };

  // 测试网络连接
  const testConnection = async () => {
    try {
      console.log(`[网络测试] 使用代理: ${useProxy ? proxyUrl : '无'}`);
      
      // 使用 Tauri HTTP 插件（支持代理配置）
      const fetchOptions: any = {
        method: 'GET',
        timeout: 10000, // 10秒超时
      };
      
      // 如果启用代理，添加代理配置
      if (useProxy && proxyUrl) {
        fetchOptions.proxy = {
          all: proxyUrl
        };
      }
      
      const response = await tauriFetch('https://github.com/huozhong-in/knowledge-focus/releases/latest/download/latest.json', fetchOptions);
      
      if (response.ok) {
        const data = await response.text();
        console.log('网络测试成功:', data.substring(0, 200) + '...');
        toast.success(`网络连接正常！${useProxy ? `(通过代理 ${proxyUrl})` : ''}`);
      } else {
        toast.error(`网络测试失败: HTTP ${response.status}`);
      }
    } catch (error) {
      console.error('网络测试失败:', error);
      const errorMsg = error instanceof Error ? error.message : '未知错误';
      toast.error(`网络测试失败: ${errorMsg}`);
    }
  };

  // 详细检查 latest.json 格式
  const debugLatestJson = async () => {
    try {
      console.log('[调试] 开始检查 latest.json 格式...');
      
      const fetchOptions: any = {
        method: 'GET',
        timeout: 10000,
        headers: {
          'User-Agent': 'KnowledgeFocus-Debug/1.0',
          'Accept': 'application/json',
          'Cache-Control': 'no-cache'
        }
      };
      
      if (useProxy && proxyUrl) {
        fetchOptions.proxy = { all: proxyUrl };
      }
      
      const response = await tauriFetch('https://github.com/huozhong-in/knowledge-focus/releases/latest/download/latest.json', fetchOptions);
      
      console.log('[调试] 响应状态:', response.status);
      console.log('[调试] 响应头:', Object.fromEntries(response.headers.entries()));
      
      if (response.ok) {
        const rawText = await response.text();
        console.log('[调试] 原始响应内容 (前500字符):', rawText.substring(0, 500));
        console.log('[调试] 响应长度:', rawText.length);
        console.log('[调试] 完整原始响应:', rawText);
        
        // 显示原始内容给用户
        toast.info(`原始响应: ${rawText.substring(0, 200)}${rawText.length > 200 ? '...' : ''}`, {
          duration: 10000
        });
        
        try {
          const jsonData = JSON.parse(rawText);
          console.log('[调试] 解析后的 JSON:', jsonData);
          
          // 检查 Tauri updater 期望的字段
          const requiredFields = ['version', 'pub_date', 'url', 'signature'];
          const missingFields = requiredFields.filter(field => !(field in jsonData));
          
          if (missingFields.length > 0) {
            console.warn('[调试] 缺少必需字段:', missingFields);
            toast.error(`latest.json 缺少字段: ${missingFields.join(', ')}`);
          } else {
            console.log('[调试] JSON 格式正确，包含所有必需字段');
            toast.success('latest.json 格式检查通过！');
          }
          
          // 显示完整信息
          const info = `
版本: ${jsonData.version || '未知'}
发布日期: ${jsonData.pub_date || '未知'}
下载 URL: ${jsonData.url || '未知'}
签名: ${jsonData.signature ? '存在' : '缺失'}
更新说明: ${jsonData.notes || '无'}
          `.trim();
          
          console.log('[调试] 更新信息:', info);
          
        } catch (parseError) {
          console.error('[调试] JSON 解析失败:', parseError);
          console.error('[调试] 原始内容:', rawText);
          toast.error(`JSON 解析失败: ${parseError instanceof Error ? parseError.message : '未知错误'}`);
          
          // 检查是否是 HTML 错误页面
          if (rawText.includes('<html') || rawText.includes('<!DOCTYPE')) {
            toast.error('返回的是 HTML 页面，可能是 404 错误或服务器错误页面');
          }
        }
      } else {
        const errorText = await response.text();
        console.error('[调试] HTTP 错误响应:', errorText);
        toast.error(`HTTP ${response.status}: ${errorText.substring(0, 100)}`);
      }
    } catch (error) {
      console.error('[调试] 检查失败:', error);
      const errorMsg = error instanceof Error ? error.message : '未知错误';
      toast.error(`调试检查失败: ${errorMsg}`);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Knowledge Focus </CardTitle>
          <CardDescription>A desktop intelligent agent platform that unlocks the knowledge value of local files</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">Version:</span>
            <Badge variant="secondary">{VERSION_INFO.version}</Badge>
          </div>
          
          {/* 更新检查部分 */}
          <div className="space-y-3 pt-2 border-t">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium">软件更新</h4>
              <div className="flex items-center gap-2">
                {updateAvailable && (
                  <Badge variant="destructive" className="text-xs">
                    新版本可用
                  </Badge>
                )}
              </div>
            </div>

            {/* 更新状态显示 */}
            {updateAvailable && (
              <div className="space-y-2 p-3 bg-muted/50 rounded-md">
                <div className="flex items-center gap-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span className="text-sm font-medium">发现新版本 {updateVersion}</span>
                </div>
                {updateNotes && (
                  <p className="text-xs text-muted-foreground pl-6">
                    <Response key={updateVersion}>{updateNotes}</Response>
                  </p>
                )}
              </div>
            )}

            {/* 下载进度 */}
            {isDownloading && (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span className="text-sm">正在下载更新...</span>
                  <span className="text-xs text-muted-foreground">{downloadProgress}%</span>
                </div>
                <Progress value={downloadProgress} className="h-2" />
              </div>
            )}

            {/* 错误信息 */}
            {updateError && (
              <div className="space-y-2 p-3 bg-destructive/10 rounded-md">
                <div className="flex items-start gap-2">
                  <AlertCircle className="h-4 w-4 text-destructive mt-0.5 flex-shrink-0" />
                  <div className="space-y-1 flex-1">
                    <span className="text-sm text-destructive font-medium">检查更新失败</span>
                    <p className="text-xs text-destructive/80 break-all">{updateError}</p>
                    <details className="text-xs">
                      <summary className="cursor-pointer text-destructive/60 hover:text-destructive/80">
                        调试信息 (点击展开)
                      </summary>
                      <div className="mt-2 p-2 bg-destructive/5 rounded border text-xs font-mono break-all">
                        <p><strong>更新检查 URL:</strong></p>
                        <p className="mb-2">https://github.com/huozhong-in/knowledge-focus/releases/latest/download/latest.json</p>
                        <p><strong>当前版本:</strong> {VERSION_INFO.version}</p>
                        <p><strong>检查时间:</strong> {formatLastCheckTime(lastUpdateCheck)}</p>
                      </div>
                    </details>
                  </div>
                </div>
              </div>
            )}

            {/* 代理设置 */}
            <div className="space-y-3 p-3 bg-muted/30 rounded-md">
              <h5 className="text-xs font-medium text-muted-foreground">网络设置</h5>
              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="useProxy"
                  checked={useProxy}
                  onChange={(e) => setUseProxy(e.target.checked)}
                  className="rounded"
                />
                <Label htmlFor="useProxy" className="text-sm">使用代理服务器</Label>
              </div>
              {useProxy && (
                <div className="space-y-2">
                  <Label htmlFor="proxyUrl" className="text-xs">代理地址</Label>
                  <Input
                    id="proxyUrl"
                    value={proxyUrl}
                    onChange={(e) => setProxyUrl(e.target.value)}
                    placeholder="http://127.0.0.1:7890"
                    className="h-8 text-xs"
                  />
                </div>
              )}
            </div>

            {/* 上次检查时间 */}
            <div className="text-xs text-muted-foreground">
              上次检查: {formatLastCheckTime(lastUpdateCheck)}
            </div>

            {/* 操作按钮 */}
            <div className="flex gap-2 flex-wrap">
              {isReadyToInstall ? (
                <Button 
                  onClick={restartApp}
                  className="flex-1"
                  variant="default"
                >
                  <RefreshCw className="h-4 w-4 mr-2" />
                  重启应用
                </Button>
              ) : updateAvailable && !isDownloading ? (
                <Button 
                  onClick={downloadAndInstall}
                  className="flex-1"
                  variant="default"
                >
                  <Download className="h-4 w-4 mr-2" />
                  下载更新
                </Button>
              ) : (
                <Button 
                  onClick={() => checkForUpdates(true)}
                  variant="outline"
                  disabled={isDownloading}
                  className="flex-1"
                >
                  {isDownloading ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4 mr-2" />
                  )}
                  检查更新
                </Button>
              )}
              
              {/* 调试按钮 */}
              <Button 
                onClick={testConnection}
                variant="outline"
                size="sm"
              >
                <Wifi className="h-4 w-4 mr-1" />
                测试HTTP
              </Button>
              
              <Button 
                onClick={debugLatestJson}
                variant="outline"
                size="sm"
              >
                🔍 调试JSON
              </Button>
            </div>
          </div>
          
          <div className="space-y-2">
            <h4 className="text-sm font-medium">About</h4>
            <p className="text-sm text-muted-foreground">
              Knowledge focus is an intelligent tool for managing and discovering knowledge in various documents on your computer.
            </p>
          </div>
          
          <div className="space-y-2">
            <h4 className="text-sm font-medium">Core Features</h4>
            <ul className="text-sm text-muted-foreground space-y-1">
              <li>• Rapid Document Directory Scanning</li>
              <li>• Generate Tags Based on File Content</li>
              <li>• Document Content Understanding and Analysis</li>
              <li>• Accumulate Knowledge Through Co-reading and Co-learning with AI</li>
            </ul>
          </div>
          
          <div className="space-y-2">
            <h4 className="text-sm font-medium">Architecture</h4>
            <div className="flex gap-2 flex-wrap">
              <Badge variant="outline">Tauri/Rust</Badge>
              <Badge variant="outline">React/TypeScript/Vite/Bun</Badge>
              <Badge variant="outline">Python/PydanticAI</Badge>
              <Badge variant="outline">TailwindCSS</Badge>
              <Badge variant="outline">Shadcn/Tweakcn</Badge>
              <Badge variant="outline">Vercel AI SDK v5/AI Elements</Badge>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
