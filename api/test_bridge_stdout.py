#!/usr/bin/env python3
"""
测试桥接事件的stdout输出能力

此脚本用于验证bridge_events.py能否在uvicorn环境下正确输出到stdout
"""


import time
from bridge_events import BridgeEventSender, test_stdout_accessibility

def test_bridge_stdout_main():
    print("=== 桥接事件stdout测试 ===")
    
    # 测试原始stdout可访问性
    print("1. 测试原始stdout可访问性...")
    if test_stdout_accessibility():
        print("✓ 原始stdout可访问")
    else:
        print("✗ 原始stdout不可访问")
        return
    
    # 测试桥接事件发送
    print("\n2. 测试桥接事件发送...")
    sender = BridgeEventSender(source="test-script")
    
    # 发送测试事件
    test_events = [
        ("stdout-test-1", {"message": "这是第一个stdout测试事件"}),
        ("stdout-test-2", {"message": "这是第二个stdout测试事件", "number": 42}),
        ("tags-updated", {"description": "stdout测试中的标签更新"}),
    ]
    
    for event_name, payload in test_events:
        print(f"发送事件: {event_name}")
        sender.send_event(event_name, payload)
        time.sleep(0.5)  # 短暂延时
    
    print("\n3. 测试完成")
    print("如果Rust端正常工作，应该能捕获到上述EVENT_NOTIFY_JSON消息")

if __name__ == "__main__":
    test_bridge_stdout_main()
