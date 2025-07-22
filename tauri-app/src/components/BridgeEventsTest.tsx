import { useEffect } from 'react';
import { useTagsUpdateListenerWithApiCheck } from '@/hooks/useBridgeEvents';

/**
 * 桥接事件监听器测试组件
 * 
 * 用于验证修复后的事件监听是否正常工作
 */
export function BridgeEventsTest() {
  useEffect(() => {
    console.log('🧪 桥接事件测试组件已挂载');
    return () => {
      console.log('🧪 桥接事件测试组件已卸载');
    };
  }, []);

  // 测试标签更新监听器
  useTagsUpdateListenerWithApiCheck(
    () => {
      console.log('🏷️ 收到标签更新事件 - 测试成功！');
    },
    true, // 假设API已就绪
    { showToasts: false }
  );

  return (
    <div className="p-4 border border-dashed border-gray-300 rounded">
      <h3 className="text-sm font-medium mb-2">桥接事件测试</h3>
      <p className="text-xs text-gray-600">
        此组件用于测试桥接事件监听器的修复效果
      </p>
      <p className="text-xs text-gray-500 mt-1">
        检查控制台是否出现 TypeError 错误
      </p>
    </div>
  );
}
