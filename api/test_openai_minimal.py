"""
最简测试：直接测试 OpenAI 兼容接口
"""
import requests
import json

def test_basic():
    """最基本的测试"""
    url = "http://127.0.0.1:60315/v1/chat/completions"
    
    payload = {
        "model": "qwen3-vl-4b",
        "messages": [
            {"role": "user", "content": "Say hello"}
        ],
        "max_tokens": 20,
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
        print(f"\n响应体:")
        
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

if __name__ == "__main__":
    import sys
    success = test_basic()
    sys.exit(0 if success else 1)
