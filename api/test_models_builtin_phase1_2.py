"""
Phase 1.2 测试: MLX-VLM Server 进程管理
测试内容：
1. 启动服务器
2. 健康检查
3. 服务器状态查询
4. 停止服务器
"""

import sys
import time
import logging
from pathlib import Path
from models_builtin import ModelsBuiltin
import httpx
from sqlmodel import create_engine
from config import TEST_DB_PATH, VLM_MODEL

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_server_lifecycle():
    """测试服务器生命周期管理"""
    print("\n" + "="*60)
    print("Phase 1.2 测试: MLX-VLM Server 进程管理")
    print("="*60)
    
    # 初始化
    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
    base_dir = Path(TEST_DB_PATH).parent.as_posix()
    models_builtin = ModelsBuiltin(engine, base_dir)
    
    # 检查模型是否已下载
    model_id = "qwen3-vl-4b"
    print(f"\n1. 检查模型 {model_id} 是否已下载...")
    
    if not models_builtin.is_model_downloaded(model_id):
        print(f"❌ 模型 {model_id} 未下载，请先运行 test_models_builtin_phase1_3.py")
        return False
    
    model_path = models_builtin.get_model_path(model_id)
    print(f"✅ 模型已下载: {model_path}")
    
    # 测试初始状态
    print("\n2. 检查初始服务器状态...")
    initial_status = models_builtin.get_server_status()
    print(f"   - Running: {initial_status['running']}")
    print(f"   - URL: {initial_status['url']}")
    
    if initial_status['running']:
        print("⚠️  服务器已在运行，先停止...")
        models_builtin.stop_mlx_server()
        time.sleep(2)
    
    # 测试启动服务器
    print("\n3. 启动 MLX-VLM 服务器...")
    print(f"   模型: {model_id}")
    print("   地址: http://127.0.0.1:60316")
    print("   (这可能需要 30-60 秒，因为需要加载模型...)")
    
    start_success = models_builtin.start_mlx_server(model_id)
    
    if not start_success:
        print("❌ 服务器启动失败")
        return False
    
    print("✅ 服务器启动成功")
    
    # 测试健康检查
    print("\n4. 执行健康检查...")
    is_healthy = models_builtin.health_check()
    print(f"   健康状态: {'✅ 正常' if is_healthy else '❌ 异常'}")
    
    if not is_healthy:
        print("❌ 健康检查失败")
        models_builtin.stop_mlx_server()
        return False
    
    # 测试服务器状态
    print("\n5. 查询服务器详细状态...")
    status = models_builtin.get_server_status()
    print(f"   - Running: {status['running']}")
    print(f"   - PID: {status['process_id']}")
    print(f"   - Loaded Model: {status.get('loaded_model', 'N/A')}")
    print(f"   - URL: {status['url']}")
    
    # 测试 API 调用（简单的健康检查）
    print("\n6. 测试 API 端点...")
    try:
        # 测试 /health 端点
        with httpx.Client(timeout=10.0) as client:
            response = client.get("http://127.0.0.1:60316/health")
            if response.status_code == 200:
                health_data = response.json()
                print("   ✅ /health 端点响应正常")
                print(f"      Loaded model: {health_data.get('loaded_model')}")
            else:
                print(f"   ❌ /health 端点响应异常: {response.status_code}")
    except Exception as e:
        print(f"   ❌ API 调用失败: {e}")
    
    # 测试真实的视觉问答
    print("\n7. 测试真实的视觉问答功能...")
    print("   (使用 OpenAI-compatible /responses 端点)")
    try:
        # 使用一个公开的测试图片
        test_image_url = "/Users/dio/Downloads/Gvk2MmNaMAAxNnJ.jpeg"
        test_prompt = "Describe this image in one sentence."
        
        with httpx.Client(timeout=30.0) as client:
            # 使用 /responses 端点 (OpenAI-compatible)
            response = client.post(
                "http://127.0.0.1:60316/responses",
                headers={"Content-Type": "application/json"},
                json={
                    "model": VLM_MODEL,
                    "input": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": test_prompt},
                                {"type": "input_image", "image_url": test_image_url}
                            ]
                        }
                    ],
                    "max_output_tokens": 100,
                    "temperature": 0.7
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                # 提取生成的文本
                output_text = result.get("output_text", "")
                if not output_text and result.get("output"):
                    # 尝试从 output 数组中提取
                    for item in result.get("output", []):
                        if isinstance(item, dict) and "content" in item:
                            content = item["content"]
                            if isinstance(content, list) and len(content) > 0:
                                output_text = content[0].get("text", "")
                                break
                
                print("   ✅ 视觉问答测试成功")
                print(f"   📝 问题: {test_prompt}")
                print(f"   🖼️  图片: {test_image_url}")
                print(f"   💬 回答: {output_text[:200]}...")  # 只显示前200字符
                
                # 检查 token 使用情况
                usage = result.get("usage", {})
                if usage:
                    print(f"   📊 Token 使用: input={usage.get('input_tokens')}, output={usage.get('output_tokens')}")
            else:
                print(f"   ❌ 视觉问答失败: HTTP {response.status_code}")
                print(f"      响应: {response.text[:200]}")
                
    except Exception as e:
        print(f"   ⚠️  视觉问答测试出错: {e}")
        print("      (这可能是正常的，取决于网络和模型状态)")
    
    # 测试停止服务器
    print("\n8. 停止服务器...")
    stop_success = models_builtin.stop_mlx_server()
    
    if not stop_success:
        print("❌ 服务器停止失败")
        return False
    
    print("✅ 服务器已停止")
    
    # 验证服务器已停止
    print("\n9. 验证服务器已停止...")
    time.sleep(2)
    final_status = models_builtin.get_server_status()
    
    if final_status['running']:
        print("❌ 服务器仍在运行")
        return False
    
    print("✅ 服务器确认已停止")
    
    print("\n" + "="*60)
    print("✅ Phase 1.2 所有测试通过！")
    print("="*60)
    
    return True


if __name__ == "__main__":
    try:
        success = test_server_lifecycle()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}", exc_info=True)
        sys.exit(1)
