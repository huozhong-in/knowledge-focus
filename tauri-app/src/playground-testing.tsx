import { useState, useEffect } from "react";
import reactLogo from "./assets/react.svg";
// import { invoke } from "@tauri-apps/api/core";
// import { listen } from '@tauri-apps/api/event';
// import { Window } from '@tauri-apps/api/window';
import { open } from '@tauri-apps/plugin-dialog';
import { fetch } from '@tauri-apps/plugin-http';
import { Button } from "@/components/ui/button";
// import { TestDB } from "./components/TestDB";

function PlaygroundTesting() {  
    const [apiLogs, setApiLogs] = useState<string[]>([]);
    // 文件选择测试
    const handleFileSelect = async () => {
      try {
        const selected = await open({
          multiple: true,
          directory: false,
        });
        
        if (selected) {
          // 如果选择了文件，selected就是文件路径
          setApiLogs(prev => [...prev, `选择的文件路径: ${selected}`].slice(-50));
          
          // 确保selected是数组
          const filePaths = Array.isArray(selected) ? selected : [selected];
          
          // 发送到后端API
          const response = await fetch('http://127.0.0.1:60000/file-content', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(filePaths),  // 直接发送文件路径数组
          });
          
          if (response.ok) {
            const data = await response.json();
            // 显示每个文件的结果
            data.results.forEach((result: any) => {
              setApiLogs(prev => [...prev, 
                `文件: ${result.path}`,
                result.success ? `内容: ${result.content.substring(0, 100)}...` : `错误: ${result.error}`
              ].slice(-50));
            });
          } else {
            setApiLogs(prev => [...prev, `请求失败: ${response.statusText}`].slice(-50));
          }
        }
      } catch (err) {
        console.error('文件选择错误:', err);
        setApiLogs(prev => [...prev, `文件选择错误: ${err}`].slice(-50));
      }
    };
  

    useEffect(() => {
      
      
      return () => {
        
      };
    }, []);
  
    return (
      <main className="container mx-auto p-3">
        <h1 className="text-xl font-bold text-center mb-3">KnowledgeFocus</h1>
        <div className="flex flex-col items-center justify-center h-[calc(100vh-4rem)]">
          <div className="flex gap-6 items-center mb-4">
            <a href="https://vitejs.dev" target="_blank" className="hover:opacity-80 transition-opacity">
              <img src="/vite.svg" className="w-12 h-12" alt="Vite logo" />
            </a>
            <a href="https://tauri.app" target="_blank" className="hover:opacity-80 transition-opacity">
              <img src="/tauri.svg" className="w-12 h-12" alt="Tauri logo" />
            </a>
            <a href="https://reactjs.org" target="_blank" className="hover:opacity-80 transition-opacity">
              <img src={reactLogo} className="w-12 h-12" alt="React logo" />
            </a>
          </div>
          {/* 添加测试组件 */}
          {/* <div className="w-full max-w-2xl bg-card rounded-lg shadow-lg p-4 mb-4">
            <TestDB />
          </div> */}
          
          {/* 添加文件选择测试 */}
          <div className="w-full max-w-2xl bg-card rounded-lg shadow-lg p-4 mb-4">
            <h2 className="text-lg font-semibold mb-3">文件路径测试</h2>
            <Button onClick={handleFileSelect}>
              选择文件测试
            </Button>
          </div>
  
          <div className="w-full max-w-2xl bg-card rounded-lg shadow-lg p-4">
            {/* <h2 className="text-lg font-semibold mb-3">Python FastAPI 服务控制</h2> */}
            <div className="mt-4">
              <h3 className="text-base font-medium mb-2">日志</h3>
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
  
  export default PlaygroundTesting;