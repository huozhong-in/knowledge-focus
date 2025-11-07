"""
测试 MLX 服务的超时保护机制

验证：
1. 非流式响应超时保护
2. 流式响应超时保护
3. 超时后的错误处理
"""
import asyncio
import httpx
# from builtin_openai_compat import OpenAIChatCompletionRequest, ChatMessage

# MLX 服务地址
MLX_SERVICE_URL = "http://127.0.0.1:60316/v1/chat/completions"

async def test_non_streaming_timeout():
    """测试非流式响应的超时机制"""
    print("\n" + "="*60)
    print("测试 1: 非流式响应超时保护")
    print("="*60)
    
    # 构造一个可能导致超长响应的请求（但仍在合理范围内）
    request_data = {
        "model": "qwen3-vl-4b",
        "messages": [
            {
                "role": "user",
                "content": "请详细介绍Python编程语言的历史、特点和应用场景"
            }
        ],
        "max_tokens": 100,  # 小 token 数应该很快完成
        "temperature": 0.7,
        "stream": False
    }
    
    print(f"📤 发送请求: max_tokens={request_data['max_tokens']}")
    print(f"   预期超时时间: ~30 + {request_data['max_tokens']} * 0.2 = ~50秒")
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(MLX_SERVICE_URL, json=request_data)
            result = response.json()
            
            if "choices" in result:
                content = result["choices"][0]["message"]["content"]
                print("✅ 请求成功完成")
                print(f"   响应长度: {len(content)} 字符")
                print(f"   内容预览: {content[:100]}...")
            else:
                print(f"❌ 响应格式异常: {result}")
                
    except httpx.TimeoutException:
        print("❌ HTTP 客户端超时（60秒）")
    except Exception as e:
        print(f"❌ 请求失败: {e}")

async def test_streaming_timeout():
    """测试流式响应的超时机制"""
    print("\n" + "="*60)
    print("测试 2: 流式响应超时保护")
    print("="*60)
    
    request_data = {
        "model": "qwen3-vl-4b",
        "messages": [
            {
                "role": "user",
                "content": "列举Python的5个优点"
            }
        ],
        "max_tokens": 150,
        "temperature": 0.7,
        "stream": True
    }
    
    print(f"📤 发送流式请求: max_tokens={request_data['max_tokens']}")
    print(f"   预期超时时间: ~60 + {request_data['max_tokens']} * 0.3 = ~105秒")
    print("   单个 chunk 超时: 30秒")
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", MLX_SERVICE_URL, json=request_data) as response:
                print("✅ 开始接收流式响应:")
                print("   ", end="", flush=True)
                
                chunk_count = 0
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str and data_str != "[DONE]":
                            try:
                                import json
                                data = json.loads(data_str)
                                
                                # 检查错误
                                if "error" in data:
                                    print(f"\n❌ 流式响应错误: {data['error']}")
                                    break
                                
                                # 正常内容
                                if "choices" in data and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        print(content, end="", flush=True)
                                        chunk_count += 1
                            except json.JSONDecodeError:
                                pass
                
                print(f"\n✅ 流式响应完成，共 {chunk_count} 个 chunks")
                
    except httpx.TimeoutException:
        print("\n❌ HTTP 客户端超时（120秒）")
    except Exception as e:
        print(f"\n❌ 请求失败: {e}")

async def test_very_long_request():
    """测试超长请求的超时保护（应该触发超时）"""
    print("\n" + "="*60)
    print("测试 3: 超长请求超时保护（预期触发超时）")
    print("="*60)
    
    request_data = {
        "model": "qwen3-vl-4b",
        "messages": [
            {
                "role": "user",
                "content": "请写一篇10000字的关于人工智能发展历史的论文"
            }
        ],
        "max_tokens": 2000,  # 超长 token 数
        "temperature": 0.7,
        "stream": False
    }
    
    print(f"📤 发送超长请求: max_tokens={request_data['max_tokens']}")
    print(f"   预期超时时间: min(30 + {request_data['max_tokens']} * 0.2, 180) = 180秒")
    print("   （这个请求应该会触发超时保护）")
    
    try:
        async with httpx.AsyncClient(timeout=200.0) as client:
            response = await client.post(MLX_SERVICE_URL, json=request_data)
            result = response.json()
            
            if "error" in result:
                print(f"✅ 预期中的超时错误: {result['error']}")
            elif "choices" in result:
                content = result["choices"][0]["message"]["content"]
                print("⚠️  请求意外完成（可能 GPU 性能很好）")
                print(f"   响应长度: {len(content)} 字符")
            else:
                print(f"❌ 响应格式异常: {result}")
                
    except httpx.TimeoutException:
        print("❌ HTTP 客户端超时（200秒）")
    except Exception as e:
        print(f"⚠️  请求异常: {e}")
        # 这也可能是预期的超时行为

async def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("MLX 服务超时保护机制测试")
    print("="*60)
    print("⚠️  注意: 这些测试需要 MLX 服务正在运行 (端口 60316)")
    print()
    
    # 先检查服务是否可用
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://127.0.0.1:60316/health")
            if response.status_code == 200:
                print("✅ MLX 服务正在运行\n")
            else:
                print("❌ MLX 服务响应异常\n")
                return
    except Exception as e:
        print(f"❌ 无法连接到 MLX 服务: {e}")
        print("   请先启动 MLX 服务: python api/mlx_service.py --base-dir <path>\n")
        return
    
    try:
        # 测试 1: 正常请求（不应该超时）
        await test_non_streaming_timeout()
        
        # 测试 2: 流式请求（不应该超时）
        await test_streaming_timeout()
        
        # 测试 3: 超长请求（预期触发超时）
        # 注意: 这个测试可能需要很长时间，可以选择性运行
        # await test_very_long_request()
        
        print("\n" + "="*60)
        print("✅ 所有测试完成！")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
