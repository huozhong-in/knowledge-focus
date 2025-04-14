import { useState, useEffect } from "react";
import reactLogo from "./assets/react.svg";
import { invoke } from "@tauri-apps/api/core";
import { listen } from '@tauri-apps/api/event';
import { Window } from '@tauri-apps/api/window';
import "./App.css";

function App() {
  const [greetMsg, setGreetMsg] = useState("");
  const [name, setName] = useState("");
  
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

  async function greet() {
    setGreetMsg(await invoke("greet", { name }));
  }

  // 获取API状态
  async function checkApiStatus() {
    try {
      const status = await invoke("get_api_status");
      setApiStatus(status as any);
    } catch (error) {
      console.error("获取API状态失败:", error);
    }
  }

  // 启动API服务
  async function startApiService() {
    try {
      const port = parseInt(customPort, 10);
      const response = await invoke("start_api_service", { 
        port: isNaN(port) ? undefined : port,
        host: customHost || undefined 
      });
      setApiStatus(response as any);
      await checkApiStatus();
    } catch (error) {
      console.error("启动API服务失败:", error);
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
      setApiLogs(prev => [...prev, `INFO: ${event.payload}`].slice(-50));
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
    
    return () => {
      // 清理监听器
      unlistenLog.then(fn => fn());
      unlistenError.then(fn => fn());
      unlistenProcessError.then(fn => fn());
      unlistenTerminated.then(fn => fn());
      unlisten.then(fn => fn());
    };
  }, []);

  return (
    <main className="container">
      <h1>KnowledgeFocus</h1>

      <div className="row">
        <a href="https://vitejs.dev" target="_blank">
          <img src="/vite.svg" className="logo vite" alt="Vite logo" />
        </a>
        <a href="https://tauri.app" target="_blank">
          <img src="/tauri.svg" className="logo tauri" alt="Tauri logo" />
        </a>
        <a href="https://reactjs.org" target="_blank">
          <img src={reactLogo} className="logo react" alt="React logo" />
        </a>
      </div>

      {/* API服务控制面板 */}
      <div className="api-control-panel">
        <h2>Python FastAPI 服务控制</h2>
        
        <div className="status-info">
          <p>状态: <strong>{apiStatus.running ? "运行中" : "已停止"}</strong></p>
          {apiStatus.running && (
            <p>
              API地址: <a href={apiStatus.url} target="_blank">{apiStatus.url}</a>
            </p>
          )}
        </div>
        
        <div className="api-controls">
          <div className="control-inputs">
            <div className="input-group">
              <label htmlFor="api-host">主机:</label>
              <input
                id="api-host"
                value={customHost}
                onChange={(e) => setCustomHost(e.target.value)}
                disabled={apiStatus.running}
                placeholder="主机地址"
              />
            </div>
            
            <div className="input-group">
              <label htmlFor="api-port">端口:</label>
              <input
                id="api-port"
                value={customPort}
                onChange={(e) => setCustomPort(e.target.value)}
                disabled={apiStatus.running}
                placeholder="端口"
              />
            </div>
          </div>
          
          <div className="control-buttons">
            <button 
              onClick={startApiService}
              disabled={apiStatus.running}
            >
              启动API服务
            </button>
            
            <button 
              onClick={stopApiService}
              disabled={!apiStatus.running}
            >
              停止API服务
            </button>
          </div>
        </div>
        
        <div className="api-logs">
          <h3>API日志</h3>
          <div className="logs-container">
            {apiLogs.length === 0 ? (
              <p className="no-logs">暂无日志</p>
            ) : (
              apiLogs.map((log, index) => (
                <div key={index} className="log-line">{log}</div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="divider"></div>

      {/* 原始示例部分 */}
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          greet();
        }}
      >
        <input
          id="greet-input"
          onChange={(e) => setName(e.currentTarget.value)}
          placeholder="Enter a name..."
        />
        <button type="submit">Greet</button>
      </form>
      <p>{greetMsg}</p>
    </main>
  );
}

export default App;
