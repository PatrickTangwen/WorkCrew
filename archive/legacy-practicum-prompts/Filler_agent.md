> Archived historical prompt. Not used by the WorkCrew runtime; see `README.md`.

**Filler Agent (Claude):**

仅在week6_work(7月27号-8月4号)里根据以下要求进行操作，不准在别的任何地方修改文件：
`draft.xlsx` 和以下 11 个 program folders 都在同一工作目录下：
Brazil 2015, India 2008, India 2009, India 2010, India 2011,
India 2012, India 2013, India 2014, India 2016, Inida 2017,
kenya 2020
另有参考文件  useful_links.txt
目标：从上述 11 个 folders 中提取每个 program 的信息，
填入 draft.xlsx → sheet "7) Practicum Courses" 的对应列。
----------------------------------------------------------

## 步骤

### 1. 读取参考格式

打开 draft.xlsx 的 "6) Engagement Projects" sheet，
记住 **Project ID*** 和 **Parent Program*** 的命名格式。
"7) Practicum Courses" 中每条 entry 严格沿用同一格式。

### 2. 读取分类标准

打开 draft.xlsx 的 "Main Issue Area Codes" tab，
记录 Standardized Format 下的所有类别，后续映射时使用。

### 3. 逐 folder 提取信息

按以下顺序遍历 12 个 folders：
Brazil 2015 → India 2008 → India 2009 → … → India 2016
→ Inida 2017 → kenya 2020
对每个 folder：

- 读取其中所有文档（PDF, DOCX, XLSX, PPT 等）
- 提取可映射到 "7) Practicum Courses" 各列的字段

### 4. 分类字段映射规则

| 列                           | 规则                                                                                                                                                                                                    |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Main Issue Area(s)** | 匹配步骤 2 中记录的 Standardized Format 类别；若无法精确匹配，选最接近的并在溯源中注明                                                                                                                  |
| **Project Tags**       | 仅从以下选项中选取：Financial Modeling · Impact Assessment · Marketing · Business Strategy/Revenue · Organizational Systems and Behavior · Investing/Endowment · Scaling · Technology Innovation |
| **其余列**             | 根据 folder 内文档如实填写；无法确定的留空                                                                                                                                                              |

### 5. 溯源（每个 cell 必须）

每个填写的字段附一条简短依据，格式：

> `[文件名] 一句话具体理由`
> 示例：
> `[India 2008/Project_Brief.pdf] 标题页注明 sector 为 Healthcare`
> `[India 2012/syllabus.docx, p.2] 课程描述中列出 Financial Modeling 为核心模块`
> 禁止泛泛理由（如"综合判断"）。
> 交叉印证时列出关键 2-3 个来源即可。
> 溯源信息请同时整理为结构化数据（JSON 或单独 sheet），
> 格式：{ "row_id + column_name": "溯源文本" }
> 后续我会据此生成可点击查看来源的交互网页。
