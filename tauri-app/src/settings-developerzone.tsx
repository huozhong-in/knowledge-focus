import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
// import { Store } from '@tauri-apps/plugin-store';
import { listen } from '@tauri-apps/api/event';
// import { join, appDataDir } from '@tauri-apps/api/path';
import "./index.css";
// import { Button } from "@/components/ui/button"
// import { toast } from "sonner";

function SettingsDeveloperZone() {  
    // API服务状态
    const [apiStatus, setApiStatus] = useState({
      running: false,
      port: 60315,
      host: "127.0.0.1",
      url: "http://127.0.0.1:60315"
    });
    const [apiLogs, setApiLogs] = useState<string[]>([]);
    
    // 获取API状态
    async function checkApiStatus() {
      try {
        const status = await invoke("get_api_status");
        setApiStatus(status as any);
        // setCustomPort(String((status as any).port));
      } catch (error) {
        console.error("获取API状态失败:", error);
      }
    }
  
    
  
    // 组件加载时检查API状态与监听API日志事件
    useEffect(() => {
      checkApiStatus();
      
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
                  API地址: {apiStatus.url}
                </p>
              )}
            </div>
  
            {/* <div className="space-y-4">
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
            </div> */}
            
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