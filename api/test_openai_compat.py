"""
测试 OpenAI 兼容的 /v1/chat/completions 接口
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

def test_openai_compat_api():
    """测试 OpenAI 兼容接口"""
    from openai import OpenAI
    
    # 创建 OpenAI 客户端（指向本地 API）
    client = OpenAI(
        base_url="http://127.0.0.1:60315/v1",
        api_key="dummy"  # 内置模型不需要真实 API key
    )
    
    print("=" * 80)
    print("测试 OpenAI 兼容的 /v1/chat/completions 接口")
    print("=" * 80)
    
    # 测试1: 纯文本对话
    print("\n1. 测试纯文本对话...")
    try:
        response = client.chat.completions.create(
            model="qwen3-vl-4b",  # 使用 model_id
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Why sky is blue?"}
            ],
            max_tokens=50,
            temperature=0.7
        )
        
        print("✅ 响应成功")
        print(f"   模型: {response.model}")
        print(f"   内容: {response.choices[0].message.content}")
        print(f"   Token 使用: {response.usage.total_tokens} "
              f"(prompt: {response.usage.prompt_tokens}, "
              f"completion: {response.usage.completion_tokens})")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 测试2: 视觉问答（多模态）
    print("\n2. 测试视觉问答（多模态）...")
    try:
        test_image = "/Users/dio/Downloads/Gvk2MmNaMAAxNnJ.jpeg"
        
        response = client.chat.completions.create(
            model="qwen3-vl-4b",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image in one sentence."},
                        {
                            "type": "image_url",
                            "image_url": {"url": test_image}
                        }
                    ]
                }
            ],
            max_tokens=100,
            temperature=0.7
        )
        
        print("✅ 视觉问答成功")
        print(f"   图片: {test_image}")
        print(f"   描述: {response.choices[0].message.content}")
        print(f"   Token 使用: {response.usage.total_tokens}")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 测试3: 流式响应
    print("\n3. 测试流式响应...")
    try:
        stream = client.chat.completions.create(
            model="qwen3-vl-4b",
            messages=[
                {"role": "user", "content": "Count from 1 to 5, one number per line."}
            ],
            max_tokens=50,
            temperature=0.7,
            stream=True
        )
        
        print("✅ 流式响应:")
        print("   ", end="")
        for chunk in stream:
            if chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print()  # 换行
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 80)
    print("✅ 所有测试通过！")
    print("=" * 80)
    return True

if __name__ == "__main__":
    success = test_openai_compat_api()
    sys.exit(0 if success else 1)
