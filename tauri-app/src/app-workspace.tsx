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
import { useTranslation } from 'react-i18next'

interface AppWorkspaceProps {
  currentSession?: ChatSession | null
  currentSessionId?: number | null
  isCreatingSession?: boolean
  tempPinnedFiles?: Array<{
    file_path: string
    file_name: string
    metadata?: Record<string, any>
  }>
  tempSelectedTools?: string[] // 临时选择的工具列表
  onCreateSessionFromMessage?: (firstMessageContent: string) => Promise<ChatSession>
  onAddTempPinnedFile?: (filePath: string, fileName: string, metadata?: Record<string, any>) => void
  onRemoveTempPinnedFile?: (filePath: string) => void
  onAddTempSelectedTool?: (toolName: string) => void
  onRemoveTempSelectedTool?: (toolName: string) => void
  chatResetTrigger?: number // 新增重置触发器
  onSessionUpdate?: (updatedSession: ChatSession) => void // 新增会话更新回调
}

export function AppWorkspace({ 
  currentSession, 
  currentSessionId, 
  // tempPinnedFiles,
  tempSelectedTools,
  onCreateSessionFromMessage,
  onAddTempPinnedFile,
  onRemoveTempPinnedFile,
  onAddTempSelectedTool,
  onRemoveTempSelectedTool,
  chatResetTrigger,
  onSessionUpdate
}: AppWorkspaceProps) {
  // 使用传入的sessionId，不生成临时ID
  const [sessionId, setSessionId] = useState<number | null>(currentSessionId || null)
  const [selectedImagePath, setSelectedImagePath] = useState<string | null>(null) // 新增图片路径状态
  const [imageSelectionCounter, setImageSelectionCounter] = useState<number>(0) // 用于强制触发图片选择更新
  const [internalCurrentSession, setInternalCurrentSession] = useState<ChatSession | null>(currentSession || null) // 内部会话状态
  const { t } = useTranslation()
  
  useEffect(() => {
    // 直接使用传入的currentSessionId，可能为null
    setSessionId(currentSessionId || null)
  }, [currentSessionId])

  useEffect(() => {
    // 更新内部会话状态
    setInternalCurrentSession(currentSession || null)
  }, [currentSession])

  // 处理图片选择的回调函数，每次选择都会增加计数器
  const handleImageSelection = (imagePath: string) => {
    setSelectedImagePath(imagePath)
    setImageSelectionCounter(prev => prev + 1)
  }

  // 处理来自FileList的会话更新
  const handleInternalSessionUpdate = (updatedSession: ChatSession) => {
    console.log('📨 [DEBUG] AppWorkspace接收到会话更新:', updatedSession)
    setInternalCurrentSession(updatedSession)
    
    // 同时调用外部回调
    if (onSessionUpdate) {
      onSessionUpdate(updatedSession)
    }
  }

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
                onSelectImage={handleImageSelection} // 使用新的图片选择回调
                onSessionUpdate={handleInternalSessionUpdate} // 使用内部会话更新回调
                onCreateSessionFromMessage={onCreateSessionFromMessage} // 传递创建会话回调
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
        <ResizablePanel defaultSize={40} minSize={20}>
          {/* ChatUI区 */}
          <div className={`flex flex-col flex-auto h-full overflow-hidden`}>
            <div className="border-b p-2 flex flex-row h-[50px] relative">
              <div className="text-md font-semibold text-muted-foreground">
                {currentSession ? currentSession.name : t('APPSIDEBAR.new-chat')}
              </div>
              <div className="absolute bottom-0 right-1 z-10">
                <PanelRightIcon 
                  className={`size-7 cursor-pointer hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50 rounded-md p-1.5 transition-all ${isInfiniteCanvasCollapsed ? "rotate-180" : ""}`} 
                  onClick={handleCanvasToggle} />
              </div>
            </div>
            <AiSdkChat 
              sessionId={sessionId ? String(sessionId) : undefined}
              currentSession={internalCurrentSession} // 传递内部维护的当前会话数据
              onCreateSessionFromMessage={onCreateSessionFromMessage}
              resetTrigger={chatResetTrigger}
              imagePath={selectedImagePath || undefined} // 传递选中的图片路径
              imageSelectionKey={imageSelectionCounter} // 传递选择计数器以强制更新
              onSessionUpdate={onSessionUpdate} // 传递会话更新回调
              tempSelectedTools={tempSelectedTools} // 传递临时选择的工具
              onAddTempSelectedTool={onAddTempSelectedTool} // 传递添加临时工具回调
              onRemoveTempSelectedTool={onRemoveTempSelectedTool} // 传递移除临时工具回调
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
