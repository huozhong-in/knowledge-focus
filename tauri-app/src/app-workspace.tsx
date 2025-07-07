"use client"

import { useState, useRef } from "react"
import { Button } from "@/components/ui/button"
import {
  ChatContainerRoot,
  ChatContainerContent,
  ChatContainerScrollAnchor
} from "@/components/ui/chat-container"
import {
  Message,
  MessageAction,
  MessageActions,
  MessageContent,
} from "@/components/ui/message"
import {
  PromptInput,
  PromptInputAction,
  PromptInputActions,
  PromptInputTextarea,
} from "@/components/ui/prompt-input"
import { ScrollButton } from "@/components/ui/scroll-button"
import { cn } from "@/lib/utils"
import {
  ArrowUp,
  Copy,
  Mic,
  MoreHorizontal,
  Plus,
  Search,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react"

// 初始消息
const initialMessages = [
  {
    id: 1,
    role: "user",
    content: "你好！请问知识库中有哪些内容？",
  },
  {
    id: 2,
    role: "assistant",
    content: "欢迎使用Knowledge Focus知识库！我们的知识库包含了多种不同类型的资料，包括技术文档、研究报告和学习资源。您想要了解哪方面的内容呢？",
  }
]

function AppWorkspace() {
  const [prompt, setPrompt] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [chatMessages, setChatMessages] = useState(initialMessages)
  const chatContainerRef = useRef<HTMLDivElement>(null)

  const handleSubmit = () => {
    if (!prompt.trim()) return

    setPrompt("")
    setIsLoading(true)

    // 立即添加用户消息
    const newUserMessage = {
      id: chatMessages.length + 1,
      role: "user",
      content: prompt.trim(),
    }

    setChatMessages([...chatMessages, newUserMessage])

    // 模拟API响应
    setTimeout(() => {
      const assistantResponse = {
        id: chatMessages.length + 2,
        role: "assistant",
        content: `这是对"${prompt.trim()}"的回复。我正在搜索相关知识库内容以提供更准确的答案。`,
      }

      setChatMessages((prev) => [...prev, assistantResponse])
      setIsLoading(false)
    }, 1500)
  }

  return (
    <div className="flex flex-1 flex-col gap-2 p-0">
      <header className="bg-background z-10 flex h-14 w-full shrink-0 items-center gap-2 border-b px-4">
        <div className="text-foreground font-medium">知识库</div>
        <div className="ml-auto">
          <Button variant="ghost" size="sm" className="gap-2">
            <Search className="h-4 w-4" />
            搜索知识库
          </Button>
        </div>
      </header>

      <div ref={chatContainerRef} className="relative flex-1 overflow-y-auto">
        <ChatContainerRoot className="h-full">
          <ChatContainerContent className="space-y-0 px-5 py-6">
            {chatMessages.map((message, index) => {
              const isAssistant = message.role === "assistant"
              const isLastMessage = index === chatMessages.length - 1

              return (
                <Message
                  key={message.id}
                  className={cn(
                    "mx-auto flex w-full max-w-3xl flex-col gap-2 px-6",
                    isAssistant ? "items-start" : "items-end"
                  )}
                >
                  {isAssistant ? (
                    <div className="group flex w-full flex-col gap-0">
                      <MessageContent
                        className="text-foreground prose flex-1 rounded-lg bg-muted p-3"
                      >
                        {message.content}
                      </MessageContent>
                      <MessageActions
                        className={cn(
                          "-ml-2.5 flex gap-0 opacity-0 transition-opacity duration-150 group-hover:opacity-100",
                          isLastMessage && "opacity-100"
                        )}
                      >
                        <MessageAction tooltip="复制" delayDuration={100}>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="rounded-full"
                          >
                            <Copy className="h-4 w-4" />
                          </Button>
                        </MessageAction>
                        <MessageAction tooltip="有帮助" delayDuration={100}>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="rounded-full"
                          >
                            <ThumbsUp className="h-4 w-4" />
                          </Button>
                        </MessageAction>
                        <MessageAction tooltip="没帮助" delayDuration={100}>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="rounded-full"
                          >
                            <ThumbsDown className="h-4 w-4" />
                          </Button>
                        </MessageAction>
                      </MessageActions>
                    </div>
                  ) : (
                    <div className="group flex flex-col items-end gap-1">
                      <MessageContent className="bg-primary text-primary-foreground max-w-[85%] rounded-3xl px-5 py-2.5 sm:max-w-[75%]">
                        {message.content}
                      </MessageContent>
                    </div>
                  )}
                </Message>
              )
            })}
            <ChatContainerScrollAnchor />
          </ChatContainerContent>
          <div className="absolute bottom-4 left-1/2 flex w-full max-w-3xl -translate-x-1/2 justify-end px-5">
            <ScrollButton containerRef={chatContainerRef} className="shadow-sm" />
          </div>
        </ChatContainerRoot>
      </div>

      <div className="bg-background z-10 shrink-0 px-3 pb-3 md:px-5 md:pb-5">
        <div className="mx-auto max-w-3xl">
          <PromptInput
            isLoading={isLoading}
            value={prompt}
            onValueChange={setPrompt}
            onSubmit={handleSubmit}
            className="border-input bg-popover relative z-10 w-full rounded-3xl border p-0 pt-1 shadow-xs"
          >
            <div className="flex flex-col">
              <PromptInputTextarea
                placeholder="搜索知识库或提问..."
                className="min-h-[44px] pt-3 pl-4 text-base leading-[1.3] sm:text-base md:text-base"
              />

              <PromptInputActions className="mt-5 flex w-full items-center justify-between gap-2 px-3 pb-3">
                <div className="flex items-center gap-2">
                  <PromptInputAction tooltip="添加新操作">
                    <Button
                      variant="outline"
                      size="icon"
                      className="size-9 rounded-full"
                    >
                      <Plus className="size-4" />
                    </Button>
                  </PromptInputAction>

                  <PromptInputAction tooltip="更多操作">
                    <Button
                      variant="outline"
                      size="icon"
                      className="size-9 rounded-full"
                    >
                      <MoreHorizontal className="size-4" />
                    </Button>
                  </PromptInputAction>
                </div>

                <div className="flex items-center gap-2">
                  <PromptInputAction tooltip="语音输入">
                    <Button
                      variant="outline"
                      size="icon"
                      className="size-9 rounded-full"
                    >
                      <Mic className="size-4" />
                    </Button>
                  </PromptInputAction>

                  <Button
                    size="icon"
                    disabled={!prompt.trim() || isLoading}
                    onClick={handleSubmit}
                    className="size-9 rounded-full"
                  >
                    {!isLoading ? (
                      <ArrowUp className="size-4" />
                    ) : (
                      <span className="size-3 rounded-xs animate-pulse bg-white" />
                    )}
                  </Button>
                </div>
              </PromptInputActions>
            </div>
          </PromptInput>
        </div>
      </div>
    </div>
  )
}

export default AppWorkspace;