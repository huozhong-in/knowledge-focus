/**
 * 前端工具通道 - 处理来自Python后端的工具调用请求
 * 
 * 此模块负责：
 * 1. 接收来自Python的工具调用请求
 * 2. 执行对应的TypeScript工具函数
 * 3. 将执行结果返回给Python后端
 */

import { toast } from 'sonner';

// 工具调用请求的数据类型
interface ToolCallRequest {
  call_id: string;
  tool_name: string;
  args: Record<string, any>;
  timeout?: number;
  timestamp?: number;
}

// 工具调用响应的数据类型
interface ToolCallResponse {
  call_id: string;
  success: boolean;
  result?: any;
  error?: string;
  duration?: number;
}

// 工具处理函数的类型
type ToolHandler = (args: Record<string, any>) => Promise<any> | any;

export class ToolChannel {
  private toolHandlers = new Map<string, ToolHandler>();
  private apiBaseUrl: string;

  constructor(apiBaseUrl: string = 'http://localhost:60315') {
    this.apiBaseUrl = apiBaseUrl;
  }

  /**
   * 注册工具处理函数
   */
  registerTool(name: string, handler: ToolHandler) {
    this.toolHandlers.set(name, handler);
    console.log(`✅ 工具已注册: ${name}`);
  }

  /**
   * 批量注册工具
   */
  registerTools(tools: Record<string, ToolHandler>) {
    Object.entries(tools).forEach(([name, handler]) => {
      this.registerTool(name, handler);
    });
  }

  /**
   * 处理来自Python的工具调用请求
   */
  async handleToolCall(request: ToolCallRequest): Promise<void> {
    const { call_id, tool_name, args } = request;
    const startTime = performance.now();

    console.log(`🔧 收到工具调用请求: ${tool_name} (call_id: ${call_id})`);

    try {
      // 检查工具是否已注册
      const handler = this.toolHandlers.get(tool_name);
      if (!handler) {
        throw new Error(`Tool '${tool_name}' not found. Available tools: ${Array.from(this.toolHandlers.keys()).join(', ')}`);
      }

      // 执行工具函数
      const result = await Promise.resolve(handler(args));
      const duration = (performance.now() - startTime) / 1000;

      // 发送成功响应
      await this.sendResponse({
        call_id,
        success: true,
        result,
        duration
      });

      console.log(`✅ 工具执行成功: ${tool_name} (耗时: ${duration.toFixed(2)}s)`);

    } catch (error) {
      const duration = (performance.now() - startTime) / 1000;
      const errorMessage = error instanceof Error ? error.message : String(error);

      console.error(`❌ 工具执行失败: ${tool_name} - ${errorMessage}`);

      // 发送失败响应
      await this.sendResponse({
        call_id,
        success: false,
        error: errorMessage,
        duration
      });

      // 显示错误提示
      toast.error(`工具执行失败: ${tool_name}`, {
        description: errorMessage,
        duration: 5000
      });
    }
  }

  /**
   * 发送响应给Python后端
   */
  private async sendResponse(response: ToolCallResponse): Promise<void> {
    try {
      const apiResponse = await fetch(`${this.apiBaseUrl}/tools/response`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(response),
      });

      if (!apiResponse.ok) {
        throw new Error(`HTTP ${apiResponse.status}: ${apiResponse.statusText}`);
      }

      console.log(`📤 工具响应已发送: call_id=${response.call_id}, success=${response.success}`);

    } catch (error) {
      console.error(`❌ 发送工具响应失败:`, error);
      toast.error('发送工具响应失败', {
        description: error instanceof Error ? error.message : String(error)
      });
    }
  }

  /**
   * 获取已注册的工具列表
   */
  getRegisteredTools(): string[] {
    return Array.from(this.toolHandlers.keys());
  }

  /**
   * 移除工具注册
   */
  unregisterTool(name: string): boolean {
    const removed = this.toolHandlers.delete(name);
    if (removed) {
      console.log(`🗑️ 工具已移除: ${name}`);
    }
    return removed;
  }
}

// 全局工具通道实例
export const toolChannel = new ToolChannel();

// 导出便捷的注册函数
export const registerTool = toolChannel.registerTool.bind(toolChannel);
export const registerTools = toolChannel.registerTools.bind(toolChannel);
export const handleToolCall = toolChannel.handleToolCall.bind(toolChannel);

// 调试函数
export const debugToolChannel = () => {
  console.log('🔍 工具通道调试信息:');
  console.log('已注册的工具:', toolChannel.getRegisteredTools());
  console.log('API基础URL:', (toolChannel as any).apiBaseUrl);
};
