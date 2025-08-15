import { useState, useRef, useEffect } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ChatMessageAvatar } from '@/components/ui/chat-message'
import {
  ChatInput,
  ChatInputTextArea,
  ChatInputSubmit,
} from '@/components/ui/chat-input'
import { MarkdownContent } from '@/components/ui/markdown-content'
import { ChatSession, ChatMessage, getSessionMessages } from './lib/chat-session-api'

interface Message {
  id: string
  content: string
  type: "incoming" | "outgoing"
  timestamp: Date
}

interface AiSdkChatProps {
  initialMessages?: Message[]
  sessionId?: string
  onCreateSessionFromMessage?: (firstMessageContent: string) => Promise<ChatSession>
  resetTrigger?: number // 用于触发重置的数字，每次改变都会重置组件
}

/**
 * 真正的AI SDK v5集成聊天组件
 * 使用textStream实现打字机效果，无mock代码
 */
export function AiSdkChat({ initialMessages = [], sessionId, onCreateSessionFromMessage, resetTrigger }: AiSdkChatProps) {
  const welcomeMessages = function(): Message[] {
    return [{
      id: "1",
      content: "欢迎使用AI数据助手！您可以在这里创建新的数据任务，我会帮您从文件中提取知识片段。",
      type: "incoming" as const,
      timestamp: new Date(Date.now() - 1000 * 60 * 5)
    }]
  }
  const [messages, setMessages] = useState<Message[]>(initialMessages.length > 0 ? initialMessages : welcomeMessages())
  const [inputValue, setInputValue] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const scrollAreaRef = useRef<HTMLDivElement>(null)

  // 当resetTrigger改变时，重置消息和输入框
  useEffect(() => {
    if (resetTrigger !== undefined) {
      setMessages(welcomeMessages())
      setInputValue("")
    }
  }, [resetTrigger])

  // 当sessionId改变时，加载该会话的聊天记录
  useEffect(() => {
    const loadSessionMessages = async () => {
      // 如果正在加载中（发送消息），不要重新加载消息
      if (isLoading) {
        console.log('[AiSdkChat] Skipping message reload during loading')
        return
      }
      
      if (!sessionId) {
        // 没有sessionId时显示欢迎消息
        setMessages(welcomeMessages())
        return
      }

      try {
        const sessionIdNum = parseInt(sessionId)
        if (isNaN(sessionIdNum)) {
          console.error('Invalid sessionId:', sessionId)
          return
        }

        console.log('🔄 加载会话聊天记录, sessionId:', sessionIdNum)
        const result = await getSessionMessages(sessionIdNum, 1, 50, false) // 获取前50条消息，时间升序
        
        // 将ChatMessage转换为Message格式
        const convertedMessages: Message[] = result.messages.map((msg: ChatMessage) => ({
          id: msg.message_id || msg.id.toString(),
          content: msg.content,
          type: msg.role === 'user' ? 'outgoing' : 'incoming',
          timestamp: new Date(msg.created_at),
        }))

        if (convertedMessages.length === 0) {
          // 如果没有消息，显示欢迎消息
          setMessages(welcomeMessages())
        } else {
          setMessages(convertedMessages)
        }

        console.log('✅ 聊天记录加载完成，消息数量:', convertedMessages.length)
      } catch (error) {
        console.error('Failed to load session messages:', error)
        // 加载失败时显示欢迎消息
        setMessages(welcomeMessages())
      }
    }

    loadSessionMessages()
  }, [sessionId, isLoading])

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

    console.log('[AiSdkChat] Created assistant message with ID:', assistantMessage.id)

    // 确保assistant消息被添加到状态中
    await new Promise<void>(resolve => {
      setMessages(prev => {
        const updated = [...prev, assistantMessage]
        console.log('[AiSdkChat] Added assistant message to state, current count:', updated.length)
        resolve()
        return updated
      })
    })

    // 短暂延迟确保状态更新完成
    await new Promise(resolve => setTimeout(resolve, 10))

    try {
      console.log('[AiSdkChat] Starting stream request with input:', currentInput)

      // 检查是否需要创建会话（延迟创建逻辑）
      let effectiveSessionId = sessionId
      
      if (!sessionId && onCreateSessionFromMessage) {
        // 如果没有会话ID且有会话创建回调，先创建新会话
        try {
          console.log('[AiSdkChat] Creating new session before sending message')
          const newSession = await onCreateSessionFromMessage(currentInput)
          effectiveSessionId = String(newSession.id)
          console.log('[AiSdkChat] Created new session:', newSession.id, 'Name:', newSession.name)
        } catch (error) {
          console.error('[AiSdkChat] Failed to create session:', error)
          // 如果会话创建失败，继续使用无会话ID的方式发送消息
        }
      }

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
      
      // 只有真实的会话ID才传递给后端
      if (effectiveSessionId && !isNaN(Number(effectiveSessionId))) {
        payload.session_id = Number(effectiveSessionId)
        console.log('[AiSdkChat] Using session_id for API call:', payload.session_id)
      } else {
        console.log('[AiSdkChat] No valid session_id, sending message without session binding')
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

      console.log('[AiSdkChat] Starting to read stream...')

      // 实时更新函数 - 不添加人工延迟，保持自然流式效果
      const updateMessageContent = (content: string) => {
        setMessages(prev => {
          const updated = prev.map(msg =>
            msg.id === assistantMessage.id
              ? { ...msg, content: content }
              : msg
          )
          return updated
        })
        // 使用requestAnimationFrame确保DOM更新后再滚动
        requestAnimationFrame(() => scrollToBottom())
      }

      // 实现AI SDK v5的textStream模式
      while (true) {
        const { done, value } = await reader.read()
        
        if (done) {
          console.log('[AiSdkChat] Stream completed')
          break
        }

        const chunk = decoder.decode(value, { stream: true })
        buffer += chunk
        
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
                
                // 处理AI SDK v5格式的流事件
                if (parsed.type === 'text-delta') {
                  if (parsed.delta) {
                    accumulatedContent += parsed.delta
                    
                    // 使用打字机效果更新内容
                    updateMessageContent(accumulatedContent)
                  } else {
                    console.log('[AiSdkChat] WARNING: text-delta event has no delta property')
                  }
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
                  className={`rounded-xl max-w-4/5 sm:w-auto px-3 py-2 ${
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
                          className="text-sm"
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
