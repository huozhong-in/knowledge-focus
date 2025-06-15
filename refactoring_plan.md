# Knowledge Focus 重构执行清单

## 重构要点分析

### 1. 优化 Python API 配置获取
**问题**：目前系统从 `/config/all` 和 `/bundle-extensions/for-rust` 两个端点获取配置，导致重复请求。
**解决方案**：由于 `/config/all` 端点已经包含了 bundle 扩展名的规则（通过 `file_filter_rules` 中 `rule_type` 为 `"os_bundle"` 的项），可以移除 `/bundle-extensions/for-rust` 的请求，改用 `/config/all` 中的数据。

### 2. 重构防抖监控器初始化与启动
**问题**：防抖监控器的初始化和启动分别在 `setup_file_monitor.rs` 和 `file_scanner.rs` 中，导致配置变更时难以重启监控。
**解决方案**：将初始化和启动逻辑整合到同一个模块中，便于统一管理和重启。

### 3. 规范化配置变更队列处理命令
**问题**：配置变更队列处理的命令命名不统一，某些命令可能冗余。
**解决方案**：规范命名并清理不必要的命令，确保处理逻辑清晰。

## 执行计划

### 1. 优化配置获取
1.1 修改 `file_monitor.rs` 中的配置获取逻辑，从 `config/all` 中解析 bundle 扩展名
1.2 删除 `get_bundle_extensions_from_api` 方法或修改为从现有配置中提取
1.3 更新 bundle 扩展名缓存机制，利用 `config/all` 中的数据

### 2. 重构防抖监控器管理
2.1 创建统一的防抖监控器管理接口方法
2.2 将 `setup_file_monitor.rs` 中的初始化逻辑和 `file_scanner.rs` 中的启动逻辑合并
2.3 添加重启防抖监控的方法，确保配置变更时能正确重启监控
2.4 确保监控器能在配置变更后重新应用新配置

### 3. 规范配置变更队列命令 ✅
3.1 ✅ 审核现有命令结构和命名约定
3.2 ✅ 规范化命令命名，使用统一的前缀 `queue_` 用于所有队列相关命令
3.3 ✅ 确保命令清晰地映射到 6 种配置变更场景
3.4 ✅ 保留旧命令作为兼容版本，同时添加新的规范化命令
3.5 ✅ 新队列命令命名规范:
   - `queue_add_blacklist_folder` - 添加黑名单文件夹到队列
   - `queue_delete_folder` - 删除文件夹（队列版本）
   - `queue_toggle_folder_status` - 切换文件夹黑白名单状态
   - `queue_add_whitelist_folder` - 添加白名单文件夹到队列
   - `queue_get_status` - 获取队列状态

### 4. Tauri 命令扩展 (已完成)
4.1 ✅ 获取bundle扩展名命令 (`get_bundle_extensions()`)
4.2 ✅ 刷新监控配置命令 (`refresh_monitoring_config()`) 
4.3 ✅ 黑名单管理命令 (添加了`add_blacklist_folder_with_path()`, `remove_blacklist_folder_by_path()`)
4.4 ✅ 优化API访问，使用getter方法替代直接访问私有字段

## 详细实施步骤

### 1. 优化配置获取

```rust
// 在 file_monitor.rs 中：

/// 从 AllConfigurations 中提取 bundle 扩展名
fn extract_bundle_extensions_from_config(&self, config: &AllConfigurations) -> Vec<String> {
    // 从 file_filter_rules 中过滤 rule_type 为 "os_bundle" 的规则
    config.file_filter_rules.iter()
        .filter(|rule| rule.rule_type == RuleTypeRust::OSBundle)
        .filter_map(|rule| {
            // 从 pattern 字段提取扩展名
            let pattern = &rule.pattern;
            if pattern.starts_with('.') {
                Some(pattern.to_string())
            } else {
                None
            }
        })
        .collect()
}

/// 更新配置并同时更新 bundle 扩展名缓存
pub async fn refresh_all_configurations(&self) -> Result<AllConfigurations, String> {
    // 获取所有配置
    let config = self.fetch_all_configurations().await?;
    
    // 从配置中提取 bundle 扩展名并更新缓存
    let bundle_extensions = self.extract_bundle_extensions_from_config(&config);
    self.update_bundle_cache(bundle_extensions);
    
    Ok(config)
}
```

### 2. 重构防抖监控器管理

```rust
// 在 AppState 或适当的模块中添加：

/// 统一的防抖监控器管理方法
pub async fn initialize_and_start_debounced_monitor(
    &self,
    app_handle: &tauri::AppHandle
) -> Result<(), String> {
    // 1. 获取当前配置
    let config = self.get_config().await?;
    
    // 2. 创建或获取现有的防抖监控器
    let debounced_monitor = {
        let mut monitor_guard = self.debounced_file_monitor.lock().unwrap();
        
        if monitor_guard.is_none() {
            // 从基础监控器创建新的防抖监控器
            let base_monitor = {
                let guard = self.file_monitor.lock().unwrap();
                guard.as_ref().ok_or("文件监控器未初始化")?
            };
            
            let base_monitor_arc = Arc::new(base_monitor.clone());
            *monitor_guard = Some(DebouncedFileMonitor::new(base_monitor_arc));
        }
        
        monitor_guard.clone().unwrap()
    };
    
    // 3. 启动监控（处理所有监控目录）
    let monitored_dirs = config.monitored_folders.clone();
    
    // 发出监控开始的事件
    app_handle.emit_all("monitoring_started", &serde_json::json!({
        "message": "文件监控已启动",
        "timestamp": SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs()
    })).unwrap_or_else(|err| eprintln!("无法发送 monitoring_started 事件: {}", err));
    
    // 启动防抖监控
    debounced_monitor.start_monitoring().await?;
    
    // 4. 为每个目录添加监控
    for dir in monitored_dirs {
        if !dir.is_blacklist {
            debounced_monitor.add_directory_to_watch(dir.path.clone(), Duration::from_millis(500)).await?;
        }
    }
    
    Ok(())
}

/// 重启防抖监控器
pub async fn restart_debounced_monitor(
    &self,
    app_handle: &tauri::AppHandle
) -> Result<(), String> {
    // 先停止现有监控
    {
        let monitor_guard = self.debounced_file_monitor.lock().unwrap();
        if let Some(monitor) = monitor_guard.as_ref() {
            // 实现停止监控的逻辑
            println!("[防抖监控] 停止现有监控");
            // 这里需要实现 DebouncedFileMonitor 的 stop_monitoring 方法
        }
    }
    
    // 重新初始化并启动
    self.initialize_and_start_debounced_monitor(app_handle).await
}
```

### 3. 规范配置变更队列命令

确保以下 6 种场景都有对应的清晰命名的命令：

1. 将常见文件夹改为黑名单：`config_change_common_to_blacklist`
2. 将常见文件夹改回白名单：`config_change_common_to_whitelist`
3. 新增白名单文件夹：`config_change_add_whitelist`
4. 删除白名单文件夹：`config_change_delete_whitelist` 
5. 新增黑名单文件夹：`config_change_add_blacklist`
6. 删除黑名单文件夹：`config_change_delete_blacklist`

```rust
// 在 commands.rs 中统一命名：

/// 配置变更：常见文件夹改为黑名单
#[tauri::command(rename_all = "snake_case")]
pub async fn config_change_common_to_blacklist(
    folder_id: i32,
    folder_path: String,
    state: tauri::State<'_, crate::AppState>,
) -> Result<serde_json::Value, String> {
    // 添加到队列
    let change = crate::ConfigChangeRequest::CommonToBlacklist { 
        folder_id, 
        folder_path: folder_path.clone() 
    };
    
    // 剩余逻辑...
}

// 其他五个命令类似实现...
```

修改 `ConfigChangeRequest` 枚举以匹配新的命令结构：

```rust
// 在 lib.rs 中:

#[derive(Debug, Clone)]
pub enum ConfigChangeRequest {
    CommonToBlacklist { folder_id: i32, folder_path: String },
    CommonToWhitelist { folder_id: i32, folder_path: String },
    AddWhitelist { folder_path: String, folder_alias: Option<String> },
    DeleteWhitelist { folder_id: i32, folder_path: String },
    AddBlacklist { parent_id: i32, folder_path: String, folder_alias: Option<String> },
    DeleteBlacklist { folder_id: i32, folder_path: String },
    // 其他必要的变更类型...
}
```

## 注意事项

1. 确保所有修改都考虑异步安全性，避免死锁
2. 添加适当的错误处理和日志记录
3. 在开发环境充分测试重构的功能，特别是配置变更队列处理
4. 确保所有UI交互都能正确传递到后端并得到处理
5. 考虑添加单元测试验证核心功能
