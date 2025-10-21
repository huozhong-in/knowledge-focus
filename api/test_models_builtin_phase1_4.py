"""
Phase 1.4 测试：自动加载逻辑
测试内容：
1. 检查自动加载条件判断
2. 测试启动时自动加载
3. 测试场景切换时模型加载/卸载
"""

import sys
import time
import logging
from pathlib import Path
from models_builtin import ModelsBuiltin
from model_config_mgr import ModelCapability
from sqlmodel import create_engine, Session, select
from config import TEST_DB_PATH

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_auto_load_logic():
    """测试自动加载逻辑"""
    print("\n" + "="*60)
    print("Phase 1.4 测试：自动加载逻辑")
    print("="*60)
    
    # 初始化
    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
    base_dir = Path(TEST_DB_PATH).parent.as_posix()
    models_builtin = ModelsBuiltin(engine, base_dir)
    
    # 测试 1: 检查自动加载条件
    print("\n1. 检查自动加载条件判断...")
    
    # 首先确保服务器未运行
    if models_builtin.is_server_running():
        print("   停止现有服务器...")
        models_builtin.stop_mlx_server()
        time.sleep(2)

    should_load, model_id = models_builtin.should_auto_load(base_dir=base_dir)
    print(f"   should_load: {should_load}")
    print(f"   model_id: {model_id}")
    
    if should_load and model_id:
        print(f"✅ 检测到应该加载内置模型: {model_id}")
    else:
        print("⚠️  未配置内置模型")
        return False
    
    # 测试 2: 测试启动时自动加载
    print("\n2. 测试启动时自动加载...")
    print(f"   目标模型: {model_id}")
    print("   (这可能需要 30-60 秒...)")
    
    auto_load_success = models_builtin.auto_load_on_startup(base_dir=base_dir)
    
    if not auto_load_success:
        print("❌ 自动加载失败")
        # 检查是否是因为模型未下载
        if not models_builtin.is_model_downloaded(model_id):
            print(f"   原因: 模型 {model_id} 未下载")
            print("   请先运行: uv run test_models_builtin_phase1_3.py")
        return False
    
    print("✅ 启动时自动加载成功")
    
    # 验证服务器状态
    if not models_builtin.is_server_running():
        print("❌ 服务器未运行")
        return False
    
    status = models_builtin.get_server_status()
    print(f"   服务器状态: running={status['running']}, PID={status['process_id']}")
    print(f"   加载的模型: {status.get('loaded_model', 'N/A')}")
    
    # 测试 3: 测试场景切换（重新加载相同模型）
    print("\n3. 测试场景切换（重新加载相同模型）...")
    
    reload_success = models_builtin.load_model_for_scenario(model_id)
    
    if not reload_success:
        print("❌ 场景切换失败")
        models_builtin.stop_mlx_server()
        return False
    
    print("✅ 场景切换成功（相同模型，无需重启）")
    
    # 测试 4: 测试卸载模型
    print("\n4. 测试卸载模型...")
    
    unload_success = models_builtin.unload_current_model()
    
    if not unload_success:
        print("❌ 卸载模型失败")
        return False
    
    print("✅ 模型卸载成功")
    
    # 验证服务器已停止
    time.sleep(2)
    if models_builtin.is_server_running():
        print("❌ 服务器仍在运行")
        return False
    
    print("✅ 服务器确认已停止")
    
    # 测试 5: 测试重复调用 auto_load（应该检测到无需加载）
    print("\n5. 测试当前无配置时的 auto_load 行为...")
    
    # 临时清除配置
    with Session(engine) as session:
        from db_mgr import CapabilityAssignment
        assignment = session.exec(
            select(CapabilityAssignment).where(
                CapabilityAssignment.capability_value == ModelCapability.VISION.value
            )
        ).first()
        
        if assignment:
            session.delete(assignment)
            session.commit()
            print("   已临时清除 VISION 配置")
    
    # 再次调用 auto_load
    should_load, model_id = models_builtin.should_auto_load(base_dir=base_dir)
    if should_load:
        print("❌ 清除配置后仍然返回 should_load=True")
        return False
    
    print("✅ 正确识别无需自动加载")
    
    print("\n" + "="*60)
    print("✅ Phase 1.4 所有测试通过！")
    print("="*60)
    
    return True


if __name__ == "__main__":
    try:
        success = test_auto_load_logic()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}", exc_info=True)
        sys.exit(1)
