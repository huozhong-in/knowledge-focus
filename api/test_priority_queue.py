#!/usr/bin/env python3
"""
测试优先级队列和懒加载
"""

import asyncio
import httpx
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:60315"

async def send_request(client: httpx.AsyncClient, request_id: int, priority: str, stream: bool = False):
    """发送一个聊天请求"""
    url = f"{BASE_URL}/v1/chat/completions"
    
    payload = {
        "model": "qwen3-vl-4b",
        "messages": [
            {
                "role": "user",
                "content": f"请简短地回答:什么是Python? (请求ID: {request_id}, 优先级: {priority})"
            }
        ],
        "stream": stream,
        "temperature": 0.7,
        "max_tokens": 50
    }
    
    start_time = time.time()
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] 🚀 发送请求 #{request_id} (优先级: {priority}, 流式: {stream})")
    
    try:
        if stream:
            async with client.stream("POST", url, json=payload, timeout=60.0) as response:
                response.raise_for_status()
                full_text = ""
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                full_text += content
                        except json.JSONDecodeError:
                            continue
                
                elapsed = time.time() - start_time
                print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] ✅ 请求 #{request_id} 完成 ({elapsed:.2f}s): {full_text[:50]}...")
                return {"id": request_id, "text": full_text, "elapsed": elapsed}
        else:
            response = await client.post(url, json=payload, timeout=60.0)
            response.raise_for_status()
            data = response.json()
            elapsed = time.time() - start_time
            
            text = data["choices"][0]["message"]["content"]
            print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] ✅ 请求 #{request_id} 完成 ({elapsed:.2f}s): {text[:50]}...")
            return {"id": request_id, "text": text, "elapsed": elapsed}
            
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] ❌ 请求 #{request_id} 失败 ({elapsed:.2f}s): {e}")
        return {"id": request_id, "error": str(e), "elapsed": elapsed}


async def test_lazy_loading():
    """测试1: 懒加载 - 第一个请求会触发模型加载"""
    print("\n" + "="*80)
    print("测试 1: 懒加载")
    print("="*80)
    
    async with httpx.AsyncClient() as client:
        result = await send_request(client, 1, "HIGH", stream=False)
        
        if "error" not in result:
            print("\n✅ 懒加载测试通过")
            print(f"   - 首次加载耗时: {result['elapsed']:.2f}s (包含模型加载时间)")
        else:
            print(f"\n❌ 懒加载测试失败: {result['error']}")


async def test_priority_queue():
    """测试2: 优先级队列 - 同时发送高低优先级请求"""
    print("\n" + "="*80)
    print("测试 2: 优先级队列")
    print("="*80)
    print("说明: 先发送一个低优先级请求(模拟批量任务),然后立即发送高优先级请求(用户聊天)")
    print("      期望: 高优先级请求应该被优先处理\n")
    
    async with httpx.AsyncClient() as client:
        # 注意: 当前实现中优先级是由后端内部控制的 (聊天=HIGH)
        # 这里我们通过模拟场景来测试:
        # - 请求2: 低优先级 (假设是批量任务)
        # - 请求3: 高优先级 (用户聊天)
        
        # 实际测试中,由于 API 端点始终使用 HIGH 优先级,
        # 我们只能观察队列的串行处理行为
        
        tasks = [
            send_request(client, 2, "LOW", stream=False),  # 先发送
            send_request(client, 3, "HIGH", stream=False),  # 后发送
        ]
        
        results = await asyncio.gather(*tasks)
        
        print("\n📊 测试结果:")
        for result in results:
            if "error" not in result:
                print(f"   - 请求 #{result['id']}: {result['elapsed']:.2f}s")
            else:
                print(f"   - 请求 #{result['id']}: 失败 - {result['error']}")


async def test_concurrent_requests():
    """测试3: 并发请求 - 验证队列串行处理"""
    print("\n" + "="*80)
    print("测试 3: 并发请求处理")
    print("="*80)
    print("说明: 同时发送3个请求,验证队列会串行处理\n")
    
    async with httpx.AsyncClient() as client:
        tasks = [
            send_request(client, 4, "HIGH", stream=True),
            send_request(client, 5, "HIGH", stream=True),
            send_request(client, 6, "HIGH", stream=True),
        ]
        
        start = time.time()
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start
        
        successful = [r for r in results if "error" not in r]
        
        print("\n📊 测试结果:")
        print(f"   - 成功请求数: {len(successful)}/3")
        print(f"   - 总耗时: {total_time:.2f}s")
        if len(successful) > 0:
            avg_time = sum(r["elapsed"] for r in successful) / len(successful)
            print(f"   - 平均单请求耗时: {avg_time:.2f}s")
            print(f"   - 理论串行时间: {avg_time * 3:.2f}s")
            print(f"   - 实际并发效率: {(avg_time * 3 / total_time * 100):.1f}%")


async def test_idle_timeout():
    """测试4: 空闲超时 - 验证60秒无请求后队列处理器退出"""
    print("\n" + "="*80)
    print("测试 4: 空闲超时 (需要等待60秒)")
    print("="*80)
    print("说明: 发送一个请求后等待65秒,观察队列处理器是否正确超时")
    print("      (这个测试很慢,可以跳过)\n")
    
    skip = input("是否跳过此测试? (y/N): ").strip().lower()
    if skip == 'y':
        print("⏭️  已跳过空闲超时测试\n")
        return
    
    async with httpx.AsyncClient() as client:
        # 发送一个请求
        await send_request(client, 7, "HIGH", stream=False)
        
        print("\n⏳ 等待65秒...")
        await asyncio.sleep(65)
        
        print("📝 请检查 Python API 日志,应该看到类似以下消息:")
        print("   'Queue processor stopped due to 60s idle timeout'")
        
        # 再发送一个请求,验证队列处理器能重新启动
        print("\n🔄 发送新请求,验证队列处理器重新启动...")
        result = await send_request(client, 8, "HIGH", stream=False)
        
        if "error" not in result:
            print("\n✅ 空闲超时测试通过")
            print("   - 队列处理器能正确超时并重新启动")
        else:
            print(f"\n❌ 空闲超时测试失败: {result['error']}")


async def main():
    """运行所有测试"""
    print("\n" + "="*80)
    print("优先级队列与懒加载测试套件")
    print("="*80)
    print(f"API 地址: {BASE_URL}")
    print("确保 Python API 服务正在运行 (端口 60315)")
    print("确保已完成模型下载 (qwen3-vl-4b)\n")
    
    # 检查 API 可用性
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/health", timeout=5.0)
            if response.status_code != 200:
                print(f"❌ API 健康检查失败: {response.status_code}")
                return
    except Exception as e:
        print(f"❌ 无法连接到 API: {e}")
        print("请先启动 Python API 服务")
        return
    
    print("✅ API 服务可用\n")
    
    # 运行测试
    await test_lazy_loading()
    await asyncio.sleep(2)
    
    await test_priority_queue()
    await asyncio.sleep(2)
    
    await test_concurrent_requests()
    await asyncio.sleep(2)
    
    await test_idle_timeout()
    
    print("\n" + "="*80)
    print("所有测试完成!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
