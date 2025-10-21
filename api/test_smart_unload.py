"""
测试智能卸载逻辑

测试场景：
1. 初始状态：4个能力都分配给 MLX-VLM
2. 切换第1个能力到其他模型 → 不卸载
3. 切换第2个能力到其他模型 → 不卸载
4. 切换第3个能力到其他模型 → 不卸载
5. 切换第4个能力到其他模型 → 自动卸载 ✅
"""

import asyncio
import sys
from pathlib import Path

# 添加 api 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from sqlmodel import create_engine, Session, select
from db_mgr import ModelCapability, CapabilityAssignment, ModelConfiguration
from builtin_openai_compat import get_vlm_manager

# 测试数据库路径
TEST_DB_PATH = Path.home() / "Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db"


async def test_smart_unload():
    """测试智能卸载逻辑"""
    
    # 连接数据库
    engine = create_engine(f"sqlite:///{TEST_DB_PATH}")
    vlm_manager = get_vlm_manager()
    
    print("=" * 60)
    print("智能卸载逻辑测试")
    print("=" * 60)
    
    # 获取 MLX-VLM 模型的配置 ID
    with Session(engine) as session:
        # 查找 MLX-VLM 模型（实际的 model_identifier）
        mlx_vlm_config = session.exec(
            select(ModelConfiguration).where(
                ModelConfiguration.model_identifier == "mlx-community/Qwen3-VL-4B-Instruct-3bit"
            )
        ).first()
        
        if not mlx_vlm_config:
            print("❌ 未找到 MLX-VLM 模型配置")
            return
        
        print(f"✅ 找到 MLX-VLM 模型配置: ID={mlx_vlm_config.id}, {mlx_vlm_config.display_name}")
        
        # 获取其他模型（用于测试切换）
        other_models = session.exec(
            select(ModelConfiguration).where(
                ModelConfiguration.model_identifier != "mlx-community/Qwen3-VL-4B-Instruct-3bit"
            )
        ).all()
        
        if not other_models:
            print("❌ 未找到其他模型用于测试切换")
            return
        
        # 选择一个非 MLX-VLM 的模型用于测试
        other_model = other_models[0]
        print(f"✅ 使用其他模型进行测试: {other_model.display_name} (ID={other_model.id})")
        print(f"   模型标识: {other_model.model_identifier}")
        
        # 测试步骤 0: 初始化 - 确保 4 个能力都分配给 MLX-VLM
        print("\n--- 步骤 0: 初始化测试环境 ---")
        print("将所有 4 个能力分配给 MLX-VLM...")
        print(f"(MLX-VLM 模型 ID: {mlx_vlm_config.id})")
        
        # 先显示当前实际状态
        print("\n当前数据库中的能力分配：")
        current_assignments = session.exec(select(CapabilityAssignment)).all()
        for assignment in current_assignments:
            model = session.exec(
                select(ModelConfiguration).where(
                    ModelConfiguration.id == assignment.model_configuration_id
                )
            ).first()
            status = "🔵 MLX-VLM" if model.model_identifier == "mlx-community/Qwen3-VL-4B-Instruct-3bit" else "⚪ 其他"
            print(f"  {assignment.capability_value:20} → ID={assignment.model_configuration_id} ({model.display_name}) {status}")
        
        # 现在初始化为 MLX-VLM
        print("\n开始初始化...")
        
        capabilities = [
            ModelCapability.VISION,
            ModelCapability.TEXT,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.TOOL_USE
        ]
        
        for cap in capabilities:
            assignment = session.exec(
                select(CapabilityAssignment).where(
                    CapabilityAssignment.capability_value == cap.value
                )
            ).first()
            
            if assignment:
                # 更新现有分配
                assignment.model_configuration_id = mlx_vlm_config.id
            else:
                # 创建新分配
                assignment = CapabilityAssignment(
                    capability_value=cap.value,
                    model_configuration_id=mlx_vlm_config.id
                )
                session.add(assignment)
        
        session.commit()
        print("✅ 初始化完成，所有能力已分配给 MLX-VLM")
        
        # 测试步骤 1: 检查当前状态
        print("\n--- 步骤 1: 检查当前能力分配 ---")
        
        mlx_vlm_count = 0
        for cap in capabilities:
            assignment = session.exec(
                select(CapabilityAssignment).where(
                    CapabilityAssignment.capability_value == cap.value
                )
            ).first()
            
            if assignment:
                model = session.exec(
                    select(ModelConfiguration).where(
                        ModelConfiguration.id == assignment.model_configuration_id
                    )
                ).first()
                
                status = "🔵 MLX-VLM" if model.model_identifier == "mlx-community/Qwen3-VL-4B-Instruct-3bit" else "⚪ 其他"
                print(f"  {cap.value}: {model.display_name} {status}")
                
                if model.model_identifier == "mlx-community/Qwen3-VL-4B-Instruct-3bit":
                    mlx_vlm_count += 1
        
        print(f"\n当前使用 MLX-VLM 的能力数量: {mlx_vlm_count}/4")
        
        # 测试步骤 2-5: 逐个切换能力
        print("\n--- 步骤 2-5: 逐个切换能力到其他模型 ---")
        
        for i, cap in enumerate(capabilities, 1):
            assignment = session.exec(
                select(CapabilityAssignment).where(
                    CapabilityAssignment.capability_value == cap.value
                )
            ).first()
            
            if assignment and assignment.model_configuration_id == mlx_vlm_config.id:
                print(f"\n切换 {cap.value} 到 {other_model.display_name}...")
                
                # 切换能力
                assignment.model_configuration_id = other_model.id
                session.commit()
                
                # 检查是否触发卸载
                unloaded = await vlm_manager.check_and_unload_if_unused(engine)
                
                remaining = 4 - i
                if unloaded:
                    print(f"  ✅ MLX-VLM 模型已卸载！ (剩余 {remaining} 个能力)")
                else:
                    print(f"  ⏳ MLX-VLM 仍在使用中 (剩余 {remaining} 个能力)")
                
                # 检查模型是否真的卸载了
                is_loaded = vlm_manager.is_model_loaded("mlx-community/Qwen3-VL-4B-Instruct-3bit")
                print(f"  模型加载状态: {'已加载' if is_loaded else '未加载'}")
                
                if i < 4:
                    print(f"  预期: 不卸载 (还有 {remaining} 个能力在使用)")
                    assert not unloaded, "❌ 错误: 提前卸载了！"
                else:
                    print("  预期: 卸载 (所有能力都已切换)")
                    assert unloaded, "❌ 错误: 应该卸载但没有卸载！"
        
        print("\n" + "=" * 60)
        print("✅ 智能卸载逻辑测试通过！")
        print("=" * 60)
        
        # 恢复原始配置（可选）
        restore = input("\n是否恢复原始配置？(y/n): ")
        if restore.lower() == 'y':
            print("\n恢复所有能力到 MLX-VLM...")
            for cap in capabilities:
                assignment = session.exec(
                    select(CapabilityAssignment).where(
                        CapabilityAssignment.capability_value == cap.value
                    )
                ).first()
                
                if assignment:
                    assignment.model_configuration_id = mlx_vlm_config.id
            
            session.commit()
            print("✅ 已恢复原始配置")


if __name__ == "__main__":
    asyncio.run(test_smart_unload())
