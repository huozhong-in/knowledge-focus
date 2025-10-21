"""
测试 ModelsBuiltin Phase 1.1 - 基础类实现
验证模型路径、下载状态检查等基础功能
"""
import sys
from pathlib import Path
from models_builtin import ModelsBuiltin
from sqlmodel import create_engine
from config import TEST_DB_PATH, VLM_MODEL

def test_phase_1_1():
    """测试 Phase 1.1 的所有功能"""
    
    # 初始化
    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
    base_dir = Path(TEST_DB_PATH).parent.as_posix()
    builtin_mgr = ModelsBuiltin(engine=engine, base_dir=base_dir)
    
    print("=" * 60)
    print("Phase 1.1 测试: ModelsBuiltin 基础类实现")
    print("=" * 60)
    
    # 测试 1: 获取模型存储路径
    print("\n[测试 1] 获取模型存储路径")
    model_id = VLM_MODEL  # 使用配置中的模型ID
    model_path = builtin_mgr.get_model_storage_path(model_id)
    print(f"  模型ID: {model_id}")
    print(f"  存储路径: {model_path}")
    print(f"  路径类型: {type(model_path)}")
    assert isinstance(model_path, Path), "返回值应该是 Path 对象"
    assert str(model_path).endswith(model_id), "路径应该包含模型ID"
    print("  ✅ 通过")
    
    # 测试 2: 检查模型下载状态（应该是未下载）
    print("\n[测试 2] 检查模型下载状态")
    is_downloaded = builtin_mgr.is_model_downloaded(model_id)
    print(f"  模型ID: {model_id}")
    print(f"  下载状态: {is_downloaded}")
    print(f"  预期: False (因为尚未下载)")
    if is_downloaded:
        print(f"  ⚠️  模型已经下载，跳过此测试")
    else:
        print("  ✅ 通过")
    
    # 测试 3: 获取已下载模型列表
    print("\n[测试 3] 获取已下载模型列表")
    downloaded = builtin_mgr.get_downloaded_models()
    print(f"  已下载模型数量: {len(downloaded)}")
    print(f"  模型列表: {downloaded}")
    assert isinstance(downloaded, list), "返回值应该是列表"
    print("  ✅ 通过")
    
    # 测试 4: 获取支持的模型信息
    print("\n[测试 4] 获取支持的模型信息")
    supported = builtin_mgr.get_supported_models()
    print(f"  支持的模型数量: {len(supported)}")
    for model_info in supported:
        print(f"\n  模型: {model_info['model_id']}")
        print(f"    显示名称: {model_info['display_name']}")
        print(f"    描述: {model_info['description']}")
        print(f"    能力: {model_info['capabilities']}")
        print(f"    大小: {model_info['size_mb']} MB")
        print(f"    已下载: {model_info['downloaded']}")
        print(f"    路径: {model_info['path']}")
    assert len(supported) > 0, "应该至少有一个支持的模型"
    assert all('model_id' in m for m in supported), "所有模型应该有 model_id"
    print("\n  ✅ 通过")
    
    # 测试 5: 验证内置模型目录已创建
    print("\n[测试 5] 验证内置模型目录")
    builtin_dir = builtin_mgr.builtin_models_dir
    print(f"  目录路径: {builtin_dir}")
    print(f"  目录存在: {builtin_dir.exists()}")
    assert builtin_dir.exists(), "内置模型目录应该已创建"
    print("  ✅ 通过")
    
    print("\n" + "=" * 60)
    print("✅ Phase 1.1 所有测试通过!")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    try:
        test_phase_1_1()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
