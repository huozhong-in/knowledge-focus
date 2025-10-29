"""
最简测试：直接测试 OpenAI 兼容接口
"""
import requests
import json
from openai import AsyncOpenAI, OpenAI

def test_basic():
    """最基本的测试"""
    url = "http://127.0.0.1:60316/v1/chat/completions"
    
    payload = {
        "model": "qwen3-vl-4b",
        "messages": [
            {"role": "user", "content": "Hi, how are you doing today?"}
        ],
        "max_tokens": 512,
        "temperature": 0.7,
        "stream": False
    }
    
    print("=" * 80)
    print("测试 POST /v1/chat/completions")
    print("=" * 80)
    print(f"\n请求 URL: {url}")
    print(f"请求体:\n{json.dumps(payload, indent=2)}")
    print("\n发送请求...")
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        
        print(f"\n响应状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        print("\n响应体:")
        
        if response.status_code == 200:
            result = response.json()
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print("\n✅ 测试成功！")
            return True
        else:
            print(response.text)
            print("\n❌ 测试失败：状态码非 200")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False

async def run_openai_sdk_async_test():
    """使用 OpenAI SDK 测试"""
    print("=" * 80)
    print("使用 OpenAI SDK 测试")
    print("=" * 80)
    
    client = AsyncOpenAI(base_url="http://127.0.0.1:60316/v1", api_key="test-api-key")
    response = await client.chat.completions.create(
        model="qwen3-vl-4b",
        messages=[
            {"role": "user", "content": "说说拜占庭将军问题"}
        ],
        max_tokens=512,
        temperature=0.7,
        stream=True
    )
    print("\n响应流:")
    async for chunk in response:
        print(chunk.choices[0].delta.content, end="", flush=True)
        # print(chunk.model_dump_json(), flush=True)  # 打印完整的 chunk JSON 数据
    print("\n\n✅ SDK 测试完成！")

def run_openai_sdk_sync_test():
    """使用 OpenAI SDK 测试（同步版）"""
    print("=" * 80)
    print("使用 OpenAI SDK 测试（同步版）")
    print("=" * 80)
    
    client = OpenAI(base_url="http://127.0.0.1:60316/v1", api_key="test-api-key")
    response = client.chat.completions.create(
        model="qwen3-vl-4b",
        messages=[
            {"role": "user", "content": "说说拜占庭将军问题"}
        ],
        max_tokens=512,
        temperature=0.7,
        stream=False
    )
    print(response.model_dump_json(indent=2, ensure_ascii=False))

if __name__ == "__main__":
    # import sys
    # success = test_basic()
    # sys.exit(0 if success else 1)
    
    import asyncio
    asyncio.run(run_openai_sdk_async_test())
    
    # run_openai_sdk_sync_test()