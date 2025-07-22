#!/usr/bin/env python3
"""
测试事件缓冲系统

此脚本模拟高频标签更新场景，验证Rust端的事件缓冲功能
"""

import time
from bridge_events import BridgeEventSender

def test_event_buffering():
    """测试事件缓冲功能"""
    print("=== 事件缓冲系统测试 ===")
    
    sender = BridgeEventSender(source="buffering-test")
    
    # 测试场景1：高频标签更新（应该被缓冲合并）
    print("\n1. 测试高频标签更新事件（应该被缓冲到5秒后发送）")
    for i in range(10):
        sender.tags_updated(f"批量处理第{i+1}批标签")
        print(f"发送第{i+1}个tags-updated事件")
        time.sleep(0.3)  # 每300ms发送一次
    
    print("已发送10个tags-updated事件，预期：Rust端5秒后只发送最后一个")
    
    # 等待6秒，让缓冲的事件发送出去
    print("等待6秒让缓冲事件发送...")
    time.sleep(6)
    
    # 测试场景2：立即转发事件（不应该被缓冲）
    print("\n2. 测试立即转发事件（error-occurred，应该立即发送）")
    for i in range(3):
        sender.error_occurred("test_error", f"这是第{i+1}个错误", {"batch": i+1})
        print(f"发送第{i+1}个error-occurred事件")
        time.sleep(0.5)
    
    print("已发送3个error-occurred事件，预期：Rust端立即转发所有3个事件")
    
    # 测试场景3：节流事件
    print("\n3. 测试节流事件（progress类型，每秒最多1个）")
    for i in range(8):
        sender.progress_update("parsing", i*10, 100, f"解析进度 {i*10}%")
        print(f"发送第{i+1}个progress事件")
        time.sleep(0.3)  # 每300ms发送一次，但应该被节流到每秒1个
    
    print("已发送8个progress事件，预期：Rust端根据节流策略发送")
    
    # 等待足够时间让所有事件处理完成
    print("\n等待5秒让所有事件处理完成...")
    time.sleep(5)
    
    print("\n=== 测试完成 ===")
    print("请检查Rust端控制台输出，验证事件缓冲是否按预期工作")

if __name__ == "__main__":
    # 30秒倒计时
    for i in range(30, 0, -1):
        print(f"倒计时: {i}秒")
        time.sleep(1)
    test_event_buffering()
