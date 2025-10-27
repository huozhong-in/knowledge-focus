# 图片自动压缩功能实现说明

## 概述
为 `stream_agent_chat_v5_compatible()` API 添加了自动图片压缩功能，优化多模态消息的性能。

## 修改内容

### 1. 新增函数：`utils.py::compress_image_to_binary()`

**位置**: `/Users/dio/workspace/knowledge-focus/api/utils.py`

**功能**:
- 接收图片文件路径
- 自动调整图片尺寸（最大边长1920像素）
- 压缩为JPEG格式（质量85）
- 返回二进制数据和MIME类型，适配 `BinaryContent`

**返回值**: `tuple[bytes, str]` - (压缩后的字节数据, MIME类型)

**特点**:
- 智能处理 RGBA/透明背景图片
- 等比例缩放，保持宽高比
- 详细的日志记录（原始/压缩大小、压缩率）
- 异常容错：压缩失败时返回原始数据

### 2. 集成到 `models_mgr.py::stream_agent_chat_v5_compatible()`

**位置**: `/Users/dio/workspace/knowledge-focus/api/models_mgr.py` 第592-606行

**改动**:
- 替换直接读取图片为调用 `compress_image_to_binary()`
- 使用压缩后的二进制数据创建 `BinaryContent`
- 保留原有的文件存在性检查和错误处理

### 3. 保持 `coreading_v5_compatible()` 不变

**位置**: `/Users/dio/workspace/knowledge-focus/api/models_mgr.py` 第1196-1218行

**说明**:
- PDF 截图不进行压缩
- 原因：截图通常不大，且包含文字，压缩会降低清晰度
- 保持原有的直接读取逻辑

## 配置参数

当前使用的压缩参数：
```python
max_size=1920   # 最大边长（像素）
quality=85      # JPEG 质量（1-100）
```

可根据需要调整这些参数以平衡文件大小和图片质量。

## 测试

提供了测试脚本：`/Users/dio/workspace/knowledge-focus/api/test_image_compression.py`

运行方式：
```bash
cd /Users/dio/workspace/knowledge-focus/api
python test_image_compression.py
```

## 效果

- **性能提升**: 大幅减少图片传输和处理的内存占用
- **兼容性**: 完全兼容现有的 BinaryContent 和 Pydantic AI 流式响应
- **透明化**: 对前端无感知，自动处理
- **可靠性**: 压缩失败时自动降级到原始图片

## 影响范围

- ✅ 影响：`stream_agent_chat_v5_compatible()` - 普通聊天中的图片
- ❌ 不影响：`coreading_v5_compatible()` - PDF 共读截图
- ❌ 不影响：其他API和功能模块

## 日志示例

压缩成功时的日志：
```
图片缩放: (3024, 4032) -> (1440, 1920)
图片压缩: image.png (3024, 4032) (8.52MB) -> (1440, 1920) (0.85MB, 压缩率 90.0%)
成功添加压缩图片: /path/to/image.png (892160 bytes, image/jpeg)
```

## 注意事项

1. 所有图片都会被转换为 JPEG 格式（即使原始是 PNG）
2. 透明背景会被替换为白色背景
3. 压缩是实时进行的，不会保存压缩后的文件
4. 如需调整压缩参数，修改 `models_mgr.py` 第595-598行的函数调用参数
