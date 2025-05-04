import { useState, useEffect, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from '@tauri-apps/api/event';
import { Window } from '@tauri-apps/api/window';
import "./index.css";
import { Button } from "@/components/ui/button"

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
    const [customHost, setCustomHost] = useState("127.0.0.1");
    const intervalRef = useRef<NodeJS.Timeout | null>(null);
  
    // 获取API状态
    async function checkApiStatus() {
      try {
        const status = await invoke("get_api_status");
        setApiStatus(status as any);
      } catch (error) {
        console.error("获取API状态失败:", error);
      }
    }
  
    // 重启API服务
    async function restartApiService() {
      try {
        const port = parseInt(customPort, 10);
        const response = await invoke("start_api_service", { 
          port: isNaN(port) ? undefined : port,
          host: customHost || undefined 
        });
        setApiStatus(response as any);
        await checkApiStatus();
      } catch (error) {
        console.error("重启API服务失败:", error);
      }
    }
  
    // 停止API服务
    async function stopApiService() {
      try {
        await invoke("stop_api_service");
        await checkApiStatus();
      } catch (error) {
        console.error("停止API服务失败:", error);
      }
    }
  
    // 组件加载时检查API状态
    useEffect(() => {
      const unlisten = Window.getCurrent().onCloseRequested(async () => {
        await invoke('set_activation_policy_accessory');
      });
      checkApiStatus();
      
      // 监听API日志事件
      const unlistenLog = listen<string>("api-log", (event) => {
        setApiLogs(prev => [...prev, event.payload].slice(-50)); // 保留最新的50条日志
      });
      
      // 监听API错误事件
      const unlistenError = listen<string>("api-error", (event) => {
        setApiLogs(prev => [...prev, `ERROR: ${event.payload}`].slice(-50));
      });
      
      // 监听API进程错误事件
      const unlistenProcessError = listen<string>("api-process-error", (event) => {
        setApiLogs(prev => [...prev, `进程错误: ${event.payload}`].slice(-50));
        checkApiStatus();
      });
      
      // 监听API终止事件
      const unlistenTerminated = listen<number | null>("api-terminated", (event) => {
        setApiLogs(prev => [...prev, `API服务已终止，状态码: ${event.payload ?? "未知"}`].slice(-50));
        checkApiStatus();
      });

      // 定时检查API状态
      intervalRef.current = setInterval(checkApiStatus, 5000);
      
      return () => {
        // 清理监听器
        unlistenLog.then(fn => fn());
        unlistenError.then(fn => fn());
        unlistenProcessError.then(fn => fn());
        unlistenTerminated.then(fn => fn());
        unlisten.then(fn => fn());
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
        }
      };
    }, []);
  
    return (
      <main className="container mx-auto p-3">
        <div className="flex flex-col items-center justify-center h-[calc(100vh-4rem)]">
          {/* API服务控制面板 */}
          <div className="w-full max-w-2xl bg-card rounded-lg shadow-lg p-4">
            <h2 className="text-lg font-semibold mb-3">Python FastAPI 服务控制</h2>
            
            <div className="mb-4 p-3 bg-muted/30 rounded-md">
              <p className="mb-1">状态: <strong>{apiStatus.running ? "运行中" : "已停止"}</strong></p>
              {apiStatus.running && (
                <p>
                  API地址: <a href={apiStatus.url} target="_blank" className="text-primary hover:underline">{apiStatus.url}</a>
                </p>
              )}
            </div>
  
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label htmlFor="api-host" className="block text-sm font-medium">主机:</label>
                  <input
                    id="api-host"
                    value={customHost}
                    onChange={(e) => setCustomHost(e.target.value)}
                    disabled={apiStatus.running}
                    placeholder="主机地址"
                    className="w-full px-3 py-1.5 rounded-md border bg-background disabled:opacity-50"
                  />
                </div>
                
                <div className="space-y-1">
                  <label htmlFor="api-port" className="block text-sm font-medium">端口:</label>
                  <input
                    id="api-port"
                    value={customPort}
                    onChange={(e) => setCustomPort(e.target.value)}
                    disabled={apiStatus.running}
                    placeholder="端口"
                    className="w-full px-3 py-1.5 rounded-md border bg-background disabled:opacity-50"
                  />
                </div>
              </div>
              
              <div className="flex gap-3 justify-end">
                <Button 
                  onClick={restartApiService}
                  disabled={apiStatus.running}
                  variant="default"
                  size="sm"
                >
                  启动API服务
                </Button>
                
                <Button 
                  onClick={stopApiService}
                  disabled={!apiStatus.running}
                  variant="secondary"
                  size="sm"
                >
                  停止API服务
                </Button>
              </div>
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