"""
测试内置模型初始化 API（用于 Splash 页面）

运行方式：
    cd api
    python test_builtin_initialize_api.py
"""
import asyncio
import httpx
import json
import time
from pathlib import Path

API_BASE = "http://127.0.0.1:60315"

async def test_initialize_api():
    """测试 /models/builtin/initialize API"""
    print("=" * 60)
    print("测试内置模型初始化 API")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        # 测试 1: 检查下载状态
        print("\n1. 检查当前下载状态...")
        response = await client.get(f"{API_BASE}/models/builtin/download-status")
        status_data = response.json()
        print(f"   状态响应: {json.dumps(status_data, indent=2, ensure_ascii=False)}")
        
        # 测试 2: 初始化模型（使用 huggingface 镜像）
        print("\n2. 初始化模型（huggingface 镜像）...")
        response = await client.post(
            f"{API_BASE}/models/builtin/initialize",
            json={"mirror": "huggingface"}
        )
        init_data = response.json()
        print(f"   初始化响应: {json.dumps(init_data, indent=2, ensure_ascii=False)}")
        
        if init_data.get("status") == "ready":
            print("   ✅ 模型已就绪，无需下载")
            return
        
        if init_data.get("status") == "downloading":
            print("   📥 模型下载已启动，等待完成...")
            print("   💡 提示：请在另一个终端运行以下命令查看实时日志：")
            print("      tail -f ~/Library/Application\\ Support/knowledge-focus.huozhong.in/logs/*.log | grep -i 'model\\|download'")
            
            # 轮询下载状态（最多等待10分钟）
            max_wait = 600  # 10 minutes
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                await asyncio.sleep(5)  # 每5秒检查一次
                
                response = await client.get(f"{API_BASE}/models/builtin/download-status")
                status_data = response.json()
                
                if status_data.get("downloaded"):
                    print("\n   ✅ 模型下载完成！")
                    print(f"   📁 模型路径: {status_data.get('model_path')}")
                    return
                else:
                    elapsed = int(time.time() - start_time)
                    print(f"   ⏳ 下载中... (已等待 {elapsed} 秒)")
            
            print("\n   ⚠️  下载超时（10分钟）")
        else:
            print(f"   ❌ 初始化失败: {init_data.get('message')}")

async def test_initialize_with_mirror():
    """测试使用中国镜像"""
    print("\n" + "=" * 60)
    print("测试使用中国镜像下载")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        print("\n初始化模型（hf-mirror 中国镜像）...")
        response = await client.post(
            f"{API_BASE}/models/builtin/initialize",
            json={"mirror": "hf-mirror"}
        )
        init_data = response.json()
        print(f"初始化响应: {json.dumps(init_data, indent=2, ensure_ascii=False)}")

if __name__ == "__main__":
    print("\n🚀 开始测试内置模型初始化 API")
    print("\n⚠️  注意：")
    print("1. 确保 API 服务器正在运行（端口 60315）")
    print("2. 模型大小约 2.6GB，下载需要一定时间")
    print("3. 可以在另一个终端查看实时日志")
    print()
    
    # 运行测试
    asyncio.run(test_initialize_api())
    
    # 如果需要测试镜像切换，取消下面的注释
    # asyncio.run(test_initialize_with_mirror())
