import { useState, useEffect } from "react";
import { ChatInput, ChatInputTextArea, ChatInputSubmit } from "@/components/ui/chat-input";
import { ChatMessageAvatar } from "@/components/ui/chat-message";
import { CustomScrollbar } from "./CustomScrollbar";
import { InfiniteCanvas} from "./InfiniteCanvas";
import { useSidebar } from "@/components/ui/sidebar";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { PanelLeftClose } from "lucide-react";

interface Message {
  id: string;
  content: string;
  type: "incoming" | "outgoing";
  timestamp: Date;
}

export function AppWorkspace() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      content: "欢迎使用AI数据助手！您可以在这里创建新的数据任务，我会帮您从文件中提取知识片段。",
      type: "incoming",
      timestamp: new Date(Date.now() - 1000 * 60 * 5),
    },
    {
      id: "2",
      content: "如何开始一个新的数据任务？",
      type: "outgoing",
      timestamp: new Date(Date.now() - 1000 * 60 * 3),
    },
    {
      id: "3",
      content: "您可以点击左侧的\"新数据任务\"按钮开始，或者直接在这里告诉我您想要处理什么样的数据。我可以帮您分析文档、提取关键信息、生成摘要等。",
      type: "incoming",
      timestamp: new Date(Date.now() - 1000 * 60 * 2),
    },
  ]);
  
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [windowWidth, setWindowWidth] = useState(window.innerWidth);
  const [userPrefersSidebarExpanded, setUserPrefersSidebarExpanded] = useState(true); // 用户偏好
  
  const { state } = useSidebar();
  const isCollapsed = state === "collapsed";

  // 监听窗口大小变化
  useEffect(() => {
    const handleResize = () => {
      setWindowWidth(window.innerWidth);
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // 监听侧边栏状态变化，记录用户偏好
  useEffect(() => {
    setUserPrefersSidebarExpanded(!isCollapsed);
  }, [isCollapsed]);

  // 响应式显示逻辑 - 用户意图优先
  
  // 各种组合的最小宽度需求
  const CANVAS_MIN = 380;    // 从400减少到380
  const CHATUI_MIN = 420;    // 从450减少到420  
  const FILELIST_MIN = 260;  // 从280减少到260
  const SIDEBAR_EXPANDED = 280;
  const SIDEBAR_COLLAPSED = 60;
  
  // 当前实际的侧边栏宽度
  const currentSidebarWidth = isCollapsed ? SIDEBAR_COLLAPSED : SIDEBAR_EXPANDED;
  
  // 计算主工作区可用宽度（总宽度减去侧边栏宽度）
  const workspaceWidth = windowWidth - currentSidebarWidth;
  
  // 判断当前主工作区能容纳哪些组合
  const canFitExpandedSidebarWithChatUI = windowWidth >= (SIDEBAR_EXPANDED + CHATUI_MIN + CANVAS_MIN);

  // 智能建议收起侧边栏（仅提示，不强制）
  const shouldSuggestCollapse = userPrefersSidebarExpanded && !isCollapsed && !canFitExpandedSidebarWithChatUI;
  
  // 判断是否显示各个区域（基于主工作区可用宽度）
  const shouldShowFileList = workspaceWidth >= (FILELIST_MIN + CHATUI_MIN + CANVAS_MIN);
  const shouldShowChatUI = workspaceWidth >= (CHATUI_MIN + CANVAS_MIN);
  
  // 计算各区域宽度
  const getLayoutWidths = () => {
    const fileListWidth = shouldShowFileList ? Math.min(350, Math.max(FILELIST_MIN, (workspaceWidth - CHATUI_MIN - CANVAS_MIN) * 0.2)) : 0;
    const chatUIWidth = shouldShowChatUI ? Math.min(650, Math.max(CHATUI_MIN, (workspaceWidth - fileListWidth - CANVAS_MIN) * 0.4)) : 0;
    const canvasWidth = Math.max(CANVAS_MIN, workspaceWidth - fileListWidth - chatUIWidth);
    
    return { fileListWidth, chatUIWidth, canvasWidth };
  };
  
  const { fileListWidth, chatUIWidth, canvasWidth } = getLayoutWidths();

  const handleSendMessage = async () => {
    if (!inputValue.trim()) return;
    
    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      content: inputValue,
      type: "outgoing",
      timestamp: new Date(),
    };
    
    setMessages(prev => [...prev, userMessage]);
    setInputValue("");
    setIsLoading(true);
    
    // Simulate AI response
    setTimeout(() => {
      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: "这是一个模拟的AI回复。在实际应用中，这里会连接到真正的AI服务。",
        type: "incoming",
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, aiMessage]);
      setIsLoading(false);
    }, 1000);
  };

  return (
    <div className="flex h-full relative">
      {/* 空间不足提示 */}
      {shouldSuggestCollapse && (
        <div className="absolute top-4 left-4 z-50">
          <Alert className="max-w-sm shadow-lg">
            <PanelLeftClose className="h-4 w-4" />
            <AlertDescription className="flex items-center justify-between">
              <span className="text-sm">空间不足，建议收起侧边栏</span>
              {/* <Button 
                size="sm" 
                variant="outline" 
                onClick={toggleSidebar}
                className="h-6 px-2 text-xs ml-2"
              >
                收起
              </Button> */}
            </AlertDescription>
          </Alert>
        </div>
      )}

      {/* 文件列表区 - 响应式显示 */}
      {shouldShowFileList && (
        <div 
          className="border-r bg-background flex-shrink-0"
          style={{ width: `${fileListWidth}px` }}
        >
          <div className="border-b p-4">
            <h2 className="text-lg font-semibold">标签聚合</h2>
            <p className="text-sm text-muted-foreground">文件标签聚合结果</p>
          </div>
          <div className="p-4">
            <div className="space-y-2">
              <div className="p-3 border rounded-lg">
                <div className="text-sm font-medium">文档类型</div>
                <div className="text-xs text-muted-foreground">PDF (15) | DOCX (8) | TXT (23)</div>
              </div>
              <div className="p-3 border rounded-lg">
                <div className="text-sm font-medium">主题标签</div>
                <div className="text-xs text-muted-foreground">技术文档 (12) | 报告 (8) | 笔记 (26)</div>
              </div>
              <div className="p-3 border rounded-lg">
                <div className="text-sm font-medium">时间范围</div>
                <div className="text-xs text-muted-foreground">本周 (5) | 本月 (18) | 更早 (23)</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ChatUI区 - 响应式显示 */}
      {shouldShowChatUI && (
        <div 
          className="flex flex-col border-r flex-shrink-0" 
          style={{ width: `${chatUIWidth}px` }}
        >
          {/* Header */}
          <div className="border-b p-4 flex items-center gap-4">
            <div className="text-xl font-semibold">AI对话</div>
            <div className="text-sm text-muted-foreground ml-auto">知识挖掘助手</div>
            {!shouldShowFileList && (
              <button
                onClick={() => {/* 可以添加显示文件列表的逻辑 */}}
                className="px-3 py-1 text-sm bg-secondary text-secondary-foreground rounded-md hover:bg-secondary/90"
                title="文件列表"
              >
                📁
              </button>
            )}
          </div>

          {/* Messages */}
          <CustomScrollbar className="flex-1 p-4 rounded-md">
            <div className="space-y-4">
              {messages.map((message) => (
                <div key={message.id} className={`flex gap-4 w-full ${message.type === 'outgoing' ? 'justify-end ml-auto' : 'justify-start mr-auto'}`}>
                  <ChatMessageAvatar />
                  <div className="flex flex-col gap-2">
                    <div className={`rounded-xl px-3 py-2 ${message.type === 'incoming' ? 'bg-secondary text-secondary-foreground' : 'bg-primary text-primary-foreground'}`}>
                      {message.content}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {message.timestamp.toLocaleTimeString()}
                    </div>
                  </div>
                </div>
              ))}
              {isLoading && (
                <div className="flex gap-4 w-full justify-start mr-auto">
                  <ChatMessageAvatar />
                  <div className="flex flex-col gap-2">
                    <div className="rounded-xl px-3 py-2 bg-secondary text-secondary-foreground">
                      正在输入...
                    </div>
                  </div>
                </div>
              )}
            </div>
          </CustomScrollbar>

          {/* Input */}
          <div className="border-t p-4">
            <ChatInput
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onSubmit={handleSendMessage}
              loading={isLoading}
            >
              <ChatInputTextArea placeholder="输入您的消息..." />
              <ChatInputSubmit />
            </ChatInput>
          </div>
        </div>
      )}

      {/* 无限画布区 - 始终显示，是核心价值区域 */}
      <div 
        className="flex-1 bg-background"
        style={{ minWidth: `${Math.max(CANVAS_MIN, canvasWidth)}px` }}
      >
        <div className="border-b p-4 flex items-center gap-4">
          <div className="text-xl font-semibold">知识图谱</div>
          <div className="text-sm text-muted-foreground ml-auto">精炼知识可视化</div>
          {!shouldShowChatUI && (
            <button
              onClick={() => {/* 可以添加显示ChatUI的逻辑 */}}
              className="px-3 py-1 text-sm bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
              title="显示对话"
            >
              💬
            </button>
          )}
        </div>
        <div className="flex-1">
          <InfiniteCanvas />
        </div>
      </div>
    </div>
  );
}
