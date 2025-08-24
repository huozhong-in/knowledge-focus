/**
 * 工具注册初始化
 * 
 * 在应用启动时注册所有前端工具到工具通道
 */

import { registerTools } from './toolChannel';
import { pdfCoReadingTools } from './pdfCoReadingTools';

/**
 * 初始化并注册所有工具
 */
export function initializeTools() {
  console.log('🔧 开始初始化前端工具...');

  // 注册PDF共读工具
  registerTools(pdfCoReadingTools);

  // 这里可以注册其他工具模块
  // registerTools(otherTools);

  console.log('✅ 前端工具初始化完成');
}

// 立即执行初始化
initializeTools();
