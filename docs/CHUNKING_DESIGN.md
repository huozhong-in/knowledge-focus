# Chunking Design - Tokenizer解耦架构

## 设计问题

在实现Docling最佳实践时，遇到了一个关键的技术挑战：

### 原始问题
- Qwen3-Embedding-0.6B模型需要1024维embedding
- 系统使用API方式调用embedding服务（Ollama/LM Studio）
- HybridChunker需要tokenizer进行chunk大小控制
- 无法直接使用API模型的tokenizer

### 解决方案：Tokenizer解耦架构

#### 核心思想
将chunking的tokenizer与embedding模型完全解耦：
1. **Chunker tokenizer**: 仅用于chunk大小估算和控制，使用通用tokenizer
2. **Embedding generation**: 通过API调用实际的embedding模型

#### 实现细节

```python
# multivector_mgr.py中的实现
def _init_chunker(self):
    # 使用通用tokenizer进行chunk大小控制
    tokenizer = HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained("microsoft/multilingual-MiniLM-L12-H384"),
        max_tokens=512,  # 保守的chunk大小
    )
    
    self.chunker = HybridChunker(
        tokenizer=tokenizer,
        merge_peers=True,
    )
```

#### 优势
1. **API友好**: 支持Ollama、LM Studio等API服务
2. **性能优化**: 用户可以使用GGUF等优化格式的模型
3. **稳定性**: 通用tokenizer确保chunk大小控制的一致性
4. **灵活性**: embedding模型可以随时切换，不影响chunking逻辑

## 配置说明

### config.py中的设置
```python
EMBEDDING_DIMENSIONS = 1024  # 已设置为Qwen3模型的维度
```

### embedding模型支持
- **Qwen3-Embedding-0.6B**: 1024维，32k上下文，支持自定义维度32-1024
- **其他模型**: 通过API方式支持任何embedding模型

## 使用流程

1. **Chunking阶段**: 
   - 使用通用tokenizer估算chunk大小
   - HybridChunker基于文档结构进行智能分块
   
2. **Embedding阶段**:
   - 通过API调用实际的embedding模型
   - 生成高质量的1024维向量

## 测试验证

运行以下测试验证配置：
```bash
cd api
python multivector_mgr.py
```

检查日志中的关键信息：
- Chunker初始化成功
- Tokenizer解耦架构说明
- Embedding维度配置正确

## 最佳实践总结

1. **架构分离**: chunking逻辑与embedding模型解耦
2. **API优先**: 支持多种embedding服务接口
3. **性能考虑**: 避免不必要的模型下载
4. **维度匹配**: 确保向量维度与存储配置一致

这种设计使得系统既能享受Docling的先进chunking能力，又能灵活使用各种embedding模型服务。
