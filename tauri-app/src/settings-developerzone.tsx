import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Store } from '@tauri-apps/plugin-store';
import { listen } from '@tauri-apps/api/event';
import { join, appDataDir } from '@tauri-apps/api/path';
import "./index.css";
import { Button } from "@/components/ui/button"
import { toast } from "sonner";

function SettingsDeveloperZone() {  
    // API服务状态
    const [apiStatus, setApiStatus] = useState({
      running: false,
      port: 60000,
      host: "127.0.0.1",
      url: "http://127.0.0.1:60000"
    });
    const [apiLogs, setApiLogs] = useState<string[]>([]);
    const [customPort, setCustomPort] = useState("60000");
    const [isPortChanged, setIsPortChanged] = useState(false);
    
    // 获取API状态
    async function checkApiStatus() {
      try {
        const status = await invoke("get_api_status");
        setApiStatus(status as any);
        setCustomPort(String((status as any).port));
      } catch (error) {
        console.error("获取API状态失败:", error);
      }
    }
  
    // 保存端口设置
    async function savePortSetting() {
      try {
        const port = parseInt(customPort, 10);
        if (isNaN(port) || port < 1024 || port > 65535) {
          toast.error("请输入有效的端口号 (1024-65535)");
          return;
        }
        
        const response = await invoke("update_api_port", { port });
        toast.success((response as any).message);
      } catch (error) {
        console.error("保存端口设置失败:", error);
        toast.error(`保存端口设置失败: ${error}`);
      }
    }
    
    // 监听输入变化
    function handlePortChange(e: React.ChangeEvent<HTMLInputElement>) {
      const newPort = e.target.value;
      setCustomPort(newPort);
      setIsPortChanged(parseInt(newPort, 10) !== apiStatus.port);
    }
  
    // 组件加载时检查API状态与监听API日志事件
    useEffect(() => {
      checkApiStatus();
      
      // 加载存储的端口设置
      const loadStoredPort = async () => {
        try {
          const appDataPath = await appDataDir();
          const storePath = await join(appDataPath, 'settings.json');
          
          // 使用正确的 Store API
          const store = await Store.load(storePath);
          
          const storedPort = await store.get('api_port');
          
          if (storedPort && typeof storedPort === 'number') {
            setCustomPort(String(storedPort));
          }
        } catch (error) {
          // 如果是首次使用，store可能不存在
          console.log("加载存储的端口设置失败 (可能是首次使用):", error);
        }
      };
      
      loadStoredPort();
      
      // 监听API日志事件
      const unlistenApiLog = listen('api-log', (event) => {
        const logMessage = event.payload as string;
        setApiLogs((prev) => [...prev, logMessage].slice(-50)); // 保留最新的50条日志
      });
      
      const unlistenApiError = listen('api-error', (event) => {
        const errorMessage = event.payload as string;
        setApiLogs((prev) => [...prev, `错误: ${errorMessage}`].slice(-50));
      });
      
      return () => {
        // 清理事件监听
        unlistenApiLog.then(unlisten => unlisten());
        unlistenApiError.then(unlisten => unlisten());
      };
    }, []);
  
    return (
      <main className="container mx-auto p-3">
        <div className="flex flex-col items-center justify-center h-[calc(100vh-4rem)]">
          {/* API服务控制面板 */}
          <div className="w-full max-w-2xl bg-card rounded-lg shadow-lg p-4">
            <h2 className="text-lg font-semibold mb-3">Python FastAPI 服务配置</h2>
            
            <div className="mb-4 p-3 bg-muted/30 rounded-md">
              <p className="mb-1">状态: <strong>{apiStatus.running ? "运行中" : "已停止"}</strong></p>
              {apiStatus.running && (
                <p>
                  API地址: <a href={apiStatus.url} target="_blank" rel="noreferrer" className="text-primary hover:underline">{apiStatus.url}</a>
                </p>
              )}
            </div>
  
            <div className="space-y-4">
              <div className="space-y-1">
                <label htmlFor="api-port" className="block text-sm font-medium">端口设置:</label>
                <p className="text-xs text-muted-foreground mb-2">修改端口设置后需要重启应用才能生效</p>
                <div className="flex gap-3">
                  <input
                    id="api-port"
                    value={customPort}
                    onChange={handlePortChange}
                    placeholder="端口"
                    className="w-full px-3 py-1.5 rounded-md border bg-background"
                  />
                  
                  <Button 
                    onClick={savePortSetting}
                    disabled={true}
                    variant="default"
                    size="sm"
                  >
                    保存设置
                  </Button>
                </div>
              </div>
            </div>
            
            <div className="mt-6 flex items-center justify-center">
              <p className="text-sm text-muted-foreground">FastAPI 服务会随应用启动和关闭自动管理</p>
            </div>
            
            <div className="mt-4">
              <h3 className="text-base font-medium mb-2">API日志</h3>
              <div className="h-[160px] overflow-y-auto border rounded-md bg-muted/10 p-3">
                {apiLogs.length === 0 ? (
                  <p className="text-muted-foreground text-center text-sm">暂无日志</p>
                ) : (
                  apiLogs.map((log, index) => (
                    <div key={index} className="text-xs mb-0.5 font-mono">{log}</div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
    );
  }
  
  export default SettingsDeveloperZone;