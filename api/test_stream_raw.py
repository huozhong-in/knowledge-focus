"""
使用OpenAI SDK测试流式响应
"""
from openai import OpenAI

def test_openai_sdk_stream():
    """使用OpenAI SDK测试流式响应"""
    # 创建客户端,指向本地API
    client = OpenAI(
        base_url="http://127.0.0.1:60315/v1",
        api_key="dummy"  # 本地API不需要真实key
    )
    
    print("=" * 80)
    print("使用 OpenAI SDK 测试流式响应")
    print("=" * 80)
    
    try:
        stream = client.chat.completions.create(
            model="qwen3-vl-4b",
            messages=[
                {"role": "user", "content": "为什么天空是蓝色的？"}
            ],
            stream=True,
            max_tokens=512
        )
        
        print("\n📥 流式响应内容:\n")
        
        chunk_count = 0
        total_content = ""
        
        for chunk in stream:
            chunk_count += 1
            
            # 显示完整chunk对象
            print(f"\n[Chunk {chunk_count}]")
            print(f"  ID: {chunk.id}")
            print(f"  Model: {chunk.model}")
            print(f"  Choices: {len(chunk.choices) if chunk.choices else 0}")
            
            if chunk.choices and len(chunk.choices) > 0:
                choice = chunk.choices[0]
                print(f"  Index: {choice.index}")
                print(f"  Delta: {choice.delta}")
                print(f"  Finish reason: {choice.finish_reason}")
                
                # 提取content
                content = getattr(choice.delta, 'content', None)
                if content:
                    print(f"  ✅ Content: {repr(content)}")
                    total_content += content
                else:
                    print(f"  ⚠️  Content: None")
            else:
                print(f"  ❌ No choices in this chunk")
        
        print("\n" + "=" * 80)
        print(f"✅ 总共接收: {chunk_count} chunks")
        print(f"✅ 完整内容: {repr(total_content)}")
        print(f"✅ 内容长度: {len(total_content)} 字符")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_openai_sdk_stream()
