# “智慧文件夹”形成条件和对应的标题

## 按文件分类 (File Category)

条件: 文件在粗筛结果中被归类到特定的 FileCategory (如 document, image, code 等)。
标题示例: "文档", "图片", "代码文件", "音视频文件", "压缩包", "设计文件", "其他文件"。

## 按文件名模式/标签 (Filename Pattern / Tag)

条件: 文件名匹配 FileFilterRule 中 rule_type='filename' 且 action='tag' 的规则，并在粗筛结果的 tags 字段中记录了相应的标签。
标题示例: "草稿文件", "最终版文件", "报告", "合同/协议", "发票/收据", "演示文稿", "周报/月报", "简历", "截图", "相机照片", "微信文件", "下载文件", "会议文件", "带版本号的文件", "备份/旧版文件", "带日期标记的文件"。

## 按项目 (Project)

条件: 文件在精炼结果中关联到通过 ProjectRecognitionRule 识别出的特定 Project。
标题示例: "项目: [项目名称]", "Git 项目", "前端项目", "Python 项目"。

## 按内容主题/关键词 (Content Topic / Keyword)

条件: 文件在精炼结果中提取出特定的 topics 或 key_phrases。
标题示例: "关于 [主题] 的文件", "包含关键词 '[关键词]' 的文件"。

## 按命名实体 (Named Entities)

条件: 文件在精炼结果中识别出特定的 named_entities (人名、地点、组织等)。
标题示例: "提及 [人名] 的文件", "提及 [组织名] 的文件"。

## 按相似性 (Similarity)

条件: 文件在精炼结果的 similar_files 字段中与其他文件有高相似度。
标题示例: "与 '[文件名]' 相似的文件", "相似文件"。

## 按文件元数据 (File Metadata)

条件: 基于粗筛结果中的 modified_time, created_time, file_size, extension 等字段进行分组。
标题示例: "今天修改的文件", "本周修改的文件", "本月修改的文件", "今年修改的文件", "大文件 (>X MB)", ".pdf 文件", ".docx 文件"。

## 按处理状态 (Processing Status)

条件: 基于粗筛结果 FileScreeningResult.status 或精炼结果 FileRefineResult.status。
标题示例: "待处理文件", "处理失败文件", "已忽略文件"。

## 按规则操作 (Rule Action)

条件: 文件匹配了 FileFilterRule 中 action='exclude' 的规则。
标题示例: "已排除文件" (这可能不是一个用户可见的“智慧文件夹”，更像是一个过滤视图)。
这些智慧文件夹的形成将依赖于Rust粗筛填充 FileScreeningResult 表，以及Python精炼处理 FileScreeningResult 并填充 FileRefineResult 和 Project 表的数据。
