"""
测试 ModelsBuiltin Phase 1.3 - 模型下载功能
验证模型下载、进度回调、错误处理等
"""
import sys
from pathlib import Path
from models_builtin import ModelsBuiltin
from sqlmodel import create_engine
from config import TEST_DB_PATH

def test_phase_1_3():
    """测试 Phase 1.3 的模型下载功能"""
    
    # 初始化
    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
    base_dir = Path(TEST_DB_PATH).parent.as_posix()
    builtin_mgr = ModelsBuiltin(engine=engine, base_dir=base_dir)
    
    print("=" * 60)
    print("Phase 1.3 测试: 模型下载功能")
    print("=" * 60)
    
    model_id = "qwen3-vl-4b"
    
    # 测试 1: 检查初始状态
    print("\n[测试 1] 检查初始下载状态")
    is_downloaded = builtin_mgr.is_model_downloaded(model_id)
    print(f"  模型ID: {model_id}")
    print(f"  初始状态: {'已下载' if is_downloaded else '未下载'}")
    
    if is_downloaded:
        print("\n  ⚠️  模型已存在，跳过下载测试")
        print("  如需测试下载功能，请先删除模型目录:")
        model_path = builtin_mgr.get_model_storage_path(model_id)
        print(f"    {model_path}")
        
        # 可选：测试删除功能
        print("\n[可选] 是否删除现有模型以测试下载？(y/N): ", end="")
        user_input = input().strip().lower()
        if user_input == 'y':
            print("  删除模型...")
            success = builtin_mgr.delete_model(model_id)
            if success:
                print("  ✅ 模型已删除")
                is_downloaded = False
            else:
                print("  ❌ 删除失败")
                return False
        else:
            print("  跳过下载测试")
            return True
    
    if not is_downloaded:
        # 测试 2: 下载模型并监控进度
        print("\n[测试 2] 下载模型 (这可能需要几分钟...)")
        print("  提示: 约2.6GB，首次下载可能较慢")
        
        download_progress = {
            "last_progress": 0,
            "stages": []
        }
        
        def progress_callback(data):
            """进度回调函数"""
            progress = data.get("progress", 0)
            status = data.get("status", "")
            message = data.get("message", "")
            
            # 记录阶段变化
            if status not in download_progress["stages"]:
                download_progress["stages"].append(status)
                print(f"\n  [{status}] {message}")
            
            # 每10%打印一次进度
            if progress >= download_progress["last_progress"] + 10:
                print(f"    进度: {progress}%")
                download_progress["last_progress"] = progress
        
        try:
            local_path = builtin_mgr.download_model(
                model_id=model_id,
                progress_callback=progress_callback
            )
            
            print("\n  ✅ 下载成功!")
            print(f"  模型路径: {local_path}")
            print(f"  经历阶段: {' -> '.join(download_progress['stages'])}")
            
            # 测试 3: 验证下载完整性
            print("\n[测试 3] 验证下载完整性")
            is_complete = builtin_mgr.is_model_downloaded(model_id)
            print(f"  完整性检查: {'✅ 通过' if is_complete else '❌ 失败'}")
            
            if not is_complete:
                print("  ❌ 模型下载不完整")
                return False
            
        except Exception as e:
            print(f"\n  ❌ 下载失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    # 测试 4: 测试无效模型ID
    print("\n[测试 4] 测试错误处理 - 无效模型ID")
    try:
        builtin_mgr.download_model("invalid-model-id")
        print("  ❌ 应该抛出 ValueError")
        return False
    except ValueError as e:
        print(f"  ✅ 正确抛出 ValueError: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Phase 1.3 所有测试通过!")
    print("=" * 60)
    print("\n提示: 如需清理测试数据，可手动删除模型目录")
    
    return True

if __name__ == "__main__":
    try:
        success = test_phase_1_3()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断测试")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
