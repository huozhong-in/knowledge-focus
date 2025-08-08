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
  stats?: {
    message_count: number
    pinned_file_count: number
  }
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
