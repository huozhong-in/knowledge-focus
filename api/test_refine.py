#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试智慧文件夹功能的脚本
"""

from sqlmodel import Session, create_engine, select
from db_mgr import (
    FileScreeningResult, Project, ProjectRecognitionRule, 
    FileRefineResult, FileRefineStatus, FileAnalysisType,
    FileCategory
)
from refine_mgr import RefineManager
import os
import pathlib
import logging
import datetime
import time

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # 创建内存数据库进行测试
    engine = create_engine("sqlite:///:memory:")
    from db_mgr import SQLModel  # 导入SQLModel才能创建数据库表
    SQLModel.metadata.create_all(engine)
    
    with Session(engine) as session:
        # 1. 设置测试数据 - 创建文件分类
        logger.info("创建测试数据 - 文件分类")
        doc_category = FileCategory(name="document", extensions=[".txt", ".md", ".pdf"])
        code_category = FileCategory(name="code", extensions=[".py", ".js"])
        session.add_all([doc_category, code_category])
        session.commit()
        
        # 2. 创建项目识别规则
        logger.info("创建项目识别规则")
        git_rule = ProjectRecognitionRule(
            name="Git项目", 
            description="识别Git仓库",
            rule_type="file_exists_in_parent_folder", 
            pattern=".git", 
            priority="high",
            indicators={"name_template": "Git项目: {folder_name}"},
            enabled=True,
            is_system=True
        )
        
        python_rule = ProjectRecognitionRule(
            name="Python项目", 
            description="识别Python项目",
            rule_type="file_exists_in_parent_folder", 
            pattern="setup.py", 
            priority="medium",
            indicators={"name_template": "Python项目: {folder_name}"},
            enabled=True,
            is_system=True
        )
        
        session.add_all([git_rule, python_rule])
        session.commit()
        
        # 3. 创建模拟文件结构和粗筛结果
        logger.info("创建模拟文件结构和粗筛结果")
        
        # 模拟一个项目目录结构
        now = datetime.datetime.now()
        yesterday = now - datetime.timedelta(days=1)
        last_week = now - datetime.timedelta(days=7)
        
        # 项目1：模拟Git项目
        screening_result1 = FileScreeningResult(
            file_path="/projects/myapp/.git/config",
            file_name="config",
            extension="",
            file_size=1024,
            category_id=None,
            modified_time=last_week,
            created_time=last_week
        )
        
        screening_result2 = FileScreeningResult(
            file_path="/projects/myapp/README.md",
            file_name="README.md",
            extension=".md",
            file_size=2048,
            category_id=doc_category.id,
            modified_time=yesterday,
            created_time=last_week,
            tags=["文档"]
        )
        
        screening_result3 = FileScreeningResult(
            file_path="/projects/myapp/app.py",
            file_name="app.py",
            extension=".py",
            file_size=4096,
            category_id=code_category.id,
            modified_time=now,
            created_time=yesterday
        )
        
        # 项目2：模拟Python项目
        screening_result4 = FileScreeningResult(
            file_path="/projects/mylibrary/setup.py",
            file_name="setup.py",
            extension=".py",
            file_size=1536,
            category_id=code_category.id,
            modified_time=now,
            created_time=now
        )
        
        screening_result5 = FileScreeningResult(
            file_path="/projects/mylibrary/lib/core.py",
            file_name="core.py",
            extension=".py",
            file_size=3072,
            category_id=code_category.id,
            modified_time=now,
            created_time=now
        )
        
        # 非项目文件
        screening_result6 = FileScreeningResult(
            file_path="/documents/report_v1.txt",
            file_name="report_v1.txt",
            extension=".txt",
            file_size=5120,
            category_id=doc_category.id,
            modified_time=yesterday,
            created_time=last_week,
            tags=["报告", "草稿"]
        )
        
        screening_result7 = FileScreeningResult(
            file_path="/documents/report_v2.txt",
            file_name="report_v2.txt",
            extension=".txt",
            file_size=5632,
            category_id=doc_category.id,
            modified_time=now,
            created_time=yesterday,
            tags=["报告", "终稿"]
        )
        
        session.add_all([
            screening_result1, screening_result2, screening_result3,
            screening_result4, screening_result5, screening_result6, screening_result7
        ])
        session.commit()
        
        # 4. 创建RefineManager并处理粗筛结果
        logger.info("创建RefineManager并处理粗筛结果")
        refine_mgr = RefineManager(session)
        
        # 先处理一部分文件
        for i in range(1, 8):
            screening_id = eval(f"screening_result{i}.id")
            logger.info(f"处理粗筛结果 ID: {screening_id}")
            result = refine_mgr.process_screening_result(screening_id)
            if result:
                logger.info(f"精炼结果 ID: {result.id}, 状态: {result.status}")
                
                # 如果有项目ID，显示项目信息
                if result.project_id:
                    project = session.get(Project, result.project_id)
                    logger.info(f"项目: {project.name}")
                
                # 如果有相关文件，显示相关文件数量
                if result.related_files:
                    logger.info(f"关联文件数量: {len(result.related_files)}")
                
                # 如果有相似文件，显示相似文件数量和详情
                if result.similar_files:
                    logger.info(f"相似文件数量: {len(result.similar_files)}")
                    for sf in result.similar_files:
                        logger.info(f"  - 相似度: {sf['similarity']}, 原因: {sf['reason']}")
        
        # 5. 测试不同类型的智慧文件夹
        logger.info("\n测试不同类型的智慧文件夹:")
        
        # 按项目查询
        projects = session.exec(select(Project)).all()
        for project in projects:
            logger.info(f"\n项目智慧文件夹: {project.name}")
            files = refine_mgr.get_wise_folder_data("project", {"project_id": project.id})
            for file in files:
                screen_result = session.get(FileScreeningResult, file.screening_id)
                logger.info(f"  - {screen_result.file_path}")
        
        # 按文件分类查询
        logger.info("\n文档分类智慧文件夹:")
        doc_files = refine_mgr.get_wise_folder_data(
            "file_category", {"category_name": "document"}
        )
        for file in doc_files:
            screen_result = session.get(FileScreeningResult, file.screening_id)
            logger.info(f"  - {screen_result.file_path}")
        
        logger.info("\n代码分类智慧文件夹:")
        code_files = refine_mgr.get_wise_folder_data(
            "file_category", {"category_name": "code"}
        )
        for file in code_files:
            screen_result = session.get(FileScreeningResult, file.screening_id)
            logger.info(f"  - {screen_result.file_path}")
        
        # 按标签查询
        if session.exec(select(FileRefineResult).where(FileRefineResult.status == FileRefineStatus.COMPLETE.value)).first():
            logger.info("\n标签'报告'智慧文件夹:")
            report_files = refine_mgr.get_wise_folder_data(
                "filename_pattern_tag", {"tag": "报告"}
            )
            for file in report_files:
                screen_result = session.get(FileScreeningResult, file.screening_id)
                logger.info(f"  - {screen_result.file_path}")
        
        # 测试批量处理
        logger.info("\n测试批量处理功能:")
        stats = refine_mgr.process_all_pending_screening_results()
        logger.info(f"批量处理结果: {stats}")

if __name__ == "__main__":
    main()
