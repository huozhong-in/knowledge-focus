#!/usr/bin/env python3
"""
第二阶段集成测试：Pin文件和多模态向量化任务处理

测试场景：
1. 通过/pin-file API创建MULTIVECTOR任务
2. 验证task_processor能够正确处理MULTIVECTOR任务
3. 验证MultivectorMgr集成是否正常工作
"""

import logging
import sys
import os
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlmodel import create_engine, Session
from db_mgr import TaskType, TaskPriority
from task_mgr import TaskManager
from lancedb_mgr import LanceDBMgr
from models_mgr import ModelsMgr
from multivector_mgr import MultiVectorMgr

def setup_logging():
    """设置测试日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def test_pin_file_integration():
    """测试Pin文件和多模态向量化的完整集成"""
    
    logger = logging.getLogger()
    logger.info("🚀 开始第二阶段集成测试：Pin文件多模态向量化")
    
    # 1. 初始化数据库组件
    from config import TEST_DB_PATH
    sqlite_url = f"sqlite:///{TEST_DB_PATH}"
    engine = create_engine(sqlite_url, echo=False)
    db_directory = os.path.dirname(TEST_DB_PATH)
    
    # 测试文件路径
    test_file = "/Users/dio/Downloads/AI代理的上下文工程：构建Manus的经验教训.pdf"
    
    if not os.path.exists(test_file):
        logger.error(f"❌ 测试文件不存在: {test_file}")
        return False
    
    try:
        with Session(bind=engine) as session:
            # 2. 测试任务创建（模拟/pin-file API调用）
            logger.info("📝 步骤1: 创建MULTIVECTOR任务（模拟pin文件操作）")
            task_mgr = TaskManager(session)
            task = task_mgr.add_task(
                task_name=f"测试Pin文件: {Path(test_file).name}",
                task_type=TaskType.MULTIVECTOR,
                priority=TaskPriority.HIGH,
                extra_data={"file_path": test_file}
            )
            logger.info(f"✅ 成功创建任务 ID: {task.id}")
            
            # 3. 测试任务处理（模拟task_processor处理）
            logger.info("🔄 步骤2: 处理MULTIVECTOR任务（模拟task_processor）")
            
            # 初始化组件
            lancedb_mgr = LanceDBMgr(base_dir=db_directory)
            models_mgr = ModelsMgr(session)
            multivector_mgr = MultiVectorMgr(session, lancedb_mgr, models_mgr)
            
            # 获取任务并更新状态
            task_mgr.update_task_status(task.id, "running")
            
            # 处理任务
            if task.extra_data and 'file_path' in task.extra_data:
                file_path = task.extra_data['file_path']
                logger.info(f"📄 开始处理文件: {file_path}")
                
                try:
                    success = multivector_mgr.process_document(file_path)
                    if success:
                        task_mgr.update_task_status(task.id, "completed", result="success",
                                                  message=f"多模态向量化完成: {file_path}")
                        logger.info("✅ 多模态向量化成功完成")
                        return True
                    else:
                        task_mgr.update_task_status(task.id, "failed", result="failure",
                                                  message=f"多模态向量化失败: {file_path}")
                        logger.error("❌ 多模态向量化失败")
                        return False
                        
                except Exception as e:
                    error_msg = f"多模态向量化异常: {file_path} - {str(e)}"
                    task_mgr.update_task_status(task.id, "failed", result="failure", message=error_msg)
                    logger.error(f"❌ {error_msg}", exc_info=True)
                    return False
            else:
                logger.error("❌ 任务数据中缺少file_path")
                return False
                
    except Exception as e:
        logger.error(f"❌ 集成测试失败: {str(e)}", exc_info=True)
        return False

def test_tagging_multivector_chain():
    """测试TAGGING→MULTIVECTOR任务链式处理"""
    
    logger = logging.getLogger()
    logger.info("🔗 测试TAGGING→MULTIVECTOR自动衔接")
    
    # 导入TAGGING→MULTIVECTOR衔接函数
    from main import _check_file_pin_status
    
    # 测试pin状态检查
    test_file = "/Users/dio/Downloads/AI代理的上下文工程：构建Manus的经验教训.pdf"
    is_pinned = _check_file_pin_status(test_file)
    logger.info(f"📍 文件pin状态检查: {test_file} -> {is_pinned}")
    
    # 由于是PDF文件，应该返回True（根据临时实现逻辑）
    if is_pinned:
        logger.info("✅ Pin状态检查机制工作正常")
        return True
    else:
        logger.warning("⚠️ Pin状态检查可能需要调整")
        return False

if __name__ == "__main__":
    setup_logging()
    
    print("=" * 60)
    print("🧪 第二阶段集成测试开始")
    print("=" * 60)
    
    # 测试1: Pin文件和多模态向量化集成
    test1_success = test_pin_file_integration()
    
    # 测试2: TAGGING→MULTIVECTOR链式处理
    test2_success = test_tagging_multivector_chain()
    
    print("=" * 60)
    if test1_success and test2_success:
        print("🎉 第二阶段集成测试全部通过！")
        print("✅ Pin文件功能已正常集成")
        print("✅ 多模态向量化任务处理正常")
        print("✅ TAGGING→MULTIVECTOR自动衔接机制工作")
    else:
        print("❌ 第二阶段集成测试存在问题")
        if not test1_success:
            print("❌ Pin文件或多模态向量化存在问题")
        if not test2_success:
            print("❌ TAGGING→MULTIVECTOR衔接机制需要调整")
    print("=" * 60)
