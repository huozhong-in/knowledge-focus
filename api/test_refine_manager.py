#!/usr/bin/env python3
"""
测试RefineManager智能文件夹生成功能
"""

import logging
import sys
import os
from datetime import datetime
from typing import List, Dict, Any

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from sqlmodel import (
    Field, 
    SQLModel, 
    create_engine, 
    Session, 
    select, 
    inspect, 
    text, 
    # asc, 
    # and_, 
    # or_, 
    # desc, 
    # not_,
    Column,
    Enum,
    JSON,
)
from refine_mgr import RefineManager
from db_mgr import DBManager, FileScreeningResult
from task_mgr import TaskManager
from screening_mgr import ScreeningManager

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RefineManagerTester:
    def __init__(self):
        db_file = "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db"
        self._session = Session(create_engine(f'sqlite:///{db_file}'))
        self.db_mgr = DBManager(self._session)
        self.task_mgr = TaskManager(self._session)
        self.screening_mgr = ScreeningManager(self._session)
        self.refine_mgr = RefineManager(self._session)
    
    def cleanup_test_data(self):
        """清理之前的测试数据"""
        logger.info("清理之前的测试数据...")
        # 删除所有测试路径的文件记录
        self._session.execute(text("DELETE FROM t_file_screening_results WHERE file_path LIKE '/test/%'"))
        self._session.commit()
        logger.info("测试数据清理完成")
        
    def create_test_data(self) -> str:
        """创建测试数据并返回任务ID"""
        logger.info("创建测试数据...")
        
        # 创建一个测试任务
        task = self.task_mgr.add_task(
            task_name="智能文件夹测试",
            task_type="refine",
        )
        task_id = str(task.id)  # 确保使用任务的ID（字符串）
        
        # 创建各种类型的测试文件记录
        test_files = [
            # 技术文档类
            {
                "file_path": "/test/docs/python_tutorial.pdf",
                "file_name": "python_tutorial.pdf",
                "file_size": 1024000,
                "file_type": "pdf",
                "tags": ["python", "tutorial", "programming"],
                "content_keywords": ["python", "programming", "tutorial", "function", "class"],
                "entities": ["Python", "Django", "Flask"],
                "project_name": "python-learning"
            },
            {
                "file_path": "/test/docs/javascript_guide.pdf", 
                "file_name": "javascript_guide.pdf",
                "file_size": 800000,
                "file_type": "pdf",
                "tags": ["javascript", "web", "frontend"],
                "content_keywords": ["javascript", "web", "frontend", "DOM", "event"],
                "entities": ["JavaScript", "React", "Vue"],
                "project_name": "web-development"
            },
            # 项目文件类
            {
                "file_path": "/test/projects/myapp/main.py",
                "file_name": "main.py",
                "file_size": 5000,
                "file_type": "py",
                "tags": ["python", "main", "entry"],
                "content_keywords": ["main", "import", "function", "class"],
                "entities": ["FastAPI", "SQLAlchemy"],
                "project_name": "myapp"
            },
            {
                "file_path": "/test/projects/myapp/config.py",
                "file_name": "config.py", 
                "file_size": 2000,
                "file_type": "py",
                "tags": ["python", "config", "settings"],
                "content_keywords": ["config", "settings", "environment"],
                "entities": ["DATABASE_URL", "SECRET_KEY"],
                "project_name": "myapp"
            },
            # 前端项目文件
            {
                "file_path": "/test/projects/webapp/app.js",
                "file_name": "app.js",
                "file_size": 3000,
                "file_type": "js",
                "tags": ["javascript", "app", "main"],
                "content_keywords": ["javascript", "app", "function", "module"],
                "entities": ["Express", "MongoDB"],
                "project_name": "webapp"
            },
            {
                "file_path": "/test/projects/webapp/package.json",
                "file_name": "package.json",
                "file_size": 1000,
                "file_type": "json",
                "tags": ["config", "npm", "dependencies"],
                "content_keywords": ["dependencies", "scripts", "version"],
                "entities": ["express", "mongoose", "nodemon"],
                "project_name": "webapp"
            },
            # 文档类
            {
                "file_path": "/test/notes/meeting_2024_01_15.md",
                "file_name": "meeting_2024_01_15.md",
                "file_size": 1500,
                "file_type": "md",
                "tags": ["meeting", "notes", "2024"],
                "content_keywords": ["meeting", "discussion", "action", "items"],
                "entities": ["John Smith", "Project Alpha", "Q1 2024"],
                "project_name": "project-alpha"
            },
            {
                "file_path": "/test/notes/research_ai_trends.md",
                "file_name": "research_ai_trends.md",
                "file_size": 2500,
                "file_type": "md", 
                "tags": ["research", "ai", "trends"],
                "content_keywords": ["AI", "machine learning", "trends", "research"],
                "entities": ["OpenAI", "Google", "Microsoft"],
                "project_name": "ai-research"
            },
            # 数据文件
            {
                "file_path": "/test/data/sales_2024.xlsx",
                "file_name": "sales_2024.xlsx",
                "file_size": 50000,
                "file_type": "xlsx",
                "tags": ["data", "sales", "2024"],
                "content_keywords": ["sales", "revenue", "data", "analysis"],
                "entities": ["Q1", "Q2", "Revenue"],
                "project_name": "sales-analysis"
            },
            # 图片文件
            {
                "file_path": "/test/images/logo_v1.png",
                "file_name": "logo_v1.png",
                "file_size": 25000,
                "file_type": "png",
                "tags": ["image", "logo", "design"],
                "content_keywords": ["logo", "brand", "design"],
                "entities": ["Company Logo", "Brand"],
                "project_name": "branding"
            }
        ]
        
        # 插入测试文件到数据库
        for file_data in test_files:
            # 输出任务ID类型进行调试
            logger.info(f"任务ID类型: {type(task_id)}, 值: {task_id}")
            
            file_record = FileScreeningResult(
                file_path=file_data["file_path"],
                file_name=file_data["file_name"],
                file_size=file_data["file_size"],
                extension=file_data["file_type"],
                modified_time=datetime.now(),
                created_time=datetime.now(),
                status="pending",
                tags=file_data["tags"],
                task_id=str(task_id)  # 确保任务ID是字符串
            )
            
            self.screening_mgr.session.add(file_record)
        
        self.screening_mgr.session.commit()
        logger.info(f"创建了 {len(test_files)} 个测试文件记录，任务ID: {task_id}")
        return task_id
    
    def test_smart_folder_generation(self, task_id: str):
        """测试智能文件夹生成功能"""
        logger.info("开始测试智能文件夹生成...")
        
        # 生成所有智能文件夹
        logger.info("\n=== 生成智能文件夹 ===")
        wise_folders = self.refine_mgr.generate_wise_folders(task_id)
        logger.info(f"总共生成了 {len(wise_folders)} 个智能文件夹")
        
        # 按文件夹类型分组显示
        folder_types = {}
        for folder in wise_folders:
            folder_type = folder["type"]
            if folder_type not in folder_types:
                folder_types[folder_type] = []
            folder_types[folder_type].append(folder)
        
        # 显示不同类型的文件夹
        for folder_type, folders in folder_types.items():
            logger.info(f"\n=== {folder_type} 类型文件夹 ({len(folders)}个) ===")
            for folder in folders:
                logger.info(f"{folder['name']} ({folder['file_count']}个文件)")
    
    def test_refine_processing(self, task_id: str):
        """测试完整的精炼处理流程"""
        logger.info("\n=== 测试完整精炼处理流程 ===")
        
        # 启动精炼处理
        result = self.refine_mgr.process_files_for_task(task_id)
        logger.info(f"精炼处理结果: {result}")
        
        # 获取所有智能文件夹
        all_folders = self.refine_mgr.get_wise_folders_by_task(task_id)
        logger.info(f"\n生成的智能文件夹总数: {len(all_folders)}")
        
        for folder in all_folders[:10]:  # 只显示前10个
            logger.info(f"  - {folder['name']} ({folder['type']}) - {folder['file_count']}个文件")
    
    def test_query_methods(self, task_id: str):
        """测试查询方法"""
        logger.info("\n=== 测试查询方法 ===")
        
        # 测试按类别查询文件
        pdf_files = self.refine_mgr.get_files_by_category(task_id, "文档")
        logger.info(f"文档类文件数量: {len(pdf_files)}")
        
        # 测试按标签查询文件
        python_files = self.refine_mgr.get_files_by_tag(task_id, "python")
        logger.info(f"Python标签文件数量: {len(python_files)}")
        
        # 测试按项目查询文件
        myapp_files = self.refine_mgr.get_files_by_project(task_id, "myapp")
        logger.info(f"myapp项目文件数量: {len(myapp_files)}")
        
        # 测试相似文件查询
        similar_files = self.refine_mgr.get_files_by_similarity(task_id, "/test/docs/python_tutorial.pdf")
        logger.info(f"相似文件数量: {len(similar_files)}")

def main():
    """主测试函数"""
    logger.info("开始RefineManager测试...")
    
    tester = RefineManagerTester()
    
    try:
        # 使用已有的真实数据进行测试
        # 查询一个已有的任务ID
        from sqlmodel import select, desc
        from task_mgr import Task
        stmt = select(Task).order_by(desc(Task.created_at)).limit(1)
        task = tester._session.exec(stmt).first()
        if not task:
            logger.error("数据库中没有找到任何任务")
            return
        
        task_id = str(task.id)
        logger.info(f"使用已有的任务ID: {task_id} 进行测试")
        
        # 查询该任务关联的文件数量
        stmt = select(FileScreeningResult).where(FileScreeningResult.task_id == task_id)
        file_count = len(tester._session.exec(stmt).all())
        logger.info(f"该任务关联的文件数量: {file_count}")
        
        # 测试智能文件夹生成
        tester.test_smart_folder_generation(task_id)
        
        # 测试完整精炼处理流程
        tester.test_refine_processing(task_id)
        
        # 测试查询方法
        tester.test_query_methods(task_id)
        
        logger.info("\n测试完成！")
        
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
