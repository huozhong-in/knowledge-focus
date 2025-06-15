# Rust 文件监控器重构计划

## 当前架构分析

### 核心组件
1. **FileMonitor 核心结构**
   - `monitored_dirs`: 监控目录列表
   - `blacklist_dirs`: 黑名单目录列表  
   - `config_cache`: 配置缓存
   - 多线程批处理器和防抖动监控器

2. **配置获取机制**
   - 使用 `/config/all` 端点获取完整配置
   - 在内存中缓存 `AllConfigurations`
   - 支持动态权限模式切换

3. **Bundle检测逻辑**
   - 硬编码备用扩展名列表 (fallback)
   - 基于文件扩展名、路径组件和目录结构检测
   - **需要改为从API动态获取**

4. **黑名单检查机制**
   - 简单的路径前缀匹配
   - **需要支持层级黑名单逻辑**

## 重构任务清单

### 🎯 阶段三A：配置获取优化 
- [x] `/config/all` 端点已经在使用 ✅
- [x] **添加Bundle扩展名获取** ✅
  - [x] 修改 `/config/all` 端点直接返回 `bundle_extensions` 字段作为简单列表（而不是通过正则规则）✅
  - [x] 更新 `AllConfigurations` 结构体，添加 `bundle_extensions` 字段 ✅
  - [x] 优化 `extract_bundle_extensions()` 方法，优先使用配置中的 `bundle_extensions` 列表 ✅
  - [x] 更新 `is_macos_bundle_folder()` 方法使用配置提供的扩展名列表 ✅

### 🎯 阶段三B：层级黑名单支持
- [x] **重构黑名单检查逻辑** ✅
  - [x] 修改 `is_in_blacklist()` 支持层级关系 (使用Trie实现) ✅
  - [x] 添加父子路径关系检查 (通过Trie的层级结构隐式支持) ✅
  - [x] 优化匹配算法性能 (Trie提供O(L)复杂度，L为路径深度) ✅

### 🎯 阶段三C：配置刷新机制与防抖重启优化
- [x] **添加配置刷新方法** ✅
  - [x] `refresh_folder_configuration()` - 重新获取文件夹配置 ✅
  - [x] `get_monitored_dirs()` - 获取当前监控目录列表 ✅
  - [x] 支持热重载，无需重启监控器 ✅
- [x] **优化防抖动监控器重启逻辑** ✅
  - [x] 添加 `stop_monitoring()` 方法，实现完整停止现有监控 ✅
  - [x] 添加 `restart_monitoring()` 方法，支持平滑重启 ✅
  - [x] 处理停止信号和通道释放，避免资源泄露 ✅

### 🎯 阶段三D：Tauri命令扩展与规范化

- [x] **在 `commands.rs` 中添加新命令** ✅
  - [x] `get_bundle_extensions()` - 获取当前bundle扩展名 ✅
  - [x] `refresh_monitoring_config()` - 刷新配置 ✅
  - [x] `add_blacklist_folder_with_path()` - 添加黑名单（通过路径） ✅
  - [x] `remove_blacklist_folder_by_path()` - 移除黑名单（通过路径） ✅

- [x] **规范化配置队列命令** ✅
  - [x] `queue_add_blacklist_folder` - 添加黑名单文件夹到队列 ✅
  - [x] `queue_delete_folder` - 删除文件夹（队列版本） ✅
  - [x] `queue_toggle_folder_status` - 切换文件夹状态 ✅
  - [x] `queue_add_whitelist_folder` - 添加白名单文件夹 ✅
  - [x] `queue_get_status` - 获取队列状态 ✅
  - [x] 保留旧命令作为兼容版本 ✅

- [x] **清理命令重复定义** ✅
  - [x] 删除重复的 `refresh_monitoring_config` 定义 ✅
  - [x] 删除重复的 `get_bundle_extensions` 定义 ✅
  - [x] 确保每个命令只有一个标准定义 ✅

## 详细实现计划

### 1. Bundle扩展名动态获取 📋

**新增方法：**
```rust
// 在 FileMonitor impl 中添加
async fn fetch_bundle_extensions(&self) -> Result<Vec<String>, String> {
    // 从 /bundle-extensions 获取最新列表
}

fn update_bundle_cache(&self, extensions: Vec<String>) {
    // 更新内存缓存
}

fn get_cached_bundle_extensions(&self) -> Vec<String> {
    // 返回缓存的扩展名，如果为空则返回fallback
}
```

**修改 `is_macos_bundle_folder()` ：**
- 优先使用动态获取的扩展名列表
- fallback扩展名作为安全网
- 添加缓存机制避免频繁API调用

### 2. 层级黑名单重构 📋

**新增数据结构：**
```rust
#[derive(Debug, Clone)]
struct HierarchicalBlacklist {
    path: String,
    parent_id: Option<i32>,
    children: Vec<HierarchicalBlacklist>,
}
```

**重构 `is_in_blacklist()` ：**
- 支持层级路径检查
- 如果父路径在黑名单，子路径自动被排除
- 优化算法复杂度，避免O(n²)遍历

### 3. 配置刷新机制 📋

**新增方法：**
```rust
impl FileMonitor {
    pub async fn refresh_folder_configuration(&self) -> Result<(), String> {
        // 重新调用 fetch_and_store_all_config()
        // 更新监控和黑名单目录
        // 通知正在运行的监控器
    }
    
    pub async fn refresh_bundle_extensions(&self) -> Result<(), String> {
        // 重新获取bundle扩展名
        // 更新缓存
    }
}
```

### 4. 性能优化考虑 📋

**缓存策略：**
- Bundle扩展名缓存 TTL：1小时
- 黑名单树形结构缓存，避免重复构建
- 监控目录变更时智能更新缓存

**并发安全：**
- 使用 `Arc<RwLock<>>` 替代 `Arc<Mutex<>>` 提升读性能
- 异步刷新避免阻塞监控线程
- 原子操作更新配置状态

## 风险评估 ⚠️

### 高风险点
1. **多线程同步**：监控器在运行时修改配置可能导致数据竞争
2. **API调用失败**：网络异常时的降级策略
3. **内存泄漏**：缓存管理不当可能导致内存持续增长

### 安全措施
1. **渐进式重构**：一次只修改一个模块，确保向后兼容
2. **Fallback机制**：API失败时使用硬编码配置
3. **全面测试**：每个阶段完成后进行集成测试
4. **配置验证**：API返回数据的格式验证和错误处理

## 测试策略 🧪

### 单元测试
- Bundle检测逻辑测试
- 黑名单层级匹配测试
- 配置缓存和刷新测试

### 集成测试  
- Python API与Rust后端通信测试
- 多线程监控器配置更新测试
- 异常情况处理测试

### 性能测试
- 大量文件扫描性能测试
- 黑名单匹配算法性能测试
- 内存使用监控

## 实施时间表 📅

**第1天**：Bundle扩展名动态获取 (阶段三A)
**第2天**：层级黑名单重构 (阶段三B) 
**第3天**：配置刷新机制 (阶段三C)
**第4天**：Tauri命令扩展 (阶段三D)
**第5天**：集成测试和优化

每个阶段完成后立即进行测试，确保系统稳定性。
