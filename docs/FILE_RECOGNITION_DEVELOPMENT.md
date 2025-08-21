# 文件识别规则管理界面开发进度

## 项目概述
为用户提供完整的文件识别规则管理界面，包括文件分类、扩展名映射、忽略规则和Bundle扩展名的增删改查功能。

## 数据库表结构分析

### 核心表和控制字段
1. **FileCategory** - 文件分类表
   - 基础增删改查，无特殊控制字段
   
2. **FileExtensionMap** - 扩展名映射表
   - 扩展名 → 分类的映射关系
   - 基础增删改查

3. **FileFilterRule** - 文件过滤规则表
   - `enabled: bool` - 规则启用/禁用状态 ⭐
   - `is_system: bool` - 系统规则vs用户规则
   - 需要支持启用/禁用切换

4. **BundleExtension** - Bundle扩展名表
   - `is_active: bool` - 扩展名启用状态 ⭐
   - `is_system_default: bool` - 系统默认vs用户添加
   - 需要支持启用/禁用切换

---

## 开发阶段规划

## 第一阶段：后端API开发 ✅

### 当前进度
- ✅ 扩展myfolders_mgr.py管理方法
- ✅ 扩展myfolders_api.py API端点
- ✅ API功能测试验证
- ✅ 修复SQLModel兼容性问题（.count() 方法）
```python
# 文件分类 (FileCategory)
GET    /file-categories          # 获取所有分类
POST   /file-categories          # 添加分类
PUT    /file-categories/{id}     # 更新分类  
DELETE /file-categories/{id}     # 删除分类

# 扩展名映射 (FileExtensionMap)
GET    /extension-mappings       # 获取所有映射
POST   /extension-mappings       # 添加映射
PUT    /extension-mappings/{id}  # 更新映射
DELETE /extension-mappings/{id}  # 删除映射

# 文件过滤规则 (FileFilterRule)  
GET    /filter-rules             # 获取所有规则
POST   /filter-rules             # 添加规则
PUT    /filter-rules/{id}        # 更新规则
DELETE /filter-rules/{id}        # 删除规则
PATCH  /filter-rules/{id}/toggle # 切换启用状态 ⭐

# Bundle扩展名 (现有，需要确认)
GET    /bundle-extensions        # ✅ 已存在
POST   /bundle-extensions        # ✅ 已存在  
DELETE /bundle-extensions/{id}   # ✅ 已存在
PATCH  /bundle-extensions/{id}/toggle # 新增：切换启用状态 ⭐
```

---

### 🎯 第二阶段：前端基础架构 ✅

**目标**: 建立标签页结构和基础组件框架

#### 2.1 重新设计 settings-file-recognition.tsx
- ✅ 📝 Tabs组件架构
- ✅ 📝 4个标签页的基础结构
- ✅ 📝 状态管理设计
- ✅ 📝 API调用基础封装

#### 2.2 检查和安装所需UI组件
- ✅ 🔍 检查现有shadcn/ui组件（已有所需组件）
- ✅ 📦 组件已充分满足需求

---

### 🎯 第三阶段：逐个实现管理界面
**目标**: 按优先级实现各个管理界面

#### 3.1 文件分类管理界面 (优先级: 高)
- [ ] 📝 分类列表展示
- [ ] 📝 添加/编辑分类对话框
- [ ] 📝 删除确认对话框
- [ ] 📝 关联扩展名数量显示

#### 3.2 扩展名映射管理界面 (优先级: 高)
- [ ] 📝 映射表格展示
- [ ] 📝 按分类筛选功能
- [ ] 📝 添加/编辑映射对话框
- [ ] 📝 批量操作功能

#### 3.3 文件过滤规则管理界面 (优先级: 中)
- [ ] 📝 规则列表展示
- [ ] 📝 启用/禁用状态切换 ⭐
- [ ] 📝 系统规则vs用户规则区分显示
- [ ] 📝 添加/编辑规则对话框
- [ ] 📝 规则类型和模式验证

#### 3.4 Bundle扩展名管理界面 (优先级: 低)
- [ ] 📝 从settings-authorization.tsx迁移现有UI
- [ ] 📝 适配新的标签页结构
- [ ] 📝 添加启用/禁用状态切换 ⭐

---

### 🎯 第四阶段：整合测试和优化
**目标**: 完善功能并进行全面测试

#### 4.1 功能完善
- [ ] 📝 数据验证和错误处理
- [ ] 📝 用户体验优化
- [ ] 📝 加载状态和反馈提示

#### 4.2 测试验证
- [ ] 🧪 各模块功能测试
- [ ] 🧪 数据一致性验证
- [ ] 🧪 边界情况处理
- [ ] 🧪 性能验证

---

## 技术要点和注意事项

### 🔧 关键技术点
1. **启用/禁用状态管理**: FileFilterRule.enabled 和 BundleExtension.is_active
2. **系统规则保护**: is_system 和 is_system_default 字段的权限控制
3. **数据关联处理**: 删除分类时需要检查关联的扩展名映射
4. **前端状态同步**: 确保UI状态与数据库状态一致

### ⚠️ 需要澄清的机制
1. **删除分类时的扩展名映射处理**: 是否允许删除有关联映射的分类？
2. **系统规则的编辑权限**: 系统规则是否允许用户修改？
3. **Bundle扩展名的系统默认**: 哪些扩展名属于系统默认？
4. **规则优先级**: 多个规则冲突时的处理逻辑？

---

## 当前状态
📅 **开始时间**: 2025年1月20日  
🚀 **当前阶段**: 第一阶段 - 后端API实现  
⏱️ **预计完成**: 分阶段进行，每阶段测试通过后继续

---

## 变更日志
- **2025-01-20**: 创建开发计划，开始第一阶段开发
