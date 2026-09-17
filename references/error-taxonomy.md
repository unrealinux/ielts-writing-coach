# 错误代码表与高频错误库

## 一、代码表（批改时必须使用）

格式：`域-代码`。每条错误在报告中写成一行：位置 → 原文 → 代码 → 修改 → 原因。

**每个代码都有一个「页边标签」（margin tag）**——即 `report_to_docx.py` 写进 Word 批注的短英文词
（如 `GRA-ART` → `Articles`）。报告里用代码（精确、可统计），Word 页边用标签（短、可扫读）。
两者的映射由 `scripts/ielts_codes.py` 统一维护，不要在报告里自造标签。

> **为什么要有标签**：页边扫一眼看到 `Articles` 出现五次，比读五句解释更能让人意识到
> "这是我的系统性问题"。标签的价值在**可扫读**，不在简短。

### GRA — 语法范围与准确性

| 代码 | 名称 | 典型表现 |
|---|---|---|
| GRA-SVA（`Agreement`） | 主谓一致 | `The number of cars have increased` / `People thinks` |
| GRA-TENSE（`Tense`） | 时态 | 全文时态漂移；`In 1990, the figure is 30%` |
| GRA-ART（`Articles`） | 冠词 | 缺冠词、误用 the/a、不可数名词前加 a |
| GRA-PLU（`Singular/plural`） | 名词单复数 | `informations` / `advices` / `equipments` / `a research` / `many student` |
| GRA-PREP（`Preposition`） | 介词 | `depend of` / `in the other hand` / `discuss about` |
| GRA-FRAG（`Fragment`） | 残句 | 从句独立成句：`Because the government did not act.` |
| GRA-RUN（`Run-on`） | 粘连句 / 逗号拼接 | `The city is crowded, it needs more housing.` |
| GRA-CLAUSE（`Clause`） | 从句结构 | 关系从句缺成分；`which is shows`；that/which 混用 |
| GRA-WO（`Word order`） | 语序 | 疑问语序用于陈述；副词位置错误 |
| GRA-VOICE（`Voice`） | 语态 | Task 1 流程图应用被动却用主动；被动滥用 |
| GRA-COMP（`Comparison`） | 比较结构 | `more better` / `as much as twice` / 比较对象不对等 |
| GRA-PUNC（`Punctuation`） | 标点 | 逗号连接两个完整句；缺逗号导致歧义；分号误用 |

### LR — 词汇资源

| 代码 | 名称 | 典型表现 |
|---|---|---|
| LR-COLL（`Collocation`） | 搭配 | `make a progress` / `do a research` / `solve the problem of X`（搭配不当）/ `learn knowledge` |
| LR-WF（`Word form`） | 词形 | `developement` / `successfully` 当形容词 / 名词动词混用 |
| LR-WW（`Word choice`） | 选词 | 意思偏了：`economic` vs `economical`；`affect` vs `effect` |
| LR-SP（`Spelling`） | 拼写 | 拼错；英式/美式混用（colour/color 同文混用） |
| LR-REG（`Informal`） | 语域 | 学术文中出现 `kids` / `a lot of` / `stuff` / `things` / `get` / `really` / `guys` |
| LR-REP（`Repetition`） | 重复 | 同一实词在 250 词中出现 ≥8 次而无替换 |
| LR-CHING（`Chinglish`） | 中式英语 | `open the light` / `with the development of society and economy` / `more and more` / `I very like` |
| LR-IDIOM（`Cliche`） | 习语误用 | 生造搭配；直译成语（`Every coin has two sides` 滥用） |

### CC — 连贯与衔接

| 代码 | 名称 | 典型表现 |
|---|---|---|
| CC-REF（`Reference`） | 指代 | `this` / `it` / `they` 指代不明；`this problem` 前文未出现 |
| CC-LINK（`Linking`） | 连接手段 | 误用（`On the contrary` 当作 `In addition` 用）；缺失；机械堆砌 |
| CC-PARA（`Paragraphing`） | 分段 | 一段到底；一句一段；段落失衡；分段点无逻辑 |
| CC-PROG（`Flow`） | 信息推进 | 段内句序混乱；后句不承接前句；结论引入新观点 |
| CC-TOPIC（`Topic sentence`） | 中心句 | 段落无中心句；中心句与段内内容不符 |

### TR / TA — 任务回应 / 任务达成

| 代码 | 名称 | 适用 | 典型表现 |
|---|---|---|---|
| TR-OFF（`Off-topic`） | 偏题 | T2 | 段落内容与题目争议无关 |
| TR-PART（`Missed part`） | 漏答 | T2 | 题干某部分未回应 |
| TR-UNDEV（`Underdeveloped`） | 论证不足 | T2 | 只有断言无解释/例证 |
| TR-GEN（`Vague`） | 空泛 | T2 | `something should be done` / `very important` |
| TR-INCON（`Position shifts`） | 立场不一致 | T2 | 引言与结论矛盾 |
| TR-TEMPLATE（`Template`） | 模板化 | 通用 | 与题目无关的背诵套句 |
| TA-OVER（`No overview`） | 缺概述 | T1 | 无 overview 段 |
| TA-DATA（`Data error`） | 数据错误 | T1 | 数字/趋势错报；by/to 混用 |
| TA-FEAT（`Key feature missed`） | 关键特征遗漏 | T1 | 未提及最显著趋势 |
| TA-OPINION（`Opinion in Task 1`） | 加入观点 | T1 | Task 1 出现原因、建议、评价 |
| TA-BULLET（`Bullet missed`） | 漏 bullet | T1-GT | 书信某个 bullet point 未覆盖 |
| TA-TONE（`Tone`） | 语气不一致 | T1-GT | 正式信中混入非正式表达 |

## 二、中国考生高频错误（按出现频次排序，批改时优先扫描）

1. **冠词**（GRA-ART）——中文无冠词系统，这是最高频且最难自察的错误。三类子问题：
   - 可数名词单数裸用：`Government should ...` → `The government` / `Governments`
   - 特指与泛指混淆：`The technology has changed our life` → `Technology has changed our lives`
   - 固定搭配：`in the long term` / `on the other hand` / `at the same time`
2. **主谓一致**（GRA-SVA）——被长主语或插入语干扰：`The number of students who study abroad have risen`
3. **名词单复数**（GRA-PLU）——特别是抽象名词与不可数名词：`informations`、`advices`、`researches`、`knowledges`、`equipments`、`a good news`、`many homeworks`
4. **时态一致**（GRA-TENSE）——Task 1 描述过去数据时切到现在时；Task 2 中 should/will/would 混用
5. **搭配错误**（LR-COLL）——高频清单：
   - ❌ `learn knowledge` → ✅ `acquire/gain knowledge`
   - ❌ `make a progress` → ✅ `make progress`
   - ❌ `do a research` → ✅ `conduct/carry out research`
   - ❌ `solve the problem of pollution` → ✅ `tackle pollution` / `address the issue of pollution`
   - ❌ `open the light` → ✅ `turn on the light`
   - ❌ `touch the society` → ✅ `come into contact with society`
   - ❌ `improve my English level` → ✅ `improve my English`
   - ❌ `pay attention on` → ✅ `pay attention to`
   - ❌ `depend of` → ✅ `depend on`
   - ❌ `discuss about` → ✅ `discuss`
   - ❌ `in the other hand` → ✅ `on the other hand`
   - ❌ `according to my opinion` → ✅ `in my opinion`
   - ❌ `With the development of society and economy` → 删除，直接切入题目
6. **中式直译**（LR-CHING）：
   - ❌ `more and more people` → ✅ `a growing number of people` / `an increasing proportion of`
   - ❌ `I very like` → ✅ `I really like` / `I am very fond of`
   - ❌ `although ... but ...` → ✅ 二者只留一个
   - ❌ `because ... so ...` → ✅ 二者只留一个
   - ❌ `With the rapid development of ...` → 换具体动因
   - ❌ `Every coin has two sides` → 换具体权衡表述
   - ❌ `Last but not least` → ✅ `Finally` / `More importantly`
7. **连接词堆砌**（CC-LINK）——`Firstly, Secondly, Moreover, Furthermore, In addition, Besides, What's more` 连续使用，段段如此。6 分的典型特征。
8. **口语化**（LR-REG）——`a lot of`、`lots of`、`kids`、`things`、`stuff`、`get`、`big`、`good`、`bad`、`nowadays`（滥用）
9. **逗号拼接**（GRA-RUN）——`China has a large population, it needs more resources.`
10. **残句**（GRA-FRAG）——`Because the government did not take action.` / `Which is why I disagree.`

## 三、批改输出要求

错误清单之后**必须**给出模式小结，格式：

```
错误模式小结
- GRA-ART 11 处，其中 8 处为"可数名词单数裸用"（Government should... / City needs...）
  → 不是笔误，是冠词系统缺失。专项：a/the/∅ 三分类练习，重点在抽象名词与泛指。
- LR-COLL 4 处，集中在 make/do/take 万能动词
  → 专项：动词+名词搭配表，替换 make/do 为具体动词（conduct / impose / implement）。
- CC-LINK 22 个连接词 / 21 句 = 每句一个，且 5 次 Moreover
  → 不是"连接词不够"，是"逻辑推进不够，靠连接词硬接"。专项：删掉一半连接词，改为指代与词汇衔接。
```

**重复错误必须标注出现次数**，单次出现只列一条。模式比个例值钱。
