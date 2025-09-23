/**
 * 聊天会话管理API客户端
 */

const API_BASE_URL = 'http://localhost:60315'

export interface ChatSession {
  id: number
  name: string
  created_at: string
  updated_at: string
  metadata: Record<string, any>
  is_active: boolean
  scenario_id?: number | null
  stats?: {
    message_count: number
    pinned_file_count: number
  }
  // 前端恢复工具勾选：会话选择的工具名列表
  selected_tools?: string[]
  // 前端对话框预填：工具配置（目前仅用到 Tavily）
  tool_configs?: Record<string, { has_api_key: boolean; api_key?: string }>
}

export interface ChatMessage {
  id: number
  message_id: string
  role: 'user' | 'assistant'
  content: string
  parts: Array<{
    type: string
    text?: string
    [key: string]: any
  }>
  metadata: Record<string, any>
  sources: Array<any>
  created_at: string
}

export interface PinnedFile {
  id: number
  file_path: string
  file_name: string
  pinned_at: string
  metadata: Record<string, any>
}

export interface ApiResponse<T> {
  success: boolean
  data: T
  message?: string
}

export interface SessionsResponse {
  success: boolean
  data: {
    sessions: ChatSession[]
    pagination: {
      page: number
      page_size: number
      total: number
      pages: number
    }
  }
}

export interface MessagesResponse {
  success: boolean
  data: {
    messages: ChatMessage[]
    pagination: {
      page: number
      page_size: number
      total: number
      pages: number
    }
  }
}

// ==================== 会话管理 ====================

export async function createSession(name?: string, metadata?: Record<string, any>): Promise<ChatSession> {
  const response = await fetch(`${API_BASE_URL}/chat/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      name,
      metadata: metadata || {}
    }),
  })

  if (!response.ok) {
    throw new Error(`Failed to create session: ${response.statusText}`)
  }

  const result: ApiResponse<ChatSession> = await response.json()
  if (!result.success) {
    throw new Error(result.message || 'Failed to create session')
  }

  return result.data
}

export async function createSmartSession(firstMessageContent: string, metadata?: Record<string, any>): Promise<ChatSession> {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/smart`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      first_message_content: firstMessageContent,
      metadata: metadata || {}
    }),
  })

  if (!response.ok) {
    throw new Error(`Failed to create smart session: ${response.statusText}`)
  }

  const result: ApiResponse<ChatSession> = await response.json()
  if (!result.success) {
    throw new Error(result.message || 'Failed to create smart session')
  }

  return result.data
}

export async function getSessions(
  page = 1,
  pageSize = 20,
  search?: string
): Promise<{ sessions: ChatSession[], total: number, pages: number }> {
  const params = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
  })
  
  if (search) {
    params.append('search', search)
  }

  const response = await fetch(`${API_BASE_URL}/chat/sessions?${params}`)
  
  if (!response.ok) {
    throw new Error(`Failed to get sessions: ${response.statusText}`)
  }

  const result: SessionsResponse = await response.json()
  if (!result.success) {
    throw new Error('Failed to get sessions')
  }

  return {
    sessions: result.data.sessions,
    total: result.data.pagination.total,
    pages: result.data.pagination.pages
  }
}

export async function getSession(sessionId: number): Promise<ChatSession> {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}`)
  
  if (!response.ok) {
    throw new Error(`Failed to get session: ${response.statusText}`)
  }

  const result: ApiResponse<ChatSession> = await response.json()
  if (!result.success) {
    throw new Error(result.message || 'Failed to get session')
  }

  return result.data
}

// ==================== 工具管理 ====================

export async function changeSessionTools(
  sessionId: number,
  addTools?: string[],
  removeTools?: string[],
): Promise<boolean> {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}/tools`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      add_tools: addTools || [],
      remove_tools: removeTools || [],
    }),
  })

  if (!response.ok) {
    throw new Error(`Failed to change session tools: ${response.statusText}`)
  }

  const result: ApiResponse<{ success: boolean }> = await response.json()
  if (!result.success) {
    throw new Error(result.message || 'Failed to change session tools')
  }
  return true
}

// export async function getMcpToolApiKey(toolName: string): Promise<string> {
//   const url = `${API_BASE_URL}/tools/mcp/get_api_key?tool_name=${encodeURIComponent(toolName)}`
//   const response = await fetch(url)
//   if (!response.ok) {
//     return ''
//   }
//   const json = await response.json()
//   if (json?.success && typeof json?.api_key === 'string') {
//     return json.api_key as string
//   }
//   return ''
// }

export async function setMcpToolApiKey(toolName: string, apiKey: string): Promise<boolean> {
  const url = `${API_BASE_URL}/tools/mcp/set_api_key?tool_name=${encodeURIComponent(toolName)}&api_key=${encodeURIComponent(apiKey)}`
  const response = await fetch(url, { method: 'POST' })
  if (!response.ok) return false
  const json = await response.json()
  return !!json?.success
}

export async function updateSession(
  sessionId: number, 
  name?: string, 
  metadata?: Record<string, any>
): Promise<ChatSession> {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      name,
      metadata
    }),
  })

  if (!response.ok) {
    throw new Error(`Failed to update session: ${response.statusText}`)
  }

  const result: ApiResponse<ChatSession> = await response.json()
  if (!result.success) {
    throw new Error(result.message || 'Failed to update session')
  }

  return result.data
}

export async function deleteSession(sessionId: number): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    throw new Error(`Failed to delete session: ${response.statusText}`)
  }

  const result: ApiResponse<any> = await response.json()
  if (!result.success) {
    throw new Error(result.message || 'Failed to delete session')
  }
}

// ==================== 消息管理 ====================

export async function getSessionMessages(
  sessionId: number,
  page = 1,
  pageSize = 30,
  latestFirst = false
): Promise<{ messages: ChatMessage[], total: number, pages: number }> {
  const params = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
    latest_first: latestFirst.toString(),
  })

  const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}/messages?${params}`)
  
  if (!response.ok) {
    throw new Error(`Failed to get messages: ${response.statusText}`)
  }

  const result: MessagesResponse = await response.json()
  if (!result.success) {
    throw new Error('Failed to get messages')
  }

  return {
    messages: result.data.messages,
    total: result.data.pagination.total,
    pages: result.data.pagination.pages
  }
}

// ==================== Pin文件管理 ====================

export async function getPinnedFiles(sessionId: number): Promise<PinnedFile[]> {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}/pinned-files`)
  
  if (!response.ok) {
    throw new Error(`Failed to get pinned files: ${response.statusText}`)
  }

  const result: ApiResponse<{ pinned_files: PinnedFile[] }> = await response.json()
  if (!result.success) {
    throw new Error('Failed to get pinned files')
  }

  return result.data.pinned_files
}

export async function pinFile(
  sessionId: number,
  filePath: string,
  fileName: string,
  metadata?: Record<string, any>
): Promise<PinnedFile> {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}/pin-file`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      file_path: filePath,
      file_name: fileName,
      metadata: metadata || {}
    }),
  })

  if (!response.ok) {
    throw new Error(`Failed to pin file: ${response.statusText}`)
  }

  const result: ApiResponse<PinnedFile> = await response.json()
  if (!result.success) {
    throw new Error(result.message || 'Failed to pin file')
  }

  return result.data
}

export async function unpinFile(sessionId: number, filePath: string): Promise<void> {
  const params = new URLSearchParams({
    file_path: filePath,
  })

  const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}/pinned-files?${params}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    throw new Error(`Failed to unpin file: ${response.statusText}`)
  }

  const result: ApiResponse<any> = await response.json()
  if (!result.success) {
    throw new Error(result.message || 'Failed to unpin file')
  }
}

// ==================== 会话场景管理 ====================

/**
 * 重新激活PDF阅读器窗口
 * 直接调用前端的 handleActivatePdfReader 来激活PDF窗口并使其可见
 */
export async function reactivatePdfWindow(pdfPath: string): Promise<boolean> {
  try {
    // 直接调用前端的PDF激活工具
    const { handleActivatePdfReader } = await import('../lib/pdfCoReadingTools')
    
    const result = await handleActivatePdfReader({ pdfPath })
    
    if (result) {
      console.log('PDF窗口激活成功:', result)
      return true
    } else {
      console.warn('PDF窗口激活失败，可能窗口不存在或已关闭')
      return false
    }
  } catch (error) {
    console.error('重新激活PDF窗口失败:', error)
    return false
  }
}

export async function enterCoReadingMode(sessionId: number, pdfPath: string): Promise<ChatSession> {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}/scenario`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      action: 'enter_co_reading',
      pdf_path: pdfPath
    }),
  })

  if (!response.ok) {
    throw new Error(`Failed to enter co-reading mode: ${response.statusText}`)
  }

  const result: ApiResponse<ChatSession> = await response.json()
  if (!result.success) {
    throw new Error(result.message || 'Failed to enter co-reading mode')
  }

  return result.data
}

export async function exitCoReadingMode(sessionId: number): Promise<ChatSession> {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}/scenario`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      action: 'exit_co_reading'
    }),
  })

  if (!response.ok) {
    throw new Error(`Failed to exit co-reading mode: ${response.statusText}`)
  }

  const result: ApiResponse<ChatSession> = await response.json()
  if (!result.success) {
    throw new Error(result.message || 'Failed to exit co-reading mode')
  }

  return result.data
}

// ==================== 工具函数 ====================

export function groupSessionsByTime(sessions: ChatSession[]): Array<{
  period: string
  chat_sessions: Array<{
    id: string
    title: string
    icon: any
    session: ChatSession
  }>
}> {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000)
  const sevenDaysAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000)
  const thirtyDaysAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000)

  const groups = {
    today: [] as ChatSession[],
    yesterday: [] as ChatSession[],
    sevenDays: [] as ChatSession[],
    thirtyDays: [] as ChatSession[],
    older: [] as ChatSession[],
  }

  sessions.forEach(session => {
    const updatedAt = new Date(session.updated_at)
    
    if (updatedAt >= today) {
      groups.today.push(session)
    } else if (updatedAt >= yesterday) {
      groups.yesterday.push(session)
    } else if (updatedAt >= sevenDaysAgo) {
      groups.sevenDays.push(session)
    } else if (updatedAt >= thirtyDaysAgo) {
      groups.thirtyDays.push(session)
    } else {
      groups.older.push(session)
    }
  })

  const result = []
  
  if (groups.today.length > 0) {
    result.push({
      period: "Today",
      chat_sessions: groups.today.map(session => ({
        id: session.id.toString(),
        title: session.name,
        icon: null, // 将在组件中设置
        session
      }))
    })
  }
  
  if (groups.yesterday.length > 0) {
    result.push({
      period: "Yesterday",
      chat_sessions: groups.yesterday.map(session => ({
        id: session.id.toString(),
        title: session.name,
        icon: null,
        session
      }))
    })
  }
  
  if (groups.sevenDays.length > 0) {
    result.push({
      period: "Previous 7 Days",
      chat_sessions: groups.sevenDays.map(session => ({
        id: session.id.toString(),
        title: session.name,
        icon: null,
        session
      }))
    })
  }
  
  if (groups.thirtyDays.length > 0) {
    result.push({
      period: "Previous 30 Days",
      chat_sessions: groups.thirtyDays.map(session => ({
        id: session.id.toString(),
        title: session.name,
        icon: null,
        session
      }))
    })
  }
  
  if (groups.older.length > 0) {
    result.push({
      period: "Older",
      chat_sessions: groups.older.map(session => ({
        id: session.id.toString(),
        title: session.name,
        icon: null,
        session
      }))
    })
  }

  return result
}
