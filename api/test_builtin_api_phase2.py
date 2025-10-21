"""
Phase 2 测试：API 端点验证
测试内容：
1. 测试获取内置模型列表
2. 测试服务器状态查询
3. 测试服务器启动/停止
4. 测试模型删除（可选）
"""

import httpx
import sys
import time
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_URL = "http://127.0.0.1:60315"  # 主 API 服务器地址


def test_builtin_api_endpoints():
    """测试内置模型管理 API 端点"""
    print("\n" + "="*60)
    print("Phase 2 测试：API 端点验证")
    print("="*60)
    
    client = httpx.Client(timeout=60.0)
    
    # 测试 1: 获取内置模型列表
    print("\n1. 测试获取内置模型列表...")
    print(f"   GET {BASE_URL}/models/builtin/list")
    
    try:
        response = client.get(f"{BASE_URL}/models/builtin/list")
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                models = data.get("data", [])
                print(f"   ✅ 成功获取 {len(models)} 个内置模型")
                for model in models:
                    print(f"      - {model['model_id']}: {model['display_name']}")
                    print(f"        Downloaded: {model['downloaded']}")
                    print(f"        Size: {model['size_mb']} MB")
            else:
                print(f"   ❌ API 返回失败: {data.get('message')}")
                return False
        else:
            print(f"   ❌ HTTP 错误: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
        print("   提示: 确保主 API 服务器正在运行 (python main.py)")
        return False
    
    # 测试 2: 获取服务器状态
    print("\n2. 测试获取服务器状态...")
    print(f"   GET {BASE_URL}/models/builtin/server/status")
    
    try:
        response = client.get(f"{BASE_URL}/models/builtin/server/status")
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                status = data.get("data", {})
                print("   ✅ 服务器状态查询成功")
                print(f"      Running: {status.get('running')}")
                print(f"      URL: {status.get('url')}")
                if status.get('running'):
                    print(f"      PID: {status.get('process_id')}")
                    print(f"      Loaded Model: {status.get('loaded_model')}")
            else:
                print(f"   ❌ API 返回失败: {data.get('message')}")
                return False
        else:
            print(f"   ❌ HTTP 错误: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
        return False
    
    # 检查是否有已下载的模型
    model_to_test = None
    response = client.get(f"{BASE_URL}/models/builtin/list")
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            for model in data.get("data", []):
                if model.get("downloaded"):
                    model_to_test = model["model_id"]
                    break
    
    if not model_to_test:
        print("\n⚠️  没有已下载的模型，跳过服务器启动/停止测试")
        print("   请先运行 test_models_builtin_phase1_3.py 下载模型")
        print("\n" + "="*60)
        print("✅ Phase 2 基础测试通过（部分功能需要已下载的模型）")
        print("="*60)
        return True
    
    print(f"\n   将使用模型 '{model_to_test}' 进行后续测试")
    
    # 测试 3: 停止服务器（如果正在运行）
    response = client.get(f"{BASE_URL}/models/builtin/server/status")
    if response.status_code == 200:
        data = response.json()
        if data.get("success") and data.get("data", {}).get("running"):
            print("\n3. 服务器正在运行，先停止...")
            print(f"   POST {BASE_URL}/models/builtin/server/stop")
            
            response = client.post(f"{BASE_URL}/models/builtin/server/stop")
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    print("   ✅ 服务器已停止")
                    time.sleep(2)
                else:
                    print(f"   ❌ 停止失败: {data.get('message')}")
            else:
                print(f"   ❌ HTTP 错误: {response.status_code}")
    
    # 测试 4: 启动服务器
    print("\n4. 测试启动服务器...")
    print(f"   POST {BASE_URL}/models/builtin/server/start")
    print("   (这可能需要 30-60 秒...)")
    
    try:
        response = client.post(
            f"{BASE_URL}/models/builtin/server/start",
            json={"model_id": model_to_test}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print("   ✅ 服务器启动成功")
                status = data.get("data", {})
                print(f"      PID: {status.get('process_id')}")
                print(f"      Loaded Model: {status.get('loaded_model')}")
            else:
                print(f"   ❌ 启动失败: {data.get('message')}")
                return False
        else:
            print(f"   ❌ HTTP 错误: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
        return False
    
    # 测试 5: 验证服务器状态
    print("\n5. 验证服务器已启动...")
    time.sleep(2)
    
    response = client.get(f"{BASE_URL}/models/builtin/server/status")
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            status = data.get("data", {})
            if status.get("running"):
                print("   ✅ 服务器确认正在运行")
            else:
                print("   ❌ 服务器状态显示未运行")
                return False
        else:
            print(f"   ❌ 查询失败: {data.get('message')}")
            return False
    
    # 测试 6: 停止服务器
    print("\n6. 测试停止服务器...")
    print(f"   POST {BASE_URL}/models/builtin/server/stop")
    
    response = client.post(f"{BASE_URL}/models/builtin/server/stop")
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            print("   ✅ 服务器已停止")
        else:
            print(f"   ❌ 停止失败: {data.get('message')}")
            return False
    else:
        print(f"   ❌ HTTP 错误: {response.status_code}")
        return False
    
    # 验证服务器已停止
    time.sleep(2)
    response = client.get(f"{BASE_URL}/models/builtin/server/status")
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            status = data.get("data", {})
            if not status.get("running"):
                print("   ✅ 服务器确认已停止")
            else:
                print("   ❌ 服务器仍在运行")
                return False
    
    print("\n" + "="*60)
    print("✅ Phase 2 所有测试通过！")
    print("="*60)
    
    client.close()
    return True


if __name__ == "__main__":
    try:
        success = test_builtin_api_endpoints()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}", exc_info=True)
        sys.exit(1)
