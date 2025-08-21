# 实现标签系统的方法

## 使用全文搜索 (FTS5)

这是在 SQLite 中实现高效标签搜索、同时避免中间表的**最佳实践**。它将标签问题转化为一个文本搜索问题。

**思路：**
将一个文件的所有标签ID（或标签名）拼接成一个用空格分隔的字符串，然后利用 FTS5 虚拟表对这个字符串进行高速索引。

1. **表结构设计**

    ```sql
    -- 标签定义表
    CREATE TABLE t_tags (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        type TEXT NOT NULL,  -- 标签类型
    );

    -- 粗筛结果表
    CREATE TABLE t_file_screening_results (
        id INTEGER PRIMARY KEY,
        file_path TEXT NOT NULL,
        -- 其他字段...
        -- 我们将在这里存储一个供人阅读的标签列表，是用逗号分隔的ID列表，但这个字段不用于高性能搜索
        tags_display_ids TEXT
    );

    -- FTS5 虚拟表 (用于高性能搜索)
    -- 注意：这里的 `tags_search_ids` 列存储的是用空格分隔的标签ID
    CREATE VIRTUAL TABLE t_files_fts USING fts5(
        tags_search_ids,  -- 这个列将被全文索引
        content='t_file_screening_results', -- 告诉FTS5内容存储在t_file_screening_results表中（可选，但推荐）
        content_rowid='id'
    );
    ```

2. **保持数据同步 (使用触发器)**

    这是实现该方案自动化和“不想维护”的关键。我们需要创建触发器，在 `t_file_screening_results` 表发生变化时，自动更新 `t_files_fts` 虚拟表。

    ```sql
    -- 插入文件时，自动更新FTS表
    CREATE TRIGGER trg_files_after_insert AFTER INSERT ON t_file_screening_results
    BEGIN
        -- 假设新插入的行的 tags_display_ids 是 '1,5,10'
        -- 我们把它转换成 '1 5 10' 这样的形式存入FTS表，是空格分隔的标签ID
        INSERT INTO t_files_fts (rowid, tags_search_ids)
        VALUES (NEW.id, REPLACE(NEW.tags_display_ids, ',', ' '));
    END;

    -- 删除文件时，自动更新FTS表
    CREATE TRIGGER trg_files_after_delete AFTER DELETE ON t_file_screening_results
    BEGIN
        DELETE FROM t_files_fts WHERE rowid = OLD.id;
    END;

    -- 更新文件时，自动更新FTS表
    CREATE TRIGGER trg_files_after_update AFTER UPDATE ON t_file_screening_results
    BEGIN
        DELETE FROM t_files_fts WHERE rowid = OLD.id;
        INSERT INTO t_files_fts (rowid, tags_search_ids)
        VALUES (NEW.id, REPLACE(NEW.tags_display_ids, ',', ' '));
    END;
    ```

    **注意**: 为了让 FTS 把每个标签ID当成一个独立的词，ID之间必须用**空格**分隔
3. **查询**

    查询变得非常简单和高效！

    - **查询包含标签 `5` 和 `10` 的文件 (AND):**

        ```sql
        SELECT content_rowid FROM t_files_fts WHERE tags_search_ids MATCH '5 AND 10';
        ```

    - **查询包含标签 `5` 或 `10` 的文件 (OR):**

        ```sql
        SELECT content_rowid FROM t_files_fts WHERE tags_search_ids MATCH '5 OR 10';
        ```

    - **查询包含标签 `5` 但不包含标签 `3` 的文件 (NOT):**

        ```sql
        SELECT content_rowid FROM t_files_fts WHERE tags_search_ids MATCH '5 NOT 3';
        ```

**优点:**

- **性能极高**：FTS5 就是为这类查询设计的，速度非常快，媲美甚至超越中间表方案。
- **查询语法强大**：支持 AND, OR, NOT 等复杂逻辑。
- **实现了“不想维护”**：通过触发器，开发者完全不用关心 FTS 表的存在，只需操作主表即可。

**缺点:**

- 设置略复杂（需要创建虚拟表和触发器）。
- 标签ID本身不能包含空格。
- 增加了存储开销（FTS索引本身需要空间）。

## 结论与最终建议

**FTS5 方案完美地满足了你的需求：**

1. **高效：** 查询性能极高，不输于传统的中间表方案。
2. **简洁：** 从应用开发者的角度看，你只需要操作 `t_file_screening_results` 主表，触发器为你处理了一切，实现了“不想维护中间表”的目标。查询语法 (`MATCH`) 也比复杂的 `JOIN` 和 `GROUP BY` 简洁得多。

**所以，如果你想在 SQLite 中设计一个足够简洁且高效的标签系统，请果断选择 FTS5 方案。**
