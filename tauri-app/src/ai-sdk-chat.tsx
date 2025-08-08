import { useState, useRef } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ChatMessageAvatar } from '@/components/ui/chat-message'
import {
  ChatInput,
  ChatInputTextArea,
  ChatInputSubmit,
} from '@/components/ui/chat-input'
import { MarkdownContent } from '@/components/ui/markdown-content'

interface Message {
  id: string
  content: string
  type: "incoming" | "outgoing"
  timestamp: Date
}

interface AiSdkChatProps {
  initialMessages?: Message[]
  sessionId?: string
}

/**
 * 真正的AI SDK v5集成聊天组件
 * 使用textStream实现打字机效果，无mock代码
 */
export function AiSdkChat({ initialMessages = [], sessionId }: AiSdkChatProps) {
  const [messages, setMessages] = useState<Message[]>(initialMessages.length > 0 ? initialMessages : [
    {
      id: "1",
      content: "欢迎使用AI数据助手！您可以在这里创建新的数据任务，我会帮您从文件中提取知识片段。",
      type: "incoming",
      timestamp: new Date(Date.now() - 1000 * 60 * 5),
    }
  ])
  const [inputValue, setInputValue] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const scrollAreaRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    if (scrollAreaRef.current) {
      const scrollElement = scrollAreaRef.current.querySelector('[data-radix-scroll-area-viewport]')
      if (scrollElement) {
        scrollElement.scrollTop = scrollElement.scrollHeight
      }
    }
  }

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      content: inputValue.trim(),
      type: "outgoing",
      timestamp: new Date(),
    }

    setMessages(prev => [...prev, userMessage])
    const currentInput = inputValue.trim()
    setInputValue("")
    setIsLoading(true)

    // 创建AI助手消息
    const assistantMessage: Message = {
      id: `assistant-${Date.now()}`,
      content: '',
      type: "incoming",
      timestamp: new Date(),
    }

    setMessages(prev => [...prev, assistantMessage])

    try {
      console.log('[AiSdkChat] Starting stream request with input:', currentInput)

      // 调用后端API
      // 组装请求体（按AI SDK v5 UIMessage格式 + 可选 session_id）
      const payload: any = {
        messages: [
          {
            role: 'user',
            parts: [{ type: 'text', text: currentInput }]
          }
        ],
        trigger: 'submit-message',
        chatId: `chat-${Date.now()}`,
      }
      if (sessionId) {
        payload.session_id = Number(sessionId)
      }

      const response = await fetch('http://localhost:60315/chat/ui-stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          'Cache-Control': 'no-cache',
        },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      if (!response.body) {
        throw new Error('No response body')
      }

      // 使用ReadableStream实现textStream模式
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulatedContent = ''

      // 实现AI SDK v5的textStream模式
      while (true) {
        const { done, value } = await reader.read()
        
        if (done) {
          console.log('[AiSdkChat] Stream completed')
          break
        }

        buffer += decoder.decode(value, { stream: true })
        
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim()
            
            if (data === '[DONE]') {
              console.log('[AiSdkChat] Received [DONE]')
              break
            }

            if (data) {
              try {
                const parsed = JSON.parse(data)
                console.log('[AiSdkChat] Parsed event:', parsed)
                
                // 处理AI SDK v5格式的流事件
                if (parsed.type === 'text-delta' && parsed.delta) {
                  accumulatedContent += parsed.delta
                  
                  // 实现打字机效果 - 实时更新内容
                  setMessages(prev => 
                    prev.map(msg => 
                      msg.id === assistantMessage.id 
                        ? { ...msg, content: accumulatedContent }
                        : msg
                    )
                  )

                  // 自动滚动到底部
                  setTimeout(scrollToBottom, 50)
                  
                  // 添加一个小延迟来让打字机效果更明显
                  await new Promise(resolve => setTimeout(resolve, 50))
                }
                else if (parsed.type === 'error') {
                  console.error('[AiSdkChat] Stream error:', parsed.errorText)
                  
                  // 显示错误消息
                  setMessages(prev => 
                    prev.map(msg => 
                      msg.id === assistantMessage.id 
                        ? { ...msg, content: `抱歉，发生了错误：${parsed.errorText}` }
                        : msg
                    )
                  )
                  break
                }
              } catch (e) {
                console.warn('[AiSdkChat] Failed to parse JSON:', data, e)
              }
            }
          }
        }
      }
    } catch (err) {
      console.error('[AiSdkChat] Error:', err)
      
      // 显示错误消息
      setMessages(prev => 
        prev.map(msg => 
          msg.id === assistantMessage.id 
            ? { ...msg, content: `抱歉，发生了错误：${err instanceof Error ? err.message : '未知错误'}` }
            : msg
        )
      )
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex flex-col flex-auto h-full overflow-hidden">
      {/* Messages */}
      <ScrollArea ref={scrollAreaRef} className="flex-1 p-4 rounded-md h-[calc(100vh-180px)]">
        <div className="space-y-4 mx-auto">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-4 w-full justify-start ${
                message.type === "outgoing" ? "ml-auto flex-row-reverse" : "mr-auto"
              }`}
            >
              <ChatMessageAvatar />
              <div className="flex flex-col gap-2">
                <div
                  className={`rounded-xl max-w-3/4 px-3 py-2 ${
                    message.type === "incoming"
                      ? "bg-secondary text-secondary-foreground"
                      : "bg-primary text-primary-foreground ml-auto"
                  }`}
                >
                  {message.type === "incoming" ? (
                    // AI消息使用Markdown渲染
                    <div className="prose prose-sm max-w-none dark:prose-invert text-secondary-foreground">
                      {message.content ? (
                        <MarkdownContent 
                          content={message.content} 
                          id={message.id}
                        />
                      ) : isLoading ? (
                        <span className="text-muted-foreground">正在思考...</span>
                      ) : null}
                      {/* 打字机光标 */}
                      {isLoading && message.content && (
                        <span className="animate-pulse ml-1">▊</span>
                      )}
                    </div>
                  ) : (
                    // 用户消息保持纯文本
                    message.content
                  )}
                </div>
                <span className="text-xs text-muted-foreground">
                  {message.timestamp.toLocaleTimeString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="border-t p-4">
        <ChatInput
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onSubmit={handleSendMessage}
          loading={isLoading}
        >
          <ChatInputTextArea
            placeholder="输入消息..."
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSendMessage()
              }
            }}
          />
          <ChatInputSubmit>
            {isLoading ? "发送中..." : "发送"}
          </ChatInputSubmit>
        </ChatInput>
      </div>
    </div>
  )
}
