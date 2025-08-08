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

interface Message {
  id: string
  content: string
  type: "incoming" | "outgoing"
  timestamp: Date
}

export function AppWorkspace() {
  // 简易会话标识：用于后端落库绑定（持久化到 localStorage）
  const [sessionId, setSessionId] = useState<number | null>(null)
  useEffect(() => {
    try {
      const key = "kf.sessionId"
      const existing = localStorage.getItem(key)
      if (existing) {
        const parsed = Number(existing)
        if (!Number.isNaN(parsed)) {
          setSessionId(parsed)
          return
        }
      }
      const newId = Date.now() // 简单的基于时间戳的ID
      localStorage.setItem(key, String(newId))
      setSessionId(newId)
    } catch (e) {
      // 读取/写入localStorage失败时，退化为内存ID
      setSessionId(Date.now())
    }
  }, [])
  const [messages] = useState<Message[]>([
    {
      id: "1",
      content: `# 欢迎使用AI助手！🤖

我是您的**智能数据助手**，可以帮您：

- 📄 分析和处理文档
- 🏷️ 提取关键信息和标签  
- 📊 生成数据摘要
- 💡 回答各种问题

请随时向我提问，我会以**实时打字机效果**回答您！

> 💡 **提示**: 我支持完整的Markdown格式，包括代码块、表格等。`,
      type: "incoming",
      timestamp: new Date(Date.now() - 1000 * 60 * 5),
    },
    // {
    //   id: "2",
    //   content: "如何开始一个新的数据任务？",
    //   type: "outgoing",
    //   timestamp: new Date(Date.now() - 1000 * 60 * 3),
    // },
    // {
    //   id: "3",
    //   content:
    //     '您可以点击左侧的"新对话"按钮开始，或者直接在这里告诉我您想要处理什么样的数据。我可以帮您分析文档、提取关键信息、生成摘要等。',
    //   type: "incoming",
    //   timestamp: new Date(Date.now() - 1000 * 60 * 2),
    // },
  ])

  // const [windowWidth, setWindowWidth] = useState(window.innerWidth)
  // const { state, setOpen } = useSidebar()
  // const isCollapsed = state === "collapsed"
  const [isInfiniteCanvasCollapsed, setIsInfiniteCanvasCollapsed] = useState(false)
  const infiniteCanvasPanelRef = useRef<ImperativePanelHandle>(null)

  // 监听窗口大小变化
  // useEffect(() => {
  //   const handleResize = () => {
  //     setWindowWidth(window.innerWidth)
  //   }

  //   window.addEventListener("resize", handleResize)
  //   return () => window.removeEventListener("resize", handleResize)
  // }, [])

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
        <ResizablePanel defaultSize={20} minSize={20}>
          <ResizablePanelGroup direction="vertical">
            <ResizablePanel defaultSize={70} minSize={20}>
              {/* 文件列表区 */}
              <FileList />
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
        <ResizablePanel defaultSize={40} minSize={20}>
          {/* ChatUI区 */}
          <div className={`flex flex-col flex-auto h-full overflow-hidden`}>
            <div className="border-b p-2 flex flex-row h-[50px] relative">
              <div className="text-md font-semibold text-muted-foreground">
                Project Planning Assistant (AI SDK v5)
              </div>
              <div className="absolute bottom-0 right-1 z-10">
                <PanelRightIcon 
                  className={`size-7 cursor-pointer hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50 rounded-md p-1.5 transition-all ${isInfiniteCanvasCollapsed ? "rotate-180" : ""}`} 
                  onClick={handleCanvasToggle} />
              </div>
            </div>
            <AiSdkChat initialMessages={messages} sessionId={sessionId ? String(sessionId) : undefined} />
          </div>
        </ResizablePanel>
        <ResizableHandle withHandle className="bg-primary" />
        <ResizablePanel 
          ref={infiniteCanvasPanelRef}
          defaultSize={40} 
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
