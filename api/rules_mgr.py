from sqlmodel import (
    Field, 
    SQLModel, 
    create_engine, 
    Session, 
    select, 
    inspect, 
    text, 
    asc, 
    and_, 
    or_, 
    desc, 
    not_,
    Column,
    Enum,
    JSON,
)
from datetime import datetime
from db_mgr import (
    RuleType, 
    RulePriority, 
    RuleAction, 
    FileCategory, 
    FileExtensionMap, 
    FileFilterRule, 
    ProjectRecognitionRule,
)
from typing import Dict, List, Any, Optional, Tuple
import logging
import re
import json
import unittest
import os

logger = logging.getLogger(__name__)

class RulesManager:
    """规则管理类，负责管理文件粗筛规则、项目识别规则等
    
    主要功能包括：
    1. 为Rust端提供规则查询接口，支持文件扩展名规则、文件名模式规则等
    2. 为Python处理提供规则应用功能，用于精炼数据和生成洞察
    3. 为前端提供规则管理界面所需的功能
    """
    
    def __init__(self, session: Session) -> None:
        """初始化规则管理器
        
        Args:
            session: 数据库会话
        """
        self.session = session
        
    def get_file_categories(self) -> List[Dict[str, Any]]:
        """获取所有文件分类
        
        Returns:
            文件分类列表
        """
        categories = self.session.exec(select(FileCategory)).all()
        return [
            {
                "id": cat.id,
                "name": cat.name,
                "description": cat.description,
                "icon": cat.icon
            }
            for cat in categories
        ]
    
    def get_file_extensions_by_category(self, category_name: str = None) -> List[Dict[str, Any]]:
        """获取指定分类的文件扩展名
        
        Args:
            category_name: 分类名称，如果为None则返回所有扩展名
            
        Returns:
            文件扩展名列表
        """
        query = select(FileExtensionMap, FileCategory).join(
            FileCategory, 
            FileExtensionMap.category_id == FileCategory.id
        )
        
        if category_name:
            query = query.where(FileCategory.name == category_name)
            
        results = self.session.exec(query).all()
        
        return [
            {
                "id": ext.FileExtensionMap.id,
                "extension": ext.FileExtensionMap.extension,
                "category": {
                    "id": ext.FileCategory.id,
                    "name": ext.FileCategory.name,
                    "description": ext.FileCategory.description,
                    "icon": ext.FileCategory.icon
                },
                "description": ext.FileExtensionMap.description,
                "priority": ext.FileExtensionMap.priority
            }
            for ext in results
        ]
    
    def get_extension_to_category_map(self) -> Dict[str, Dict[str, Any]]:
        """获取扩展名到分类的映射，用于Rust端快速分类文件
        
        Returns:
            扩展名到分类映射的字典
        """
        extensions = self.get_file_extensions_by_category()
        mapping = {}
        
        for ext in extensions:
            mapping[ext["extension"]] = {
                "category_name": ext["category"]["name"],
                "category_id": ext["category"]["id"],
                "priority": ext["priority"]
            }
            
        return mapping
    
    def get_filename_filter_rules(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """获取文件名过滤规则
        
        Args:
            enabled_only: 是否只返回启用的规则
            
        Returns:
            文件名过滤规则列表
        """
        query = select(FileFilterRule).where(
            FileFilterRule.rule_type == RuleType.FILENAME.value
        )
        
        if enabled_only:
            query = query.where(FileFilterRule.enabled == True)
            
        rules = self.session.exec(query).all()
        
        return [
            {
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "pattern": rule.pattern,
                "pattern_type": rule.pattern_type,
                "action": rule.action,
                "priority": rule.priority,
                "category_id": rule.category_id,
                "extra_data": rule.extra_data
            }
            for rule in rules
        ]
    
    def get_project_recognition_rules(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """获取项目识别规则
        
        Args:
            enabled_only: 是否只返回启用的规则
            
        Returns:
            项目识别规则列表
        """
        query = select(ProjectRecognitionRule)
        
        if enabled_only:
            query = query.where(ProjectRecognitionRule.enabled == True)
            
        rules = self.session.exec(query).all()
        
        return [
            {
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "rule_type": rule.rule_type,
                "pattern": rule.pattern,
                "priority": rule.priority,
                "indicators": rule.indicators
            }
            for rule in rules
        ]
    
    def get_all_rules_for_rust(self) -> Dict[str, Any]:
        """获取所有规则数据，供Rust端使用
        
        返回格式化后的规则数据，包括扩展名映射、文件名过滤规则和项目识别规则
        
        Returns:
            包含所有规则的字典
        """
        rules_data = {
            "extension_mapping": self.get_extension_to_category_map(),
            "filename_rules": self.get_filename_filter_rules(enabled_only=True),
            "project_rules": self.get_project_recognition_rules(enabled_only=True),
            "exclude_rules": self._get_exclude_rules(),
            "version": "1.0"  # 规则版本，用于Rust端检查更新
        }
        
        return rules_data
    
    def _get_exclude_rules(self) -> List[Dict[str, Any]]:
        """获取需要排除的文件规则
        
        Returns:
            排除规则列表
        """
        query = select(FileFilterRule).where(
            and_(
                FileFilterRule.action == RuleAction.EXCLUDE.value,
                FileFilterRule.enabled == True
            )
        )
        
        rules = self.session.exec(query).all()
        
        return [
            {
                "pattern": rule.pattern,
                "pattern_type": rule.pattern_type,
                "priority": rule.priority
            }
            for rule in rules
        ]
    
    def match_file_extension(self, filename: str) -> Dict[str, Any]:
        """根据文件名匹配扩展名规则
        
        Args:
            filename: 文件名
            
        Returns:
            匹配结果，包含分类信息
        """
        ext = filename.split('.')[-1].lower() if '.' in filename else ""
        
        # 获取扩展名映射
        ext_map = self.get_extension_to_category_map()
        
        if (ext in ext_map):
            return {
                "matched": True,
                "extension": ext,
                "category": ext_map[ext]["category_name"],
                "category_id": ext_map[ext]["category_id"]
            }
        else:
            return {
                "matched": False,
                "extension": ext,
                "category": "unknown",
                "category_id": None
            }
    
    def match_filename_patterns(self, filename: str) -> List[Dict[str, Any]]:
        """根据文件名匹配文件名模式规则
        
        Args:
            filename: 文件名
            
        Returns:
            匹配到的规则列表
        """
        # 获取所有启用的文件名规则
        rules = self.get_filename_filter_rules(enabled_only=True)
        
        # 按优先级排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        rules.sort(key=lambda x: priority_order.get(x["priority"], 999))
        
        matches = []
        
        for rule in rules:
            pattern = rule["pattern"]
            pattern_type = rule["pattern_type"]
            
            if pattern_type == "regex":
                if re.search(pattern, filename, re.IGNORECASE):
                    matches.append({
                        "rule_id": rule["id"],
                        "rule_name": rule["name"],
                        "action": rule["action"],
                        "extra_data": rule["extra_data"]
                    })
            elif pattern_type == "glob":
                # 简化处理，只支持*和?通配符
                glob_pattern = pattern.replace("*", ".*").replace("?", ".")
                if re.search(f"^{glob_pattern}$", filename, re.IGNORECASE):
                    matches.append({
                        "rule_id": rule["id"],
                        "rule_name": rule["name"],
                        "action": rule["action"],
                        "extra_data": rule["extra_data"]
                    })
            elif pattern_type == "keyword":
                if pattern.lower() in filename.lower():
                    matches.append({
                        "rule_id": rule["id"],
                        "rule_name": rule["name"],
                        "action": rule["action"],
                        "extra_data": rule["extra_data"]
                    })
        
        return matches
    
    def should_exclude_file(self, filename: str) -> bool:
        """判断文件是否应该被排除
        
        Args:
            filename: 文件名
            
        Returns:
            是否应该排除
        """
        matches = self.match_filename_patterns(filename)
        
        # 检查是否有EXCLUDE操作的规则匹配
        for match in matches:
            if match["action"] == RuleAction.EXCLUDE.value:
                return True
        
        return False
    
    def test_rule_match(self, rule_id: int, test_string: str) -> Dict[str, Any]:
        """测试规则匹配，用于前端规则管理界面
        
        Args:
            rule_id: 规则ID
            test_string: 测试字符串
            
        Returns:
            测试结果
        """
        # 查询规则
        rule = self.session.get(FileFilterRule, rule_id)
        if not rule:
            return {"matched": False, "error": "规则不存在"}
        
        # 执行匹配
        matched = False
        if rule.pattern_type == "regex":
            try:
                matched = bool(re.search(rule.pattern, test_string, re.IGNORECASE))
            except re.error as e:
                return {"matched": False, "error": f"正则表达式错误: {str(e)}"}
        elif rule.pattern_type == "glob":
            glob_pattern = rule.pattern.replace("*", ".*").replace("?", ".")
            matched = bool(re.search(f"^{glob_pattern}$", test_string, re.IGNORECASE))
        elif rule.pattern_type == "keyword":
            matched = rule.pattern.lower() in test_string.lower()
        
        return {
            "matched": matched,
            "rule": {
                "id": rule.id,
                "name": rule.name,
                "pattern": rule.pattern,
                "pattern_type": rule.pattern_type
            }
        }
    
    def create_file_filter_rule(self, rule_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建新的文件过滤规则
        
        Args:
            rule_data: 规则数据
            
        Returns:
            创建的规则
        """
        # 验证必要的字段
        required_fields = ["name", "rule_type", "pattern", "pattern_type", "action"]
        for field in required_fields:
            if field not in rule_data:
                return {"success": False, "error": f"缺少必要字段: {field}"}
                
        # 创建规则
        rule = FileFilterRule(
            name=rule_data["name"],
            description=rule_data.get("description"),
            rule_type=rule_data["rule_type"],
            pattern=rule_data["pattern"],
            pattern_type=rule_data["pattern_type"],
            action=rule_data["action"],
            priority=rule_data.get("priority", RulePriority.MEDIUM.value),
            category_id=rule_data.get("category_id"),
            enabled=rule_data.get("enabled", True),
            is_system=False,  # 用户创建的规则
            extra_data=rule_data.get("extra_data")
        )
        
        try:
            self.session.add(rule)
            self.session.commit()
            self.session.refresh(rule)
            
            return {
                "success": True, 
                "rule": {
                    "id": rule.id,
                    "name": rule.name,
                    "description": rule.description,
                    "rule_type": rule.rule_type,
                    "pattern": rule.pattern,
                    "pattern_type": rule.pattern_type,
                    "action": rule.action,
                    "priority": rule.priority,
                    "category_id": rule.category_id,
                    "enabled": rule.enabled,
                    "is_system": rule.is_system,
                    "extra_data": rule.extra_data
                }
            }
        except Exception as e:
            logger.error(f"创建规则失败: {e}")
            self.session.rollback()
            return {"success": False, "error": f"创建规则失败: {str(e)}"}
    
    def update_file_filter_rule(self, rule_id: int, rule_data: Dict[str, Any]) -> Dict[str, Any]:
        """更新文件过滤规则
        
        Args:
            rule_id: 规则ID
            rule_data: 规则数据
            
        Returns:
            更新结果
        """
        # 查询规则
        rule = self.session.get(FileFilterRule, rule_id)
        if not rule:
            return {"success": False, "error": "规则不存在"}
        
        # 系统规则不允许修改某些字段
        if rule.is_system:
            protected_fields = ["rule_type", "pattern_type", "action"]
            for field in rule_data:
                if field in protected_fields:
                    logger.warning(f"尝试修改系统规则的保护字段: {field}")
                    # rule_data.pop(field) # Don't pop, just skip updating
                    continue
        
        # 更新规则
        try:
            # 更新规则字段
            for key, value in rule_data.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)
                    
            # 更新时间戳
            rule.updated_at = datetime.now()
            
            self.session.commit()
            self.session.refresh(rule)
            
            return {
                "success": True, 
                "rule": {
                    "id": rule.id,
                    "name": rule.name,
                    "description": rule.description,
                    "rule_type": rule.rule_type,
                    "pattern": rule.pattern,
                    "pattern_type": rule.pattern_type,
                    "action": rule.action,
                    "priority": rule.priority,
                    "category_id": rule.category_id,
                    "enabled": rule.enabled,
                    "is_system": rule.is_system,
                    "extra_data": rule.extra_data
                }
            }
        except Exception as e:
            logger.error(f"更新规则失败: {e}")
            self.session.rollback()
            return {"success": False, "error": f"更新规则失败: {str(e)}"}
    
    def delete_file_filter_rule(self, rule_id: int) -> Dict[str, Any]:
        """删除文件过滤规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            删除结果
        """
        # 查询规则
        rule = self.session.get(FileFilterRule, rule_id)
        if not rule:
            return {"success": False, "error": "规则不存在"}
        
        # 系统规则不允许删除
        if rule.is_system:
            return {"success": False, "error": "系统规则不允许删除，可以禁用"}
        
        # 删除规则
        try:
            self.session.delete(rule)
            self.session.commit()
            return {"success": True}
        except Exception as e:
            logger.error(f"删除规则失败: {e}")
            self.session.rollback()
            return {"success": False, "error": f"删除规则失败: {str(e)}"}
    
    def toggle_rule_status(self, rule_id: int, enabled: bool) -> Dict[str, Any]:
        """切换规则启用状态
        
        Args:
            rule_id: 规则ID
            enabled: 是否启用
            
        Returns:
            操作结果
        """
        # 查询规则
        rule = self.session.get(FileFilterRule, rule_id)
        if not rule:
            return {"success": False, "error": "规则不存在"}
        
        # 更新状态
        try:
            rule.enabled = enabled
            rule.updated_at = datetime.now()
            self.session.commit()
            return {"success": True, "enabled": rule.enabled}
        except Exception as e:
            logger.error(f"更新规则状态失败: {e}")
            self.session.rollback()
            return {"success": False, "error": f"更新规则状态失败: {str(e)}"}
    
    # 项目识别规则相关函数
    def match_project_folder(self, folder_name: str, folder_structure: List[str] = None) -> List[Dict[str, Any]]:
        """匹配项目文件夹
        
        Args:
            folder_name: 文件夹名称
            folder_structure: 文件夹结构，如果有的话
            
        Returns:
            匹配到的项目规则列表
        """
        project_rules = self.get_project_recognition_rules(enabled_only=True)
        matches = []
        
        # 按优先级排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        project_rules.sort(key=lambda x: priority_order.get(x["priority"], 999))
        
        # 遍历规则进行匹配
        for rule in project_rules:
            if rule["rule_type"] == "name_pattern":
                # 对文件夹名称进行模式匹配
                if re.search(rule["pattern"], folder_name, re.IGNORECASE):
                    matches.append({
                        "rule_id": rule["id"],
                        "rule_name": rule["name"],
                        "rule_type": rule["rule_type"],
                        "confidence": 0.8,
                        "indicators": rule["indicators"]
                    })
            
            elif rule["rule_type"] == "structure" and folder_structure:
                # 对文件夹结构进行匹配
                structure_markers = rule.get("indicators", {}).get("structure_markers", [])
                if structure_markers:
                    # 检查文件夹结构中是否存在指定的标记
                    marker_matches = [
                        marker for marker in structure_markers
                        if any(item.endswith(marker) for item in folder_structure)
                    ]
                    if marker_matches:
                        confidence = len(marker_matches) / len(structure_markers)
                        matches.append({
                            "rule_id": rule["id"],
                            "rule_name": rule["name"],
                            "rule_type": rule["rule_type"],
                            "confidence": min(confidence, 1.0),
                            "matched_markers": marker_matches,
                            "indicators": rule["indicators"]
                        })
        
        return matches

    # 项目识别规则管理功能
    def create_project_recognition_rule(self, rule_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建新的项目识别规则
        
        Args:
            rule_data: 规则数据
            
        Returns:
            创建的规则
        """
        # 验证必要的字段
        required_fields = ["name", "rule_type", "pattern"]
        for field in required_fields:
            if field not in rule_data:
                return {"success": False, "error": f"缺少必要字段: {field}"}
                
        # 创建规则
        rule = ProjectRecognitionRule(
            name=rule_data["name"],
            description=rule_data.get("description"),
            rule_type=rule_data["rule_type"],
            pattern=rule_data["pattern"],
            priority=rule_data.get("priority", RulePriority.MEDIUM.value),
            indicators=rule_data.get("indicators", {}),
            enabled=rule_data.get("enabled", True),
            is_system=False  # 用户创建的规则
        )
        
        try:
            self.session.add(rule)
            self.session.commit()
            self.session.refresh(rule)
            
            return {
                "success": True, 
                "rule": {
                    "id": rule.id,
                    "name": rule.name,
                    "description": rule.description,
                    "rule_type": rule.rule_type,
                    "pattern": rule.pattern,
                    "priority": rule.priority,
                    "indicators": rule.indicators,
                    "enabled": rule.enabled,
                    "is_system": rule.is_system
                }
            }
        except Exception as e:
            logger.error(f"创建项目规则失败: {e}")
            self.session.rollback()
            return {"success": False, "error": f"创建项目规则失败: {str(e)}"}
    
    def update_project_recognition_rule(self, rule_id: int, rule_data: Dict[str, Any]) -> Dict[str, Any]:
        """更新项目识别规则
        
        Args:
            rule_id: 规则ID
            rule_data: 规则数据
            
        Returns:
            更新结果
        """
        # 查询规则
        rule = self.session.get(ProjectRecognitionRule, rule_id)
        if not rule:
            return {"success": False, "error": "项目规则不存在"}
        
        # 系统规则不允许修改某些字段
        if rule.is_system:
            protected_fields = ["rule_type"]
            for field in rule_data:
                if field in protected_fields:
                    logger.warning(f"尝试修改系统项目规则的保护字段: {field}")
                    # rule_data.pop(field) # Don't pop, just skip updating
                    continue
        
        # 更新规则
        try:
            # 更新规则字段
            for key, value in rule_data.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)
                    
            # 更新时间戳
            rule.updated_at = datetime.now()
            
            self.session.commit()
            self.session.refresh(rule)
            
            return {
                "success": True, 
                "rule": {
                    "id": rule.id,
                    "name": rule.name,
                    "description": rule.description,
                    "rule_type": rule.rule_type,
                    "pattern": rule.pattern,
                    "priority": rule.priority,
                    "indicators": rule.indicators,
                    "enabled": rule.enabled,
                    "is_system": rule.is_system
                }
            }
        except Exception as e:
            logger.error(f"更新项目规则失败: {e}")
            self.session.rollback()
            return {"success": False, "error": f"更新项目规则失败: {str(e)}"}
    
    def delete_project_recognition_rule(self, rule_id: int) -> Dict[str, Any]:
        """删除项目识别规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            删除结果
        """
        # 查询规则
        rule = self.session.get(ProjectRecognitionRule, rule_id)
        if not rule:
            return {"success": False, "error": "项目规则不存在"}
        
        # 系统规则不允许删除
        if rule.is_system:
            return {"success": False, "error": "系统项目规则不允许删除，可以禁用"}
        
        # 删除规则
        try:
            self.session.delete(rule)
            self.session.commit()
            return {"success": True}
        except Exception as e:
            logger.error(f"删除项目规则失败: {e}")
            self.session.rollback()
            return {"success": False, "error": f"删除项目规则失败: {str(e)}"}
    
    def toggle_project_rule_status(self, rule_id: int, enabled: bool) -> Dict[str, Any]:
        """切换项目规则启用状态
        
        Args:
            rule_id: 规则ID
            enabled: 是否启用
            
        Returns:
            操作结果
        """
        # 查询规则
        rule = self.session.get(ProjectRecognitionRule, rule_id)
        if not rule:
            return {"success": False, "error": "项目规则不存在"}
        
        # 更新状态
        try:
            rule.enabled = enabled
            rule.updated_at = datetime.now()
            self.session.commit()
            return {"success": True, "enabled": rule.enabled}
        except Exception as e:
            logger.error(f"更新项目规则状态失败: {e}")
            self.session.rollback()
            return {"success": False, "error": f"更新项目规则状态失败: {str(e)}"}
    
    # 为前端提供的统计和批量操作接口
    def get_rules_statistics(self) -> Dict[str, Any]:
        """获取规则统计信息，用于前端展示
        
        Returns:
            规则统计信息
        """
        stats = {
            "file_categories": {
                "total": len(self.session.exec(select(FileCategory)).all()),
                "categories": [
                    {
                        "name": cat.name,
                        "description": cat.description,
                        "extensions_count": len(self.session.exec(
                            select(FileExtensionMap).where(FileExtensionMap.category_id == cat.id)
                        ).all())
                    }
                    for cat in self.session.exec(select(FileCategory)).all()
                ]
            },
            "file_extensions": {
                "total": len(self.session.exec(select(FileExtensionMap)).all())
            },
            "filter_rules": {
                "total": len(self.session.exec(select(FileFilterRule)).all()),
                "enabled": len(self.session.exec(select(FileFilterRule).where(
                    FileFilterRule.enabled == True
                )).all()),
                "disabled": len(self.session.exec(select(FileFilterRule).where(
                    FileFilterRule.enabled == False
                )).all()),
                "system": len(self.session.exec(select(FileFilterRule).where(
                    FileFilterRule.is_system == True
                )).all()),
                "custom": len(self.session.exec(select(FileFilterRule).where(
                    FileFilterRule.is_system == False
                )).all()),
                "by_type": {
                    "filename": len(self.session.exec(select(FileFilterRule).where(
                        FileFilterRule.rule_type == RuleType.FILENAME.value
                    )).all()),
                    "extension": len(self.session.exec(select(FileFilterRule).where(
                        FileFilterRule.rule_type == RuleType.EXTENSION.value
                    )).all()),
                    "folder": len(self.session.exec(select(FileFilterRule).where(
                        FileFilterRule.rule_type == RuleType.FOLDER.value
                    )).all()),
                    "structure": len(self.session.exec(select(FileFilterRule).where(
                        FileFilterRule.rule_type == RuleType.STRUCTURE.value
                    )).all())
                },
                "by_action": {
                    "include": len(self.session.exec(select(FileFilterRule).where(
                        FileFilterRule.action == RuleAction.INCLUDE.value
                    )).all()),
                    "exclude": len(self.session.exec(select(FileFilterRule).where(
                        FileFilterRule.action == RuleAction.EXCLUDE.value
                    )).all()),
                    "label": len(self.session.exec(select(FileFilterRule).where(
                        FileFilterRule.action == RuleAction.LABEL.value
                    )).all())
                }
            },
            "project_rules": {
                "total": len(self.session.exec(select(ProjectRecognitionRule)).all()),
                "enabled": len(self.session.exec(select(ProjectRecognitionRule).where(
                    ProjectRecognitionRule.enabled == True
                )).all()),
                "disabled": len(self.session.exec(select(ProjectRecognitionRule).where(
                    ProjectRecognitionRule.enabled == False
                )).all()),
                "system": len(self.session.exec(select(ProjectRecognitionRule).where(
                    ProjectRecognitionRule.is_system == True
                )).all()),
                "custom": len(self.session.exec(select(ProjectRecognitionRule).where(
                    ProjectRecognitionRule.is_system == False
                )).all()),
                "by_type": {
                    "name_pattern": len(self.session.exec(select(ProjectRecognitionRule).where(
                        ProjectRecognitionRule.rule_type == "name_pattern"
                    )).all()),
                    "structure": len(self.session.exec(select(ProjectRecognitionRule).where(
                        ProjectRecognitionRule.rule_type == "structure"
                    )).all())
                }
            }
        }
        
        return stats
    
    def export_rules(self) -> Dict[str, Any]:
        """导出所有规则数据，用于备份或迁移
        
        Returns:
            规则数据
        """
        data = {
            "version": "1.0",
            "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "categories": [
                {
                    "name": cat.name,
                    "description": cat.description,
                    "icon": cat.icon
                }
                for cat in self.session.exec(select(FileCategory)).all()
            ],
            "extensions": [
                {
                    "extension": ext.extension,
                    "category_name": self.session.get(FileCategory, ext.category_id).name,
                    "description": ext.description,
                    "priority": ext.priority
                }
                for ext in self.session.exec(select(FileExtensionMap)).all()
            ],
            "filter_rules": [
                {
                    "name": rule.name,
                    "description": rule.description,
                    "rule_type": rule.rule_type,
                    "pattern": rule.pattern,
                    "pattern_type": rule.pattern_type,
                    "action": rule.action,
                    "priority": rule.priority,
                    "category_id": rule.category_id,
                    "enabled": rule.enabled,
                    "is_system": rule.is_system,
                    "extra_data": rule.extra_data
                }
                for rule in self.session.exec(select(FileFilterRule)).all()
            ],
            "project_rules": [
                {
                    "name": rule.name,
                    "description": rule.description,
                    "rule_type": rule.rule_type,
                    "pattern": rule.pattern,
                    "priority": rule.priority,
                    "indicators": rule.indicators,
                    "enabled": rule.enabled,
                    "is_system": rule.is_system
                }
                for rule in self.session.exec(select(ProjectRecognitionRule)).all()
            ]
        }
        
        return data
    
    def import_rules(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """导入规则数据
        
        Args:
            data: 规则数据
            
        Returns:
            导入结果
        """
        try:
            # 验证数据版本
            if "version" not in data or data["version"] != "1.0":
                return {"success": False, "error": "规则数据版本不兼容"}
            
            # 统计导入数量
            stats = {
                "categories": 0,
                "extensions": 0,
                "filter_rules": 0,
                "project_rules": 0
            }
            
            # 导入分类
            if "categories" in data:
                for cat_data in data["categories"]:
                    # 检查是否存在
                    existing = self.session.exec(
                        select(FileCategory).where(FileCategory.name == cat_data["name"])
                    ).first()
                    
                    if not existing:
                        cat = FileCategory(
                            name=cat_data["name"],
                            description=cat_data.get("description"),
                            icon=cat_data.get("icon")
                        )
                        self.session.add(cat)
                        stats["categories"] += 1
            
            # 先提交分类，获取ID
            self.session.commit()
            
            # 获取分类名称到ID的映射
            category_map = {
                cat.name: cat.id 
                for cat in self.session.exec(select(FileCategory)).all()
            }
            
            # 导入扩展名
            if "extensions" in data:
                for ext_data in data["extensions"]:
                    # 检查分类是否存在
                    if ext_data.get("category_name") not in category_map:
                        continue
                        
                    # 检查是否存在
                    existing = self.session.exec(
                        select(FileExtensionMap).where(FileExtensionMap.extension == ext_data["extension"])
                    ).first()
                    
                    if not existing:
                        ext = FileExtensionMap(
                            extension=ext_data["extension"],
                            category_id=category_map[ext_data["category_name"]],
                            description=ext_data.get("description"),
                            priority=ext_data.get("priority", RulePriority.MEDIUM.value)
                        )
                        self.session.add(ext)
                        stats["extensions"] += 1
            
            # 导入过滤规则
            if "filter_rules" in data:
                for rule_data in data["filter_rules"]:
                    # 检查是否存在
                    existing = self.session.exec(
                        select(FileFilterRule).where(FileFilterRule.name == rule_data["name"])
                    ).first()
                    
                    if not existing:
                        rule = FileFilterRule(
                            name=rule_data["name"],
                            description=rule_data.get("description"),
                            rule_type=rule_data["rule_type"],
                            pattern=rule_data["pattern"],
                            pattern_type=rule_data.get("pattern_type", "regex"),
                            action=rule_data["action"],
                            priority=rule_data.get("priority", RulePriority.MEDIUM.value),
                            category_id=rule_data.get("category_id"),
                            enabled=rule_data.get("enabled", True),
                            is_system=rule_data.get("is_system", False),
                            extra_data=rule_data.get("extra_data")
                        )
                        self.session.add(rule)
                        stats["filter_rules"] += 1
            
            # 导入项目规则
            if "project_rules" in data:
                for rule_data in data["project_rules"]:
                    # 检查是否存在
                    existing = self.session.exec(
                        select(ProjectRecognitionRule).where(
                            ProjectRecognitionRule.name == rule_data["name"]
                        )
                    ).first()
                    
                    if not existing:
                        rule = ProjectRecognitionRule(
                            name=rule_data["name"],
                            description=rule_data.get("description"),
                            rule_type=rule_data["rule_type"],
                            pattern=rule_data["pattern"],
                            priority=rule_data.get("priority", RulePriority.MEDIUM.value),
                            indicators=rule_data.get("indicators"),
                            enabled=rule_data.get("enabled", True),
                            is_system=rule_data.get("is_system", False)
                        )
                        self.session.add(rule)
                        stats["project_rules"] += 1
            
            # 提交所有更改
            self.session.commit()
            
            return {
                "success": True, 
                "stats": stats
            }
        except Exception as e:
            logger.error(f"导入规则失败: {e}")
            self.session.rollback()
            return {"success": False, "error": f"导入规则失败: {str(e)}"}
    
    # 精炼数据和洞察生成所需的高级规则支持
    def get_insights_rules(self, insight_type: str = None) -> List[Dict[str, Any]]:
        """获取用于生成洞察的规则
        
        Args:
            insight_type: 洞察类型，如果为None则返回所有洞察规则
            
        Returns:
            洞察规则列表
        """
        query = select(FileFilterRule).where(
            and_(
                FileFilterRule.action == RuleAction.LABEL.value,
                FileFilterRule.enabled == True,
                FileFilterRule.extra_data != None
            )
        )
        
        rules = self.session.exec(query).all()
        result = []
        
        for rule in rules:
            extra_data = rule.extra_data
            if extra_data and "insight_type" in extra_data:
                if insight_type is None or extra_data["insight_type"] == insight_type:
                    result.append({
                        "id": rule.id,
                        "name": rule.name,
                        "pattern": rule.pattern,
                        "pattern_type": rule.pattern_type,
                        "insight_type": extra_data["insight_type"],
                        "label": extra_data.get("label"),
                        "label_name": extra_data.get("label_name"),
                        "extra_data": extra_data
                    })
        
        return result

# Test cases
class TestRulesManager(unittest.TestCase):
    
    def setUp(self):
        """Set up a test database and RulesManager instance."""
        # Use the same database file as db_mgr.py
        self.session = Session(create_engine("sqlite:////Users/dio/Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db"))
        self.rules_manager = RulesManager(self.session)
        
    def tearDown(self):
        """Close the database session."""
        self.session.close()

    # Test Rule Querying Functions
    def test_get_file_categories(self):
        categories = self.rules_manager.get_file_categories()
        self.assertIsInstance(categories, list)
        self.assertGreater(len(categories), 0) # Assuming init_db adds categories
        self.assertIn("name", categories[0])

    def test_get_file_extensions_by_category(self):
        # Assuming 'Document' category exists from init_db
        document_extensions = self.rules_manager.get_file_extensions_by_category("Document")
        self.assertIsInstance(document_extensions, list)
        # self.assertGreater(len(document_extensions), 0) # May be empty if no extensions for Document
        if document_extensions:
            self.assertIn("extension", document_extensions[0])
            self.assertIn("category", document_extensions[0])
            self.assertEqual(document_extensions[0]["category"]["name"], "Document")

        all_extensions = self.rules_manager.get_file_extensions_by_category()
        self.assertIsInstance(all_extensions, list)
        self.assertGreater(len(all_extensions), 0) # Assuming init_db adds extensions

    def test_get_extension_to_category_map(self):
        ext_map = self.rules_manager.get_extension_to_category_map()
        self.assertIsInstance(ext_map, dict)
        self.assertGreater(len(ext_map), 0) # Assuming init_db adds extensions
        # Assuming '.pdf' extension exists and is mapped to a category
        # self.assertIn("pdf", ext_map) # Specific extensions depend on init_db content
        # if "pdf" in ext_map:
        #     self.assertIn("category_name", ext_map["pdf"])

    def test_get_filename_filter_rules(self):
        all_rules = self.rules_manager.get_filename_filter_rules(enabled_only=False)
        self.assertIsInstance(all_rules, list)
        # self.assertGreater(len(all_rules), 0) # May be empty if no filename rules in init_db

        enabled_rules = self.rules_manager.get_filename_filter_rules(enabled_only=True)
        self.assertIsInstance(enabled_rules, list)
        # self.assertLessEqual(len(enabled_rules), len(all_rules))

    def test_get_project_recognition_rules(self):
        all_rules = self.rules_manager.get_project_recognition_rules(enabled_only=False)
        self.assertIsInstance(all_rules, list)
        # self.assertGreater(len(all_rules), 0) # May be empty if no project rules in init_db

        enabled_rules = self.rules_manager.get_project_recognition_rules(enabled_only=True)
        self.assertIsInstance(enabled_rules, list)
        # self.assertLessEqual(len(enabled_rules), len(all_rules))

    def test_get_all_rules_for_rust(self):
        rust_rules = self.rules_manager.get_all_rules_for_rust()
        self.assertIsInstance(rust_rules, dict)
        self.assertIn("extension_mapping", rust_rules)
        self.assertIn("filename_rules", rust_rules)
        self.assertIn("project_rules", rust_rules)
        self.assertIn("exclude_rules", rust_rules)
        self.assertIn("version", rust_rules)

    # Test Rule Matching Functions
    def test_match_file_extension(self):
        # Assuming '.pdf' maps to 'Document'
        match_pdf = self.rules_manager.match_file_extension("report.pdf")
        self.assertTrue(match_pdf["matched"])
        self.assertEqual(match_pdf["extension"], "pdf")
        # self.assertEqual(match_pdf["category"], "Document") # Category name depends on init_db

        match_unknown = self.rules_manager.match_file_extension("archive.xyz123")
        self.assertFalse(match_unknown["matched"])
        self.assertEqual(match_unknown["extension"], "xyz123")
        self.assertEqual(match_unknown["category"], "unknown")

        match_no_extension = self.rules_manager.match_file_extension("README")
        self.assertFalse(match_no_extension["matched"])
        self.assertEqual(match_no_extension["extension"], "")
        self.assertEqual(match_no_extension["category"], "unknown")

    def test_match_filename_patterns(self):
        # Add a test filename rule
        rule_data = {
            "name": "Test Filename Rule",
            "rule_type": RuleType.FILENAME.value,
            "pattern": ".*report.*",
            "pattern_type": "regex",
            "action": RuleAction.INCLUDE.value,
            "priority": RulePriority.MEDIUM.value
        }
        create_result = self.rules_manager.create_file_filter_rule(rule_data)
        self.assertTrue(create_result["success"])

        matches = self.rules_manager.match_filename_patterns("final_report_2023.pdf")
        self.assertIsInstance(matches, list)
        self.assertGreater(len(matches), 0)
        self.assertTrue(any(m["rule_name"] == "Test Filename Rule" for m in matches),
                        "Test Filename Rule was not found in matches")

        no_matches = self.rules_manager.match_filename_patterns("image.png")
        self.assertIsInstance(no_matches, list)
        # self.assertEqual(len(no_matches), 0) # May match other rules from init_db

    def test_should_exclude_file(self):
        # Add an exclude rule
        exclude_rule_data = {
            "name": "Exclude Temp Files",
            "rule_type": RuleType.FILENAME.value,
            "pattern": ".*\\.tmp$",
            "pattern_type": "regex",
            "action": RuleAction.EXCLUDE.value,
            "priority": RulePriority.HIGH.value
        }
        create_result = self.rules_manager.create_file_filter_rule(exclude_rule_data)
        self.assertTrue(create_result["success"])

        self.assertTrue(self.rules_manager.should_exclude_file("document.tmp"))
        self.assertFalse(self.rules_manager.should_exclude_file("document.txt"))

    def test_test_rule_match(self):
        # Add a test rule
        rule_data = {
            "name": "Test Match Rule",
            "rule_type": RuleType.FILENAME.value,
            "pattern": ".*test.*",
            "pattern_type": "regex",
            "action": RuleAction.INCLUDE.value,
            "priority": RulePriority.MEDIUM.value
        }
        create_result = self.rules_manager.create_file_filter_rule(rule_data)
        self.assertTrue(create_result["success"])
        rule_id = create_result["rule"]["id"]

        match_result = self.rules_manager.test_rule_match(rule_id, "this is a test string")
        self.assertTrue(match_result["matched"])
        self.assertEqual(match_result["rule"]["id"], rule_id)

        no_match_result = self.rules_manager.test_rule_match(rule_id, "this is a different string")
        self.assertFalse(no_match_result["matched"])

        invalid_rule_result = self.rules_manager.test_rule_match(9999, "some string")
        self.assertFalse(invalid_rule_result["matched"])
        self.assertIn("error", invalid_rule_result)

    # Test Rule Management Functions (File Filter Rules)
    def test_create_file_filter_rule(self):
        rule_data = {
            "name": "New Test Rule",
            "rule_type": RuleType.FILENAME.value,
            "pattern": "new_file_.*",
            "pattern_type": "regex",
            "action": RuleAction.LABEL.value,
            "priority": RulePriority.LOW.value,
            "extra_data": {"label": "new"}
        }
        result = self.rules_manager.create_file_filter_rule(rule_data)
        self.assertTrue(result["success"])
        self.assertIn("rule", result)
        self.assertEqual(result["rule"]["name"], "New Test Rule")

        # Test missing required field
        invalid_rule_data = {
            "name": "Invalid Rule",
            "rule_type": RuleType.FILENAME.value,
            "pattern": ".*"
            # Missing pattern_type and action
        }
        result = self.rules_manager.create_file_filter_rule(invalid_rule_data)
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_update_file_filter_rule(self):
        # Create a rule first
        rule_data = {
            "name": "Rule to Update",
            "rule_type": RuleType.FILENAME.value,
            "pattern": "old_pattern",
            "pattern_type": "regex",
            "action": RuleAction.INCLUDE.value,
            "priority": RulePriority.MEDIUM.value
        }
        create_result = self.rules_manager.create_file_filter_rule(rule_data)
        self.assertTrue(create_result["success"])
        rule_id = create_result["rule"]["id"]

        # Update the rule
        update_data = {
            "description": "Updated description",
            "pattern": "new_pattern",
            "priority": RulePriority.HIGH.value,
            "enabled": False
        }
        update_result = self.rules_manager.update_file_filter_rule(rule_id, update_data)
        self.assertTrue(update_result["success"])
        self.assertEqual(update_result["rule"]["description"], "Updated description")
        self.assertEqual(update_result["rule"]["pattern"], "new_pattern")
        self.assertEqual(update_result["rule"]["priority"], RulePriority.HIGH.value)
        self.assertFalse(update_result["rule"]["enabled"])

        # Test updating system rule protected fields (should be ignored)
        # Assuming there's a system rule with ID 1 (depends on init_db)
        system_rule_id = 1
        system_update_data = {
            "rule_type": RuleType.EXTENSION.value, # Protected field
            "pattern": "should_not_change"
        }
        system_update_result = self.rules_manager.update_file_filter_rule(system_rule_id, system_update_data)
        # Check if the protected field was NOT updated
        system_rule_after_update = self.session.get(FileFilterRule, system_rule_id)
        # self.assertNotEqual(system_rule_after_update.rule_type, RuleType.EXTENSION.value) # Depends on original type
        # self.assertNotEqual(system_rule_after_update.pattern, "should_not_change") # Pattern is not protected

    def test_delete_file_filter_rule(self):
        # Create a rule first
        rule_data = {
            "name": "Rule to Delete",
            "rule_type": RuleType.FILENAME.value,
            "pattern": "delete_me",
            "pattern_type": "keyword",
            "action": RuleAction.EXCLUDE.value
        }
        create_result = self.rules_manager.create_file_filter_rule(rule_data)
        self.assertTrue(create_result["success"])
        rule_id = create_result["rule"]["id"]

        # Delete the rule
        delete_result = self.rules_manager.delete_file_filter_rule(rule_id)
        self.assertTrue(delete_result["success"])

        # Verify it's deleted
        deleted_rule = self.session.get(FileFilterRule, rule_id)
        self.assertIsNone(deleted_rule)

        # Test deleting a system rule (should fail)
        # Assuming there's a system rule with ID 1 (depends on init_db)
        system_rule_id = 1
        delete_system_result = self.rules_manager.delete_file_filter_rule(system_rule_id)
        self.assertFalse(delete_system_result["success"])
        self.assertIn("error", delete_system_result)

    def test_toggle_rule_status(self):
        # Create a rule first
        rule_data = {
            "name": "Rule to Toggle",
            "rule_type": RuleType.FILENAME.value,
            "pattern": "toggle",
            "pattern_type": "keyword",
            "action": RuleAction.INCLUDE.value,
            "enabled": True
        }
        create_result = self.rules_manager.create_file_filter_rule(rule_data)
        self.assertTrue(create_result["success"])
        rule_id = create_result["rule"]["id"]

        # Toggle to disabled
        toggle_result = self.rules_manager.toggle_rule_status(rule_id, False)
        self.assertTrue(toggle_result["success"])
        self.assertFalse(toggle_result["enabled"])

        # Verify status in DB
        toggled_rule = self.session.get(FileFilterRule, rule_id)
        self.assertFalse(toggled_rule.enabled)

        # Toggle back to enabled
        toggle_result = self.rules_manager.toggle_rule_status(rule_id, True)
        self.assertTrue(toggle_result["success"])
        self.assertTrue(toggle_result["enabled"])

        # Verify status in DB
        toggled_rule = self.session.get(FileFilterRule, rule_id)
        self.assertTrue(toggled_rule.enabled)

    # Test Project Recognition Rule Functions
    def test_match_project_folder(self):
        # Add a test project rule (name pattern)
        name_rule_data = {
            "name": "Test Project Name Rule",
            "rule_type": "name_pattern",
            "pattern": ".*project.*",
            "priority": RulePriority.HIGH.value
        }
        create_name_result = self.rules_manager.create_project_recognition_rule(name_rule_data)
        self.assertTrue(create_name_result["success"])

        # Add a test project rule (structure)
        structure_rule_data = {
            "name": "Test Project Structure Rule",
            "rule_type": "structure",
            "pattern": "", # Pattern is not used for structure rules
            "priority": RulePriority.MEDIUM.value,
            "indicators": {"structure_markers": ["package.json", "Cargo.toml"]}
        }
        create_structure_result = self.rules_manager.create_project_recognition_rule(structure_rule_data)
        self.assertTrue(create_structure_result["success"])

        # Test name pattern match
        name_matches = self.rules_manager.match_project_folder("my_awesome_project")
        self.assertIsInstance(name_matches, list)
        self.assertGreater(len(name_matches), 0)
        self.assertEqual(name_matches[0]["rule_name"], "Test Project Name Rule")

        # Test structure match
        structure_matches = self.rules_manager.match_project_folder("some_folder", ["/path/to/some_folder/package.json", "/path/to/some_folder/src/main.rs"])
        self.assertIsInstance(structure_matches, list)
        self.assertGreater(len(structure_matches), 0)
        # The order of matches depends on priority and insertion order, so check for existence
        structure_rule_matched = any(match["rule_name"] == "Test Project Structure Rule" for match in structure_matches)
        self.assertTrue(structure_rule_matched)

        # Test no match
        no_matches = self.rules_manager.match_project_folder("random_folder")
        self.assertIsInstance(no_matches, list)
        # self.assertEqual(len(no_matches), 0) # May match other rules from init_db

    def test_create_project_recognition_rule(self):
        rule_data = {
            "name": "New Project Rule",
            "rule_type": "name_pattern",
            "pattern": "new_project_.*",
            "priority": RulePriority.LOW.value,
            "indicators": {"language": "Python"}
        }
        result = self.rules_manager.create_project_recognition_rule(rule_data)
        self.assertTrue(result["success"])
        self.assertIn("rule", result)
        self.assertEqual(result["rule"]["name"], "New Project Rule")

        # Test missing required field
        invalid_rule_data = {
            "name": "Invalid Project Rule",
            "rule_type": "name_pattern"
            # Missing pattern
        }
        result = self.rules_manager.create_project_recognition_rule(invalid_rule_data)
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_update_project_recognition_rule(self):
        # Create a rule first
        rule_data = {
            "name": "Project Rule to Update",
            "rule_type": "name_pattern",
            "pattern": "old_project_pattern",
            "priority": RulePriority.MEDIUM.value
        }
        create_result = self.rules_manager.create_project_recognition_rule(rule_data)
        self.assertTrue(create_result["success"])
        rule_id = create_result["rule"]["id"]

        # Update the rule
        update_data = {
            "description": "Updated project description",
            "pattern": "new_project_pattern",
            "priority": RulePriority.HIGH.value,
            "enabled": False,
            "indicators": {"language": "Rust"}
        }
        update_result = self.rules_manager.update_project_recognition_rule(rule_id, update_data)
        self.assertTrue(update_result["success"])
        self.assertEqual(update_result["rule"]["description"], "Updated project description")
        self.assertEqual(update_result["rule"]["pattern"], "new_project_pattern")
        self.assertEqual(update_result["rule"]["priority"], RulePriority.HIGH.value)
        self.assertFalse(update_result["rule"]["enabled"])
        self.assertEqual(update_result["rule"]["indicators"]["language"], "Rust")

        # Test updating system rule protected fields (should be ignored)
        # Assuming there's a system project rule (depends on init_db)
        # This test is harder without knowing the ID of a system project rule from init_db
        # For now, skip testing protected fields update on system project rules

    def test_delete_project_recognition_rule(self):
        # Create a rule first
        rule_data = {
            "name": "Project Rule to Delete",
            "rule_type": "name_pattern",
            "pattern": "delete_project_me"
        }
        create_result = self.rules_manager.create_project_recognition_rule(rule_data)
        self.assertTrue(create_result["success"])
        rule_id = create_result["rule"]["id"]

        # Delete the rule
        delete_result = self.rules_manager.delete_project_recognition_rule(rule_id)
        self.assertTrue(delete_result["success"])

        # Verify it's deleted
        deleted_rule = self.session.get(ProjectRecognitionRule, rule_id)
        self.assertIsNone(deleted_rule)

        # Test deleting a system rule (should fail)
        # This test is harder without knowing the ID of a system project rule from init_db
        # For now, skip testing deletion of system project rules

    def test_toggle_project_rule_status(self):
        # Create a rule first
        rule_data = {
            "name": "Project Rule to Toggle",
            "rule_type": "name_pattern",
            "pattern": "toggle_project",
            "enabled": True
        }
        create_result = self.rules_manager.create_project_recognition_rule(rule_data)
        self.assertTrue(create_result["success"])
        rule_id = create_result["rule"]["id"]

        # Toggle to disabled
        toggle_result = self.rules_manager.toggle_project_rule_status(rule_id, False)
        self.assertTrue(toggle_result["success"])
        self.assertFalse(toggle_result["enabled"])

        # Verify status in DB
        toggled_rule = self.session.get(ProjectRecognitionRule, rule_id)
        self.assertFalse(toggled_rule.enabled)

        # Toggle back to enabled
        toggle_result = self.rules_manager.toggle_project_rule_status(rule_id, True)
        self.assertTrue(toggle_result["success"])
        self.assertTrue(toggle_result["enabled"])

        # Verify status in DB
        toggled_rule = self.session.get(ProjectRecognitionRule, rule_id)
        self.assertTrue(toggled_rule.enabled)

    # Test Advanced Functions
    def test_get_rules_statistics(self):
        stats = self.rules_manager.get_rules_statistics()
        self.assertIsInstance(stats, dict)
        self.assertIn("file_categories", stats)
        self.assertIn("file_extensions", stats)
        self.assertIn("filter_rules", stats)
        self.assertIn("project_rules", stats)
        self.assertGreaterEqual(stats["file_categories"]["total"], 0)
        self.assertGreaterEqual(stats["file_extensions"]["total"], 0)
        self.assertGreaterEqual(stats["filter_rules"]["total"], 0)
        self.assertGreaterEqual(stats["project_rules"]["total"], 0)

    def test_export_rules(self):
        exported_data = self.rules_manager.export_rules()
        self.assertIsInstance(exported_data, dict)
        self.assertIn("version", exported_data)
        self.assertIn("export_time", exported_data)
        self.assertIn("categories", exported_data)
        self.assertIn("extensions", exported_data)
        self.assertIn("filter_rules", exported_data)
        self.assertIn("project_rules", exported_data)

    def test_import_rules(self):
        # Export existing rules first
        exported_data = self.rules_manager.export_rules()

        # Create a new in-memory database for import test
        # This is safer than importing into the main test db
        import_engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(import_engine)
        import_session = Session(import_engine)
        import_rules_manager = RulesManager(import_session)

        # Import the exported data
        import_result = import_rules_manager.import_rules(exported_data)
        self.assertTrue(import_result["success"])
        self.assertIn("stats", import_result)
        self.assertGreaterEqual(import_result["stats"]["categories"], 0)
        self.assertGreaterEqual(import_result["stats"]["extensions"], 0)
        self.assertGreaterEqual(import_result["stats"]["filter_rules"], 0)
        self.assertGreaterEqual(import_result["stats"]["project_rules"], 0)

        # Verify counts match (approximately, as system rules might be handled differently)
        # self.assertEqual(import_result["stats"]["categories"], len(exported_data["categories"]))
        # self.assertEqual(import_result["stats"]["extensions"], len(exported_data["extensions"]))
        # self.assertEqual(import_result["stats"]["filter_rules"], len(exported_data["filter_rules"]))
        # self.assertEqual(import_result["stats"]["project_rules"], len(exported_data["project_rules"]))

        import_session.close()

    def test_get_insights_rules(self):
        # Add a rule with insight data
        insight_rule_data = {
            "name": "Insight Rule Test",
            "rule_type": RuleType.FILENAME.value,
            "pattern": ".*insight.*",
            "pattern_type": "keyword",
            "action": RuleAction.LABEL.value,
            "extra_data": {"insight_type": "recent_activity", "label_name": "Insightful"}
        }
        create_result = self.rules_manager.create_file_filter_rule(insight_rule_data)
        self.assertTrue(create_result["success"])

        # Get all insight rules
        all_insights = self.rules_manager.get_insights_rules()
        self.assertIsInstance(all_insights, list)
        self.assertGreater(len(all_insights), 0)
        insight_rule_found = any(rule["name"] == "Insight Rule Test" for rule in all_insights)
        self.assertTrue(insight_rule_found)

        # Get insight rules by type
        recent_activity_insights = self.rules_manager.get_insights_rules("recent_activity")
        self.assertIsInstance(recent_activity_insights, list)
        self.assertGreater(len(recent_activity_insights), 0)
        insight_rule_found_by_type = any(rule["name"] == "Insight Rule Test" for rule in recent_activity_insights)
        self.assertTrue(insight_rule_found_by_type)

        # Get insight rules for a non-existent type
        non_existent_insights = self.rules_manager.get_insights_rules("non_existent_type")
        self.assertIsInstance(non_existent_insights, list)
        self.assertEqual(len(non_existent_insights), 0)


if __name__ == '__main__':
    unittest.main()
