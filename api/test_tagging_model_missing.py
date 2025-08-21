#!/usr/bin/env python3
"""
测试标签模型缺失事件的发送

这个脚本模拟标签生成模型缺失的情况，并发送相应的桥接事件。
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge_events import BridgeEventSender

def test_tagging_model_missing():
    """测试发送标签模型缺失事件"""
    print("=== 测试标签模型缺失事件 ===")
    
    sender = BridgeEventSender(source="test-script")
    
    # 发送标签模型缺失事件
    sender.tagging_model_missing(
        message="标签生成需要的模型未配置: base, embedding",
        details={
            "missing_capabilities": ["base", "embedding"],
            "required_for": "file_tagging",
            "suggestion": "请在AI模型配置页面配置相关模型"
        }
    )
    
    print("✅ 标签模型缺失事件已发送")
    print("前端应该收到 'tagging-model-missing' 事件并显示配置提示")

if __name__ == "__main__":
    print("开始测试标签模型缺失事件...")
    print("前端需要监听 'tagging-model-missing' 事件")
    print()
    
    test_tagging_model_missing()
    
    print()
    print("测试完成！检查前端是否收到事件并显示了相应的toast通知。")
