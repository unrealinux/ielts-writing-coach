# 示例产物

不用装任何东西，先看这两份文件就能判断这个工具适不适合你。

| 文件 | 看什么 |
|---|---|
| `report-task2.md` | **批改报告长什么样**——分数卡、逐项诊断（门槛/证据/差什么）、23 条错误清单、缺陷归属审计、6 组 before→after 改写、下一步动作 |
| `reviewed-task2.docx` | **带 Word 批注的批改稿**——用 Word / Pages / WPS 打开，右栏有 22 条真实批注，点开可看；正文里斜体段落是改写建议；第二页起是评分页 |

两份文件是**同一篇作文**的两种产出：报告给人读，docx 给人改。

## 这对样例的来源

- 题目与学生作文：`evals/samples/sample-task2-prompt.txt` 与 `sample-task2-essay.txt`
- 这是一篇**刻意写坏的样例**（含冠词、主谓一致、逗号拼接等 16 处真实语法错误），用于演示批改能力，不是真实考生作文

## 自己重跑一遍

```bash
# 生成报告产物（需要先让 agent 批改，或直接用已有报告）
python3 scripts/report_to_docx.py \
  --essay evals/samples/sample-task2-essay.txt \
  --report report-task2.md \
  --out /tmp/重跑.docx

# 校验生成的包
python3 scripts/report_to_docx.py --validate-only /tmp/重跑.docx
```

**输出是字节可复现的**：同样的输入得到同样的文件，可以和这里的示例逐字节比对
（`shasum -a 256 reviewed-task2.docx`）。

## 其他样例

`evals/samples/` 下还有三组**输入**样例，覆盖不同失败模式：

| 样例 | 失败模式 | 看点 |
|---|---|---|
| `sample-task2-essay.txt` | 语法错误密集 | GRA 5.5、16 处错误、40% 句子以连接词开头（机械衔接） |
| `sample-task2-hollow-essay.txt` | 论证空洞 | **零语法错误**但 8 个论点全无展开 → TR 5.5 |
| `sample-task2-offtopic-essay.txt` | 跑题 | 语言最好（GRA 8.0）却答了另一个问题 → TR 5.0 |
| `sample-task1-chart-essay.txt` | Task 1 无概述 | 缺 overview（TA 上限 5.0）+ 100% 纯报数 + 时态混用 |

三篇 Task 2 样例的中点总分是 6.0 / 6.5 / 7.0，而 TR 是中点 6.0 / 5.5 / 5.0——
**语言越好，内容问题越难察觉**，这是这个工具最想说明的一件事。
