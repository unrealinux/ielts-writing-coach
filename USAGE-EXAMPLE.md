# 完整使用示例

一篇 Task 2 作文，从「贴进对话框」到「拿到两份产物」的完整走查。

**下面每一条命令、每一段输出都是真跑出来的**，用的是仓库自带的样例 `evals/samples/sample-task2-essay.txt`，
你可以照着重跑并逐字对照。

---

## 0. 你只需要说这一句话

```
帮我批改这篇雅思作文。

题目：Some people believe that university education should be free for all students.
      Others think students should pay for their own tuition.
      Discuss both views and give your own opinion.

作文：<把作文粘在这里>
```

**题目必须给。** 这不是「建议」，是硬需求——跑题**无法从作文本身看出来**。
一篇跑题的作文往往语言干净、论证充分，是它最好看的时候。不给题目，工具只能拒绝给 TR 打分：

```
## 8. 题目相关度

⚠️ **未提供题目**，无法检查是否偏题（TR-OFF / TR-PART）。

**偏题无法从作文本身看出来**——一篇跑题的作文往往语言干净、论证充分。
必须用 `--prompt <题目文件或题干>` 传入题目才能做这项检查，否则 TR / TA 不应评分。
```

（实跑：`python3 scripts/analyze_essay.py evals/samples/sample-task2-essay.txt --task 2` → 末尾就是上面这段。）

---

## 1. 你最终拿到什么

三份东西，用途不同：

| 产物 | 给谁用 | 内容 |
|---|---|---|
| **对话里的批改** | 你，现在读 | 四项分项分数 + 每项引用了原文哪几句 + 差什么才能进档 |
| `报告.md` | 存档、复习 | 分数卡、逐项诊断、错误清单（按代码）、缺陷归属审计、错误模式小结、6 组 before→after、下一步 3 个动作 |
| `批改稿.docx` | 你，改作文时 | 正文里 **22 条真实 Word 批注**锚定在原句上，斜体段落是改写建议，第二页起是评分页 |

---

## 2. 完整流程：谁在做什么

| 步骤 | 谁做 | 做什么 | 产出 |
|---|---|---|---|
| **0** | 你 | 给题目 + 作文 | — |
| **1** | 脚本 | 客观预分析：字数、句长、词汇重复、衔接手段、错误模式探测、论证支撑度、题目相关度 | 8 节事实表（**不构成分数**） |
| **2** | 模型 | 逐条核对预分析、逐项定档、写报告 | `报告.md` |
| **3** | 脚本 | 审计「同一处缺陷是否被多个评分项重复扣分」 | 审计表 |
| **4** | 脚本 | 从报告生成带 Word 批注的 docx | `批改稿.docx` |
| **5** | 模型 | 呈现产物、说明「需人工确认」的部分 | — |

关键分工：**脚本只提供事实，所有判断由模型做，且每条扣分必须引用原文。**
脚本给的是「20 句里 16 处错误」，不是「GRA 5.5」——分数不能由正则给出。

---

## 3. 逐步实跑

### 第 1 步：客观预分析

```bash
python3 scripts/analyze_essay.py evals/samples/sample-task2-essay.txt \
  --task 2 \
  --prompt evals/samples/sample-task2-prompt.txt \
  --out 预分析.md
```

真实输出的骨架：

```
## 1. 规模
| 词数 | 259 | ✅ 达标（要求 ≥250） |
| 段数 | 5 | ✅ |
| 平均句长 | 12.9 词 | ✅ |
**段落词数分布**：43 / 70 / 72 / 50 / 24
⚠️ 段落严重失衡（最短段不足最长段的 40%），影响 CC。

## 3. 衔接手段
- 连接词总数：13，每句 0.65 个
- **以连接词开头的句子：10 / 20 = 50%**
  - ⚠️ **过半句子以连接词开头 = 机械堆砌**。官方标准把机械使用连接词判为 CC 6 的特征，不是加分项。

## 5. 高频错误模式探测（启发式，需人工确认）
| GRA-ART | 可数名词单数裸用 | 1 | `poor family can` | ... |
| GRA-RUN | 疑似逗号拼接句 | 1 | `However, the government should provide...` | ... |
| LR-CHING | 中式模板套句 | 3 | `with the development of society`；`more and more`；`every coin has two sides` |
| LR-COLL | 介词搭配 | 1 | `pay attention on` | ... |
| LR-REG | 学术文中出现 I think | 1 | `I think` | ... |
> 这些是**正则启发式**，会有误报和漏报。必须回到原文逐条确认后再写入报告。

## 7. 论证支撑度（独立于语法：语法干净也可能论证空洞）
| 具体细节（数字 / 年份 / 专有名词） | 0 | ❌ 为零：全文没有任何可核验的具体信息 |
| 模糊限制语（may / can / could / likely） | 6 | ⚠️ 偏多：无证据的模糊化是空洞，不是谨慎 |

### ⚠️ 判定：论证支撑度不足
命中信号：证据/数据标记 0 处；全文无任何具体细节；模糊限制语 6 处
论证支撑度不足，且同时存在语法错误（错误探测 8 处命中），属复合型问题：
两轴都要改，但 TR 的修复优先级高于语法。

## 8. 题目相关度
**识别到的题型**：discussion_opinion（讨论双方 + 给出自己的观点）
**题干关键词覆盖：5 / 5 = 100%**
✅ 题干关键词覆盖良好，未见偏题信号（仍需人工核对问题部分是否逐条回应）
```

注意第 7 节那句「**两轴都要改，但 TR 的修复优先级高于语法**」——
这是三轴诊断的核心结论：**语法错误多不代表先改语法**。

### 第 2 步：模型写报告

报告第一节就是结论，不用往下翻：

```
## 一句话结论
这是一篇**结构完整、可读性良好、但论证与技术细节都停在 6 分档**的典型作文。
最关键的瓶颈是 **GRA 的错误密度**（20 句里 16 处语法错误，且复杂句比简单句更容易出错）；
提分最快的一步是**先把"论证三追问"用起来**——把 ¶2、¶3 里 4 处光秃秃的断言改成因果链，
TR 与 LR 会同时受益。

## 分数卡
| 项目 | 预估分 | 一句话依据（含原文引用） |
| Task Response | 6.0 | 三个问题部分都回应了，但立场只在 ¶4 出现，¶1 结尾是 "This essay will discuss both sides"，属于"立场未贯穿全文"；6 个主体论点中 4 个是裸断言 |
| Coherence & Cohesion | 6.0 | 五段结构清晰、每段有明确中心句，但 20 句用掉 13 个连接词（0.65/句），且 ¶4 的 "However" 用成了递进而非转折 |
| Lexical Resource | 6.0 | 零拼写错误，有 "reduce the gap between the rich and the poor" 这类可圈可点的表达；但 `education` 重复 8 次而无替换，搭配错误频出（"pay attention on"、"get the knowledge"） |
| Grammatical Range & Accuracy | 5.5 | 复杂结构只用到 if/although/because 状语从句（无关系从句、无被动、无名词化）；错误密度过高（16 处/20 句），且**复杂句恰恰是出错集中区** |
| **总分** | **6.0** | 四项均值 5.875 → 四舍五入到最近 0.5 → **6.0** |
```

**每一行都带原文引用**，这是它和「AI 说你这篇 6 分」的区别。

错误清单是可核对的表格，不是散落的点评：

```
| # | 位置 | 原文 | 代码 | 修改 | 原因 |
| 1 | ¶1 | pay attention **on** the university education | GRA-PREP | pay attention **to** | 固定搭配 |
| 2 | ¶1 | **the** university education | GRA-ART | university education | 泛指抽象概念不加 the |
| 4 | ¶1 | Nowadays, with the development of society and economy, ... | TR-TEMPLATE | （删除，直接切入争议） | 与本题无关的背诵套句 |
| 5 | ¶1 | This essay will discuss both sides. | TR-INCON | This essay argues that ... | 无立场，导致立场不贯穿全文 |
| 8 | ¶2 | If the government **pay** the tuition | GRA-SVA | pays | 主谓一致 |
```

改写是成组的 before → after，每组都说明**为什么这样改**：

```
### 2. ¶2 第一个论点（循环论证 + 残句 + 主谓一致）

**原文**
> Firstly, it can help the poor students to get the knowledge. Because education is very
> important for everyone. If the government pay the tuition, students from poor family
> can also go to university.

**问题**：TR-UNDEV（"教育重要"是循环论证，没有解释为什么该免费）、GRA-FRAG、GRA-SVA、GRA-PLU、LR-COLL

**改写**
> The strongest argument for state funding is that tuition fees ration places by income
> rather than by ability. Where a degree costs several thousand pounds a year, capable
> school-leavers from poorer families must weigh the salary they forgo against a debt
> they may carry for decades, and many rationally choose to work instead.

**改动说明**：这是本次批改最重要的一处改动。原句的论证链是"免费 → 帮助穷人 → 因为教育重要"，
**第三步是循环的**。改写后建立了一条真实机制：费用 → 用收入而非能力分配名额 →
贫困生权衡放弃的工资与债务 → 理性选择工作。规则：每个论点问三次"为什么成立"，
答案写出来就是机制。
```

最后是能直接执行的动作，不是「多练习」：

```
## 下一步 3 个动作
**1. 今天（15 分钟）：冠词专项——把 6 处 "the + 抽象名词" 逐个判断。**
   规则一句话：泛指抽象概念用零冠词（education / knowledge / teaching quality），
   特指前文提过的具体对象才用 the。
**2. 本周：论证深度专项——"追问三次"训练（每天 3 句，共 21 句）。**
**3. 下一篇作文：写之前把题干三个问题部分写在草稿纸顶部，引言最后一句直接给立场。**
**关于时间分配**：本文 259 词、高出下限仅 9 词，说明字数不是问题。
把省下的时间用于写完后的 3 分钟检查，专门扫三类错误：冠词（6 处）、主谓一致（1 处）、
名词单复数（2 处）——这 9 处修掉，GRA 从 5.5 提到 6.0，总分随之从 6.0 变 6.5。
```

### 第 3 步：报告审计

```bash
python3 scripts/audit_report.py examples/report-task2.md
```

```
# 缺陷归属审计：report-task2.md

> 规则：**一处缺陷只归一个评分项**。同一处被两个以上评分项当作扣分证据时，
> 报告必须显式声明它的归属项。

- 逐项诊断中提取到 **24** 条独立引文
- 其中被 **≥2 个评分项**用作证据的：**2** 条
- 归属声明：有
- 审计覆盖：**完整**（有成句引用可查）

| 引文片段 | 出现在哪些评分项 | 已声明归属 |
| `it is good for the society, it can make the country develop ` | CC、GRA、TR | ✅ |
```

为什么需要这一步：一个逗号拼接会同时表现为标点错误（GRA）、指代不清（CC）、甚至逻辑被掩盖（TR）。
三项都据此降档，就是**同一个错误算了三次**，四项各被压低一点、总分可能少 0.5。
审计器把这条规则变成机制，未声明归属时返回非 0。

### 第 4 步：生成带批注的 docx

```bash
python3 scripts/report_to_docx.py \
  --essay evals/samples/sample-task2-essay.txt \
  --report examples/report-task2.md \
  --out 批改稿.docx
```

```
wrote 批改稿.docx
  essay paragraphs : 5
  Word comments    : 22
  italic rewrites  : 6
  model paragraph  : included
  unanchored notes : 1 (listed on the score page, not attached)
validation: ok
```

**输出是字节可复现的**：

```bash
shasum -a 256 批改稿.docx examples/reviewed-task2.docx
# f9f42cd7e9b925d20564681a9304486ab9c7245f69adac47009c1e1cfc040e1d  ← 两个文件相同
```

注意 `unanchored notes : 1` —— 有 1 条批注**锚定失败**，它被列在评分页上而**不会挂到错误位置**。
工具宁可让一条批注「没挂上」，也不让它挂错句子。

### 第 5 步：跨篇追踪（可选，需要 ≥2 篇报告）

把报告放进一个目录，跑：

```bash
python3 scripts/track_progress.py ~/ielts-reports --out ~/ielts-reports/_趋势.md
```

真实输出。这三行来自仓库自带的三篇样例作文各自的批改报告（随包只附其中一份：
`examples/report-task2.md`；三篇都跑一遍就能得到同样的表）：

```
## 1. 分项趋势
| 日期 | 任务 | 词数 | TR/TA | CC | LR | GRA | 总分 |
| 2026-09-13 | Task 2 | 259 | 6.0 | 6.0 | 6.0 | 5.5 | **6.0** |
| 2026-09-13 | Task 2 | 313 | 5.5 | 6.0 | 6.5 | 7.5 | **6.5** |
| 2026-09-13 | Task 2 | 425 | 5.0 | 7.0 | 7.5 | 8.0 | **7.0** |

## 2. 变化（同一任务类型的首篇 → 末篇）
### ⚠️ 不计算趋势变化
所有报告都落在同一天（2026-09-13），**无法判断先后顺序**。
...本脚本拒绝这样做。
下面给出的是**各分项的分布区间**：

| 项目 | 最低 | 最高 | 区间 |
| TR/TA | 5.0 | 6.0 | 1.0 |
| GRA | 5.5 | 8.0 | 2.5 |

## 3. 当前状态与跨档算术
四项总和 **27.5** ／ 当前总分 **7.0** ／ 下一档 **7.5**
**跨档需要四项总和增加 1.5**（达到 29.0）。
```

三篇样例的对比正是这个工具最想说明的一件事：**总分 6.0 → 6.5 → 7.0，
而 TR 是 6.0 → 5.5 → 5.0——语言越好，内容问题越难察觉。**

第 2 节那段「拒绝计算趋势」也是刻意的：同一天的几篇报告按文件名排序再相减，
会得出一个「进步/退步」的数字，但那个数字是虚构的。

---

## 4. 四种常见变体

**Task 1 Academic（图表）**：

```bash
python3 scripts/analyze_essay.py 我的图表作文.txt --task 1 --prompt 题目.txt
```

Task 1 用**另一套判据**：不统计「证据标记/举例标记/因果标记」（在图表题里数字就是任务本身，
"没有举例、没有因果"恰恰是正确的），改为检查 overview 是否存在、纯报数比例、比较类表达、
观点/原因是否泄漏、时态是否混用。

**Task 1 General Training（书信）**：

```bash
python3 scripts/analyze_essay.py 我的书信.txt --task 1gt --prompt 题目.txt
```

书信没有 overview 要求——用 `--task 1` 跑书信会告诉你「概述（overview）｜**未找到**｜❌ **TA 上限 5.0**」，
那是错的。`1gt` 只检查书信专属项：称呼、敬语、称呼与敬语是否匹配、语域。

**只要 docx，不要报告**：先让模型批改出报告，再：

```bash
python3 scripts/report_to_docx.py --essay 我的作文.txt --report 我的报告.md --out 批改稿.docx
```

**只校验现有 docx，不生成**：

```bash
python3 scripts/report_to_docx.py --validate-only 批改稿.docx
# ok   批改稿.docx is a valid package with consistent comments
```

---

## 5. 四种误用会被拦住

| 误用 | 会发生什么 |
|---|---|
| **不给题目** | 第 8 节明确写「未提供题目，无法检查是否偏题」，并声明 **TR / TA 不应评分**（而不是假装算出一个分数） |
| **`--task` 与题干矛盾** | 报告开头插入 `## ⚠️ 输入自相矛盾` 横幅，声明「第 7 节结论不可用」——因为跑错分支不会崩溃，只会产出**自信的错误结论**（比如在书信里报告「overview 已找到 ✅」） |
| **作文与报告不是同一篇** | 硬失败、退出码 1、**删除半成品**，不交付文件：`The report quotes text that does not occur in the essay you passed.` |
| **报告里有错误代码但解析不出错误行** | 硬失败，而不是产出零批注的文档后退出 0 |

实跑第 3 条的完整输出（注意它先把「挂不上的东西」如实数出来，再拒绝交付）：

```
wrote /tmp/x.docx
  essay paragraphs : 5
  Word comments    : 0
  italic rewrites  : 0
  model paragraph  : included
  unanchored notes : 23 (listed on the score page, not attached)
  unplaced rewrites: 6

BUILD FAILED: 0 of 23 quoted fragments were found in the essay.
  The report quotes text that does not occur in the essay you passed.
  Most likely the two files are not a pair: wrong report, or the essay
  was rewritten after it was reviewed.
  essay : evals/samples/sample-task2-offtopic-essay.txt
  report: examples/report-task2.md
  The partial .docx was removed; nothing was delivered.
exit=1
```

对比一下：如果工具「尽力而为」地交付这个文件，你会拿到一份**零批注的文档**，
而它看起来完全正常——这是最坏的结果，因为你不会知道批注丢了。所以这里的正确行为是**不交付**。

---

## 6. 复现这份示例的全部命令

```bash
cd <你放这个 skill 的目录>          # 例如 ~/.agents/skills/ielts-writing-coach

# 第 1 步：客观预分析
python3 scripts/analyze_essay.py evals/samples/sample-task2-essay.txt \
  --task 2 --prompt evals/samples/sample-task2-prompt.txt --out /tmp/预分析.md

# 第 2 步：报告由模型产出（仓库里已有一份：examples/report-task2.md）

# 第 3 步：审计
python3 scripts/audit_report.py examples/report-task2.md

# 第 4 步：生成 docx + 校验 + 与仓库示例比对
python3 scripts/report_to_docx.py --essay evals/samples/sample-task2-essay.txt \
  --report examples/report-task2.md --out /tmp/走查.docx
python3 scripts/report_to_docx.py --validate-only /tmp/走查.docx
shasum -a 256 /tmp/走查.docx examples/reviewed-task2.docx     # 应完全相同

# 第 5 步：跨篇追踪（需要 ≥2 份你自己的报告；本仓库只带 1 份报告，跑不出趋势）
python3 scripts/track_progress.py ~/ielts-reports

# 改完任何东西，跑全量自检
python3 scripts/selfcheck.py        # 205 项
```

---

## 附：两个使用要点

**① 对话里问就行，不用敲命令。** 上面所有脚本都是给模型的工具；
你只要说「帮我批改这篇雅思作文，题目是……」。「生成一份带批注的 Word」也是同一句话的事。

**② 报告里每处「需人工确认」都要真的去看。** 正则启发式会误报也会漏报——
它的定位是**帮你快速找到可疑处**，不是替你做判断。
真正决定分数的三件事工具做不了：**图表数据是否读对、GT 书信三个 bullet 是否全覆盖、
你的论点是否真的成立**。
