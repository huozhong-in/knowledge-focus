# 系统授权和监控文件夹管理重构实施步骤

## 重构概述

本次重构将系统从"挨个文件夹授权"的方式改为"获取系统最大文件访问授权"的方式，简化用户体验，提高系统访问效率。核心思路是：
- 优先获取macOS完全磁盘访问权限 / Windows管理员权限
- 以白名单+黑名单的方式管理文件夹监控
- 支持常见文件夹预置和自定义添加
- 支持macOS bundle扩展名管理，避免不必要的扫描

## 实施步骤分解

### 阶段一：数据库结构调整 📋

#### 1.1 数据库表结构重构
- [x] **db_mgr.py**: 新增 `t_bundle_extensions` 表，用于存储macOS bundle扩展名
  - 字段：id, extension, description, is_active, created_at, updated_at
- [x] **db_mgr.py**: 修改 `t_myfiles` 表结构
  - 添加 `is_common_folder` 字段：标识是否为常见文件夹（不可删除）
  - 添加 `parent_id` 字段：支持黑名单层级关系
  - 调整 `auth_status` 字段默认值逻辑
- [x] **db_mgr.py**: 新增系统配置表 `t_system_config`
  - 字段：key, value, description, updated_at
  - 用于存储完全磁盘访问权限状态等系统级配置

#### 1.2 数据库初始化更新
- [x] **db_mgr.py**: 实现bundle扩展名初始数据插入
  - 预置常见macOS bundle扩展名（.app, .bundle, .framework等）
- [x] **db_mgr.py**: 实现数据库迁移脚本，处理现有数据兼容性
- [x] **db_mgr.py**: 添加系统配置初始化数据

### 阶段二：Python API层改造 🔧

#### 2.1 MyFilesManager 重构
- [x] **myfiles_mgr.py**: 重构 `get_default_directories()` 方法
  - 支持macOS和Windows不同系统的常见文件夹
  - 添加文件夹存在性检查
- [x] ~~**myfiles_mgr.py**: 新增完全磁盘访问权限检测方法~~ (改用前端tauri-plugin-macos-permissions)
  - ~~`check_full_disk_access_detailed()`: 详细权限检测~~
  - ~~`request_full_disk_access()`: 权限请求引导~~
- [x] **myfiles_mgr.py**: 实现黑名单层级管理
  - `add_blacklist_folder(parent_id, folder_path)`: 在白名单下添加黑名单
  - `get_folder_hierarchy()`: 获取文件夹层级关系
- [x] **myfiles_mgr.py**: 新增Bundle扩展名管理
  - `get_bundle_extensions()`: 获取所有bundle扩展名
  - `add_bundle_extension()`: 添加新扩展名
  - `remove_bundle_extension()`: 删除扩展名

#### 2.2 ScreeningManager 增强
- [x] **screening_mgr.py**: 新增按文件夹路径前缀批量删除方法
  - `delete_screening_results_by_folder(folder_path)`: 当文件夹变为黑名单时清理数据
- [x] **screening_mgr.py**: 优化黑名单检查逻辑
  - `is_path_in_blacklist_hierarchy()`: 支持层级黑名单检查

#### 2.3 FastAPI端点更新

- [x] ~~**main.py**: 新增完全磁盘访问权限相关端点~~ (改用前端tauri-plugin-macos-permissions)
  - ~~`GET /system/full-disk-access-status`: 检查权限状态~~
  - ~~`POST /system/request-full-disk-access`: 请求权限~~
- [x] **main.py**: 重构文件夹管理端点
  - `GET /config/all`: 返回包含权限状态的完整配置
  - `POST /folders/blacklist/{parent_id}`: 在指定父文件夹下添加黑名单
  - `DELETE /folders/blacklist/{folder_id}`: 删除黑名单文件夹
- [x] **main.py**: 新增Bundle扩展名管理端点
  - `GET /bundle-extensions`: 获取bundle扩展名列表
  - `POST /bundle-extensions`: 添加新扩展名
  - `DELETE /bundle-extensions/{ext_id}`: 删除扩展名

### 阶段三：Rust后端适配 ⚡

#### 3.1 文件监控器重构

- [x] **file_monitor.rs**: 重构配置获取逻辑
  - 适配新的 `/config/all` 端点返回格式 ✅
  - ~~处理完全磁盘访问权限状态~~ (前端处理)
- [x] **file_monitor.rs**: 优化Bundle检测逻辑
  - 从API动态获取bundle扩展名列表 ✅
  - 实现bundle扩展名缓存机制 ✅
- [x] **file_monitor.rs**: 重构黑名单检查
  - 支持层级黑名单逻辑 ✅ (现有逻辑已支持)
  - 优化黑名单匹配算法性能 ✅
- [x] **file_monitor.rs**: 新增配置刷新方法
  - ~~`update_permission_status()`: 响应权限状态变化~~ (前端处理)
  - `refresh_folder_configuration()`: 刷新文件夹配置 ✅

#### 3.2 Tauri命令扩展

- [x] ~~**commands.rs**: 新增权限管理相关命令~~ (使用tauri-plugin-macos-permissions)
  - ~~`check_system_permissions()`: 检查系统权限~~
  - ~~`request_full_disk_access()`: 请求完全磁盘访问权限~~
- [x] **commands.rs**: 扩展文件夹管理命令
  - `add_blacklist_folder()`: 添加黑名单文件夹 ✅
  - `remove_blacklist_folder()`: 移除黑名单文件夹 ✅
  - `get_folder_hierarchy()`: 获取文件夹层级关系 ✅
  - `refresh_monitoring_config()`: 刷新配置 ✅
  - `get_bundle_extensions()`: 获取Bundle扩展名 ✅
  - `add_blacklist_folder()`: 添加黑名单文件夹
  - `remove_blacklist_folder()`: 移除黑名单文件夹

### 阶段四：前端界面重构 🎨

#### 4.1 主界面重新设计
- [x] **home-authorization.tsx**: 重构整体布局结构
  - 顶部权限状态卡片（完全磁盘访问权限显示）
  - 中部文件夹管理表格（支持层级显示）
  - 底部bundle扩展名管理区域
- [x] **home-authorization.tsx**: 实现权限引导流程
  - 检测权限状态并显示相应提示
  - 一键请求完全磁盘访问权限
  - 权限获取后的状态更新

#### 4.2 文件夹管理界面改造
- [x] **home-authorization.tsx**: 重构文件夹列表显示
  - 实现白名单+黑名单的层级树形显示
  - 添加文件夹类型标识（常见/自定义）
  - 支持拖拽排序和层级调整
- [x] **home-authorization.tsx**: 新增黑名单管理功能
  - 在白名单item旁边添加"添加黑名单"按钮
  - 实现黑名单子文件夹的添加/删除
  - 黑名单文件夹的可视化区分（颜色/图标）
- [x] **home-authorization.tsx**: 实现常见文件夹转换逻辑
  - 常见文件夹可在白名单/黑名单间切换
  - 非常见文件夹只能删除
  - 添加文件夹按钮只能添加白名单

#### 4.3 Bundle扩展名管理界面
- [x] **home-authorization.tsx**: 新增Bundle管理区域
  - 显示当前所有bundle扩展名
  - 支持添加/删除bundle扩展名
  - 提供常见扩展名的快速添加选项

#### 4.4 权限状态指示器
- [x] **home-authorization.tsx**: 实现权限状态实时显示
  - 完全磁盘访问权限状态指示器
  - 各文件夹监控状态指示器
  - 权限问题的解决方案提示

### 阶段五：集成测试与优化 🧪

#### 5.1 权限流程测试
- [ ] **测试**: 完全磁盘访问权限申请流程
  - macOS系统设置跳转是否正确
  - 权限获取后应用重启提示
  - 权限状态检测准确性
- [ ] **测试**: Windows管理员权限检测
  - 管理员权限状态检查
  - 权限不足时的提示和处理

#### 5.2 文件夹管理功能测试
- [ ] **测试**: 常见文件夹初始化
  - 不同操作系统默认文件夹正确性
  - 文件夹存在性检查逻辑
- [ ] **测试**: 黑名单层级功能
  - 白名单下添加黑名单文件夹
  - 黑名单文件夹的监控排除逻辑
  - 层级关系的正确维护

#### 5.3 Bundle扩展名功能测试
- [ ] **测试**: Bundle检测准确性
  - 各种类型macOS bundle的正确识别
  - Bundle内部文件的扫描排除
- [ ] **测试**: 扩展名管理功能
  - 动态添加/删除扩展名
  - 扩展名变更后的实时生效

#### 5.4 性能优化
- [ ] **优化**: 大量文件夹的监控性能
  - 黑名单检查算法优化
  - 内存使用优化
- [ ] **优化**: 权限检查频率优化
  - 避免频繁的权限状态检查
  - 实现智能的权限状态缓存

### 阶段六：用户体验优化 ✨

#### 6.1 权限引导优化
- [ ] **UX**: 完善权限申请引导界面
  - 详细的权限说明和好处介绍
  - 图文并茂的权限设置步骤
  - 权限设置后的验证和反馈

#### 6.2 错误处理和用户反馈
- [ ] **UX**: 完善各种错误场景的处理
  - 权限被拒绝后的处理方案
  - 网络错误时的用户提示
  - 文件夹不存在时的处理逻辑

#### 6.3 界面交互优化
- [ ] **UX**: 优化文件夹管理的用户体验
  - 拖拽添加文件夹的反馈效果
  - 批量操作的进度显示
  - 操作结果的即时反馈

## 重要注意事项 ⚠️

### 权限管理架构调整 🔄
**使用前端 tauri-plugin-macos-permissions 处理权限检测：**
- ✅ 更直接的系统API调用，准确性更高
- ✅ 减少Python后端复杂度
- ✅ 实时权限状态检测
- ✅ 原生macOS权限请求体验

### 性能考虑
- 大量文件夹监控时的性能优化
- 避免过度的权限检查影响用户体验
- Bundle检测的算法效率优化

### 跨平台兼容
- macOS和Windows权限机制差异的处理
- 不同操作系统版本的兼容性考虑
- 确保核心功能在所有支持平台正常工作

