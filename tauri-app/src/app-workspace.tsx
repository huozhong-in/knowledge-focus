import { useState, useRef, useEffect } from "react"
import { PanelRightIcon} from "lucide-react"
import { InfiniteCanvas } from "./infinite-canvas"
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable"
import { ImperativePanelHandle } from "react-resizable-panels"
import { FileList } from "./file-list"
import { RagLocal } from "./rag-local"
import { AiSdkChat } from "./ai-sdk-chat"
import { ChatSession } from "./lib/chat-session-api"

interface Message {
  id: string
  content: string
  type: "incoming" | "outgoing"
  timestamp: Date
}

interface AppWorkspaceProps {
  currentSession?: ChatSession | null
  currentSessionId?: number | null
  isCreatingSession?: boolean
  tempPinnedFiles?: Array<{
    file_path: string
    file_name: string
    metadata?: Record<string, any>
  }>
  onCreateSessionFromMessage?: (firstMessageContent: string) => Promise<ChatSession>
  onAddTempPinnedFile?: (filePath: string, fileName: string, metadata?: Record<string, any>) => void
  onRemoveTempPinnedFile?: (filePath: string) => void
  chatResetTrigger?: number // 新增重置触发器
}

export function AppWorkspace({ 
  currentSession, 
  currentSessionId, 
  // tempPinnedFiles,
  onCreateSessionFromMessage,
  onAddTempPinnedFile,
  onRemoveTempPinnedFile,
  chatResetTrigger
}: AppWorkspaceProps) {
  // 使用传入的sessionId，不生成临时ID
  const [sessionId, setSessionId] = useState<number | null>(currentSessionId || null)
  
  useEffect(() => {
    // 直接使用传入的currentSessionId，可能为null
    setSessionId(currentSessionId || null)
  }, [currentSessionId])
  const [messages] = useState<Message[]>([
    {
      id: "1",
      content: `# 欢迎使用AI助手！🤖

我是您的**智能数据助手**，可以帮您：

- 📄 分析和处理文档
- 🏷️ 提取关键信息和标签  
- 📊 生成数据摘要
- 💡 回答各种问题
`,
      type: "incoming",
      timestamp: new Date(Date.now() - 1000 * 60 * 5),
    },
  ])

  // const [windowWidth, setWindowWidth] = useState(window.innerWidth)
  // const { state, setOpen } = useSidebar()
  // const isCollapsed = state === "collapsed"
  // 监听窗口大小变化
  // useEffect(() => {
  //   const handleResize = () => {
  //     setWindowWidth(window.innerWidth)
  //   }

  //   window.addEventListener("resize", handleResize)
  //   return () => window.removeEventListener("resize", handleResize)
  // }, [])
  
  const [isInfiniteCanvasCollapsed, setIsInfiniteCanvasCollapsed] = useState(false)
  const infiniteCanvasPanelRef = useRef<ImperativePanelHandle>(null)
  useEffect(() => {
    if (infiniteCanvasPanelRef.current) {
      infiniteCanvasPanelRef.current.collapse() // 初始状态为收起
      setIsInfiniteCanvasCollapsed(true) // 设置初始状态为收起
    }
  }, [])
  // 处理无限画布面板的收起/展开
  const handleCanvasToggle = () => {
    if (infiniteCanvasPanelRef.current) {
      if (isInfiniteCanvasCollapsed) {
        infiniteCanvasPanelRef.current.expand()
      } else {
        infiniteCanvasPanelRef.current.collapse()
      }
    }
  }

  return (
    <main className="flex flex-row h-full overflow-hidden w-full">
      <ResizablePanelGroup
        direction="horizontal"
        className="w-full"
      >
        <ResizablePanel defaultSize={30} minSize={20}>
          <ResizablePanelGroup direction="vertical">
            <ResizablePanel defaultSize={70} minSize={20}>
              {/* 文件列表区 */}
              <FileList 
                currentSessionId={currentSessionId} 
                onAddTempPinnedFile={onAddTempPinnedFile}
                onRemoveTempPinnedFile={onRemoveTempPinnedFile}
              />
            </ResizablePanel>
            <ResizableHandle withHandle className="bg-primary" />
            <ResizablePanel defaultSize={30} minSize={20}>
              <div className="flex flex-col h-full p-1">
                <RagLocal />
              </div>
            </ResizablePanel>
          </ResizablePanelGroup>
        </ResizablePanel>
        <ResizableHandle withHandle className="bg-primary" />
        <ResizablePanel defaultSize={0} minSize={20}>
          {/* ChatUI区 */}
          <div className={`flex flex-col flex-auto h-full overflow-hidden`}>
            <div className="border-b p-2 flex flex-row h-[50px] relative">
              <div className="text-md font-semibold text-muted-foreground">
                {currentSession ? currentSession.name : "新对话"}
              </div>
              <div className="absolute bottom-0 right-1 z-10">
                <PanelRightIcon 
                  className={`size-7 cursor-pointer hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50 rounded-md p-1.5 transition-all ${isInfiniteCanvasCollapsed ? "rotate-180" : ""}`} 
                  onClick={handleCanvasToggle} />
              </div>
            </div>
            <AiSdkChat 
              initialMessages={messages} 
              sessionId={sessionId ? String(sessionId) : undefined}
              onCreateSessionFromMessage={onCreateSessionFromMessage}
              resetTrigger={chatResetTrigger}
            />
          </div>
        </ResizablePanel>
        <ResizableHandle withHandle className="bg-primary" />
        <ResizablePanel 
          ref={infiniteCanvasPanelRef}
          defaultSize={30} 
          minSize={10} 
          collapsible 
          onCollapse={() => setIsInfiniteCanvasCollapsed(true)}
          onExpand={() => setIsInfiniteCanvasCollapsed(false)}
          >
          {/* 无限画布区 */}
          <div className={`flex flex-auto w-full bg-background h-full`}>
            <div className="flex-1">
              <InfiniteCanvas />
            </div>
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </main>
  )
}
