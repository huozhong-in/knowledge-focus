"""
简化的 OpenAI 兼容接口测试
"""
import httpx

def test_simple():
    """测试基本功能"""
    print("=" * 80)
    print("测试 /v1/chat/completions 接口")
    print("=" * 80)
    
    # 测试1: 纯文本对话
    print("\n1. 测试纯文本对话...")
    try:
        response = httpx.post(
            "http://127.0.0.1:60315/v1/chat/completions",
            json={
                "model": "qwen3-vl-4b",
                "messages": [
                    {"role": "user", "content": "What is skey is blue?"}
                ],
                "max_tokens": 512,
                "temperature": 0.7
            },
            timeout=30.0
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 响应成功")
            print(f"   模型: {result.get('model')}")
            print(f"   内容: {result}")
            print(f"   Token 使用: {result['usage']['total_tokens']}")
        else:
            print(f"❌ 请求失败: {response.status_code}")
            print(f"   {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 80)
    print("✅ 测试通过！")
    print("=" * 80)
    return True

if __name__ == "__main__":
    import sys
    success = test_simple()
    sys.exit(0 if success else 1)
