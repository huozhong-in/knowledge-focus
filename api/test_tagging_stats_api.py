"""
测试标签统计API

使用方法：
1. 确保API服务已启动: cd api && ./api_standalone.sh
2. 运行测试: conda run -n ./.venv python test_tagging_stats_api.py
"""

import requests
import json

API_BASE_URL = "http://127.0.0.1:60315"

def test_tagging_stats_api():
    """测试标签统计API端点"""
    print("\n" + "="*60)
    print("🧪 测试标签统计API")
    print("="*60)
    
    try:
        # 测试新的统计API
        url = f"{API_BASE_URL}/file-screening/tagging-stats"
        print(f"\n📡 请求URL: {url}")
        
        response = requests.get(url, timeout=5)
        print(f"📊 状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 响应数据:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            if data.get("success"):
                tagged_count = data.get("tagged_count", 0)
                total_count = data.get("total_count", 0)
                
                print(f"\n📈 统计结果:")
                print(f"   - 已打标签文件数: {tagged_count}")
                print(f"   - 粗筛结果总数: {total_count}")
                print(f"   - 标签覆盖率: {(tagged_count/total_count*100) if total_count > 0 else 0:.1f}%")
                
                return True
            else:
                print(f"❌ API返回失败: {data.get('message')}")
                return False
        else:
            print(f"❌ HTTP请求失败: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ 连接失败: 请确保API服务已启动")
        print("   启动命令: cd api && ./api_standalone.sh")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_screening_total_api():
    """测试原有的总数API端点（对比验证）"""
    print("\n" + "="*60)
    print("🧪 测试原有总数API（对比验证）")
    print("="*60)
    
    try:
        url = f"{API_BASE_URL}/file-screening/total"
        print(f"\n📡 请求URL: {url}")
        
        response = requests.get(url, timeout=5)
        print(f"📊 状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 响应数据:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return True
        else:
            print(f"❌ HTTP请求失败: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        return False

if __name__ == "__main__":
    print("\n" + "🚀"*30)
    print("开始测试标签统计功能")
    print("🚀"*30)
    
    # 先测试原有API，确保基础功能正常
    result1 = test_screening_total_api()
    
    # 测试新的统计API
    result2 = test_tagging_stats_api()
    
    print("\n" + "="*60)
    print("📋 测试总结")
    print("="*60)
    print(f"原有总数API: {'✅ 通过' if result1 else '❌ 失败'}")
    print(f"标签统计API: {'✅ 通过' if result2 else '❌ 失败'}")
    
    if result1 and result2:
        print("\n🎉 所有测试通过！")
    else:
        print("\n⚠️  部分测试失败，请检查API服务状态")
    print("="*60 + "\n")
