# 发布清单

> 回答一个问题：**发布时直接给 zip 包就够了吗？**
> 简答：**看发布到哪。** 发给同事够用；发布到 GitHub 或 skill 市场都不够。

---

## 0. 三种发布目标，三种要求

| 目标 | zip 够吗 | 还缺什么 | 谁适合 |
|---|---|---|---|
| **私下分享**（同事、朋友、群里） | ✅ **够了** | 无 | 小范围试用 |
| **GitHub 仓库** | ⚠️ 作为 Release 附件 | `LICENSE`、`.gitignore`、README（都已有）| 想让人能提 issue / PR / 看历史 |
| **Skill 市场 / 安装器** | ❌ **不够** | **必须是 git 仓库**，可能还要 marketplace manifest | 想要曝光与一键安装 |

### 为什么"发布"不能只给 zip

zip 是**构建产物，不是真源**。只有 zip 会导致：

- **没有历史**——别人无法 diff 两个版本，无法看你改了什么、为什么改
- **无法协作**——提不了 issue、开不了 PR（本项目 12 个缺陷全部来自对抗性测试，其中数条是"如果早点有人提 issue 就会更早发现"那一类）
- **安装器用不了**——`npx skills add <owner>/<repo>` 这类工具**只认 git 仓库**，不认 zip
- **市场索引不到**——skill 市场按仓库抓取，zip 没有可抓的地址
- **无法追责**——没有 LICENSE 时，使用者不清楚能不能商用、能不能改

本项目的四个同类竞品（[AaronL725](https://github.com/AaronL725/ielts-writing-review-skills)、[Jobo16](https://github.com/Jobo16/ielts-buddy)、[YANZHANLIN](https://github.com/YANZHANLIN/ielts-claude-skills)、[Shpaldik](https://github.com/Shpaldik/OpenIELTS-AI)）**全部以 git 仓库发布**，zip 只作为附件。

**推荐做法**：仓库是真源，zip 挂到 GitHub Release 作为「下载即用」入口。两者都要，不冲突。

---

## 1. 发布前必改（3 项）

| # | 项 | 在哪 | 为什么 |
|---|---|---|---|
| 1 | **`LICENSE` 的版权署名** | `LICENSE` 第 3 行 | 已填 `xieyingfei`（取自 git 配置），要改真实姓名/组织名就改这一行。**注意：不要把说明文字加进 `LICENSE`**——加了 GitHub 会报 `NOASSERTION`，许可证扫描器也识别不了；说明放在 `NOTICE.md` |
| 2 | **版本号** | `SKILL.md` frontmatter 的 `metadata.version` | **唯一真源**。改这里之后必须同步 README 最新条目、`USAGE.md`、`evals/evals.json`——`selfcheck.py` 会校验四处一致，不同步就直接失败 |
| 3 | **zip 文件名** | `USAGE.md` 里的解压示例 | 文档里的文件名与实际包名必须一致 |

改完跑一次：

```bash
python3 scripts/selfcheck.py
```

**全绿才能发。** 它会校验文件完整性、解析逻辑、docx 结构与幂等性、版本五处一致、CI 承诺与文档一致、文档声明的自检项数——任何一项不同步都会失败。

---

## 2. 发到 GitHub

### 2.1 初始化仓库

> ✅ **本地仓库已经初始化并完成首次提交**（分支 `main`，36 个文件，无缓存与个人产物）。
> 你只需要**添加远程仓库并推送**，下面的 `git init` 与首次 commit 可跳过。

<details>
<summary>从零开始时的完整步骤（供参考）</summary>


`.gitignore` 已备好（排除 `__pycache__`、`.DS_Store`、以及**用户产物** `ielts-reports/` `ielts-reviewed/` `*.docx`，但保留 `examples/*.docx`）。

```bash
cd ielts-writing-coach
git init -b main
git add -A
git status          # 确认没有 __pycache__ / .DS_Store / 个人报告被带进去
git commit -m "ielts-writing-coach vX.Y.Z"
git remote add origin git@github.com:<你>/<仓库名>.git
git push -u origin main
```

**`git status` 那一步不要跳。** 用户的批改报告是私人内容，别推进公开仓库。

</details>

**你现在要做的**：

```bash
cd <skill 目录>
git remote add origin git@github.com:<你>/<仓库名>.git
git push -u origin main
```

### 2.2 打 tag 并挂 Release

```bash
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin main --tags
```

然后到 GitHub Release 页面上传 zip 作为附件。

### 2.3 打包与校验和

**用 `git archive` 打包，不要用 `zip -r`。**

```bash
git archive --format=zip --prefix=ielts-writing-coach/ \
  -o ielts-writing-coach-skill-vX.Y.Z.zip vX.Y.Z
shasum -a 256 ielts-writing-coach-skill-vX.Y.Z.zip
```

两个好处，都是实测过的：

- **同一个 commit 打两次，字节完全相同。** `git archive` 把每个条目的时间戳写成 **commit 时间**，
  而不是「打包那一刻」。所以 Release 说明里的 sha256 是**别人可以自己复核的**——`zip -r` 做不到这一点。
- **内容恒等于 `git ls-files`。** 不会有 `.git`、`__pycache__`、`.DS_Store`、用户报告混进去，
  也就不再依赖 `-x` 排除清单；那种清单漏写一项就是隐私事故。

两点注意：

- **换一个 commit 就会得到不同字节**（时间戳来自 commit）。所以校验和要对着 **tag** 打，并与 tag 一起公布。
- 未提交的改动**不会**进包。`git status` 必须是干净的——这反而是好事，它挡住了「把半成品发出去」。

> 历史：v1.12.1 及更早用 `zip -r`，那种包**不可复现**，Release 说明里的 sha256 只能靠发布者自己声明。
> `examples/` 里的 docx 一直是可复现的（生成器固定了时间戳），它的 sha256 也可以公开核对。

### 2.4 仓库描述建议

**和 README、发布说明用同一个顺序**：先讲报告，再讲分数。GitHub 的描述会出现在搜索结果里，
是门面的一部分——它曾经是唯一还写着「四项评分」的地方，因为改 README 时没人想到它。

```
雅思作文批改 AI agent skill：逐句证据 + 错误模式 + 定向改写 + Word 真批注 + 跨篇趋势；
分数给区间不给单点。零依赖（Python 标准库）、离线，自带全量自检与校准记录。
```

> ⚠️ **这一条自检管不到**：它在 GitHub 的仓库元数据里，不在仓库文件里。
> 改文案时要**手动**同步（`gh repo edit --description`），并记住它与 README 是同一件事。

### 2.5 交付物的渲染验证（手动，仅 macOS）

自检能证明 docx 是一个**结构合法的 OOXML 包**，但证明不了它**画得出东西**——一个空的 `document.xml` 同样合法。
能区分这两者的是 Apple 的排版引擎：

```bash
qlmanage -t -s 800 -o /tmp/ql examples/reviewed-task2.docx
open /tmp/ql/reviewed-task2.docx.png
```

看图确认五件事：标题、题干、作文正文、斜体重写句、中文批注**都在**，并且**分页正确**。
这一步**没有进 CI**：`qlmanage` 走 QuickLook，需要一个窗口服务器会话，CI runner 上不保证有；
一个会挂起或随机失败的任务比没有这个任务更糟。同理，**Word 里的批注侧栏也验证不了**——
它需要真的装 Word。这一点已写在 `USAGE.md` 的边界清单里，别在发布说明里暗示已验证。

---

## 3. 发到 skill 市场 / 支持安装器

这一类的共同前提：**先有公开 git 仓库**。

| 平台类型 | 需要什么 | 本项目现状 |
|---|---|---|
| `npx skills add <owner>/<repo>` 类安装器 | 公开仓库，且仓库里能定位到 `SKILL.md` | ⚠️ **仓库形状与 zip 形状不同，见下** |
| skill 市场（按仓库索引） | 公开仓库 + 清晰的 README | ✅ README 已备 |
| 需要 manifest 的市场 | 通常要 `manifest.json` 或 `.claude-plugin/marketplace.json` | ❌ 未提供——**按目标市场的格式要求再补**，不要凭空造一个格式 |

### 3.1 仓库形状 ≠ zip 形状（这一条以前写错过）

| | 形状 |
|---|---|
| **发布 zip** | `ielts-writing-coach/SKILL.md` —— 因为用 `git archive --prefix=ielts-writing-coach/` 打的 |
| **git 仓库** | `SKILL.md` 在**仓库根**，没有 `ielts-writing-coach/` 这一层 |

这两者**不等价**，而本文件以前只写「`<name>/SKILL.md` 的目录形状正确」——那描述的是 zip，
却被当成了仓库的凭据。安装器读的是**仓库**，所以这句话当时是**没验证过的推断**。

**已核实的部分**（2026-09-23）：`npx skills`（v1.7.0，来自 `vercel-labs/skills`）能把
`unrealinux/ielts-writing-coach` **解析为合法来源**：

```
◇  Source: https://github.com/unrealinux/ielts-writing-coach.git
```

它的 `init` 帮助也写明支持两种形状（`creates <name>/SKILL.md or ./SKILL.md`），
所以仓库根放 `SKILL.md` 是**被支持的形状之一**。

**未核实的部分**：本机到 github.com 的 **HTTPS** 连接不稳定（`git clone` 报
`Failed to connect to github.com port 443`、npm 也超时），所以**端到端安装没有跑完**。
「形状正确」目前仍是**基于工具文档与来源解析的推断，不是实测通过的安装**。

**要真正验证**（在任意一台网络正常的机器上，一条命令）：

```bash
npx skills add unrealinux/ielts-writing-coach --list   # 只列出，不安装
```

能列出 `ielts-writing-coach` 即证明形状可用；列出为空或报错，则把仓库改成
`<name>/SKILL.md` 子目录结构（同时要改 `git archive --prefix`，否则 zip 会多一层）。

**关于 manifest**：本项目刻意**没有**预先创建 manifest，因为：

- 各市场格式不统一，猜错格式等于多一份需要同步、且没人读的元数据
- 版本真源已放在 `SKILL.md` frontmatter 的 `metadata.version`——**那是安装器唯一会读的文件**，放这里不会漂移
- 等你确定目标市场，按它的文档加，并**把它接进 `selfcheck.py` 的版本一致性校验**（否则又多一处会漂移的版本号）

---

## 4. 发出去之前，最后确认这 9 件事

```
□ python3 scripts/selfcheck.py 全绿
□ LICENSE 的占位符已替换
□ SKILL.md / README / README.en / 使用说明 / evals.json 五处版本一致（selfcheck 已校验）
□ examples/reviewed-task2.docx 渲染一次，确认不是「结构合法但画不出东西」（见 2.5）
□ git status 干净（`git archive` 只打已提交内容，脏工作区会静默少文件）
□ 版本号 tag 与 zip 文件名一致，zip 由 `git archive` 打在 tag 上（见 2.3）
□ 解压发布的那个包，在里面再跑一次 selfcheck
□ 首次发布或改过目录结构时，在**网络正常**的机器上跑 `npx skills add <owner>/<repo> --list`（见 3.1）
□ 发布说明**先讲报告、再讲分数**，并写清：分数是**区间估计**、绝对分典型误差约半个档位、
  排序比绝对值可信；不读图表图片；启发式会误报漏报
```

倒数第二条是**对产物本身**的验证，不是对工作区的验证：包可能在打包环节出错
（少了文件、多带了一份报告），而工作区自检对此一无所知。
`unzip -d /tmp/x <zip> && cd /tmp/x/ielts-writing-coach && python3 scripts/selfcheck.py`。

最后一条最重要——**把边界写在最显眼的地方，比让人踩坑后再解释便宜得多。**

---

## 5. 可以直接复制的发布说明

**写的时候按这个顺序**：先讲**报告**（它可靠的部分），再讲**分数**（并立刻说明它有区间）。
反过来写会让人以为卖点是估分——而估分恰好是这份工具最弱的一环（实测平均误差约半个档位）。

```markdown
## ielts-writing-coach vX.Y.Z

AI agent skill：雅思写作 Task 1 / Task 2 **批改**。给它题干和作文，它给回一份报告：
**逐句错误定位、错误模式、定向改写、下一步先改什么**。

**为什么值得用**——把一句模糊的「我作文不太好」变成一张可执行清单：
哪几类错误在反复出现、先改哪一个、改完能换来什么。这部分是它的强项。

**分数请当成区间读。** 在 24 篇真实考生作文上实测过：绝对分的**平均误差约半个档位**，
且它会把分数收拢在中间。所以报告给的是**区间**（如 5.5–6.5）而不是「你的分数」，
并且**排序比绝对值可信**——拿它看进步，比拿它估分可靠。

**能做什么**
- **逐句证据**：每一条扣分都引用原文的具体句子，不写「词汇较丰富」这类无证据评价
- **错误代码化**：37 个统一代码（`GRA-ART` 冠词、`LR-COLL` 搭配…），归纳成**错误模式**而不是逐个纠错
- **定向改写**：before → after，每一组都说明为什么这样改
- **带真实 Word 批注的 `.docx`**：零依赖直接写 OOXML，锚定原句、支持嵌套批注、**字节可复现**
- **跨篇追踪**：分项趋势 + 持续性问题（跨篇重复出现才算系统性弱点）
- **报告审计**：检查同一处缺陷是否被多个评分项重复扣分（那会造成系统性低估）
- **校准记录**：附模板与脚本，让你量出这个工具**对你自己**偏多少

**怎么装**：解压到 `~/.agents/skills/`，见 `USAGE.md`

**先看效果再看文档**：`examples/` 里有现成的批改报告与带 22 条批注的批改稿

**边界（请先读）**
- 分数是**区间估计**，非官方成绩；绝对分典型误差约半个档位
- 仍未与**考官评分**比对过——上述测量用的是一份公开标注语料，出处未能独立核实
- **不读图表图片**——Task 1 的数据正确性需人工对照
- 启发式探测会有误报漏报，报告中每处标注「需人工确认」
- 只覆盖写作（Task 1 / Task 2），不含口语、听力、阅读

MIT License ｜ 全量自检全绿 ｜ 评测用例见 `evals/evals.json`

**校验和**（由 `git archive` 打在 tag 上，同一 tag 两次打包字节相同，可自行复核）
<sha256>  ielts-writing-coach-skill-vX.Y.Z.zip
```

> **发布说明里不要写的东西**：任何没有来源的数字（「绝大多数考生…」「Band 8+ 很罕见」）。
> 这个项目在 `SKILL.md` 里写过一次，直接导致分数被压缩，实测斜率掉到 0.32——
> 详见 `references/calibration-evidence.md`。

---

## 6. 不发布也想让人用？

直接把 zip 发过去即可，**装完无需重启**——运行中的 harness 会监视 skill 根目录。对方三步：

```bash
unzip ielts-writing-coach-skill-vX.Y.Z.zip -d ~/.agents/skills/
python3 ~/.agents/skills/ielts-writing-coach/scripts/selfcheck.py
# 然后说：帮我批改这篇雅思作文
```

---

## 7. 怎么请人试用

「发出去」和「有人真的用」是两件事。这一节是后者需要的东西。

### 7.1 让对方**先判断值不值得装**

**绝大部分人不会为了评估一个工具去装它。** 所以邀请的第一句不该是安装命令，
而是 [`examples/`](examples/) 里那份现成的报告与批改稿——它们不用装就能打开。

顺序：**先给产物 → 再给安装命令 → 最后才讲边界**。

### 7.2 可以直接复制的邀请（私聊 / 群里发）

```
试一个雅思作文批改 skill？想请你帮我看一眼。

【不用装就能判断】这里有一份它批改过的样例报告 + 带 Word 批注的批改稿：
<Release 链接>
看那份报告像不像对你有用的反馈就行，工具本身先不用管。

【想真跑一遍，3 分钟】
unzip ielts-writing-coach-skill-vX.Y.Z.zip -d ~/.agents/skills/
然后对你的 AI 说：帮我批改这篇雅思作文。题目：<题目>  作文：<粘上作文>

【先说清边界，免得你踩坑】
· 分数只是**区间**，实测误差约半个档位——**别拿它估分**，看它指出的问题。
· 不读图表图片，Task 1 的数据要你自己对照图表。
· 没在 Word 里验证过批注的显示。
· 需要你的 agent 支持 skill 格式（`<name>/SKILL.md`）。

【跑完愿意的话告诉我一句】：哪里说错了 / 哪里漏了 / 装的时候卡在哪。一句就够。
```

### 7.3 让对方**报什么**才修得动

「感觉还行」修不了任何东西。所以要在邀请里点名问，并且问得**具体到能直接变成 issue**：

| 问什么 | 为什么问这个 |
|---|---|
| **装上了吗**？卡在哪 | 安装是整个链路里唯一没验证过的一环（见 §3.1），这一条最可能出问题 |
| **它的批注落对句子了吗** | docx 的锚定是有精度处理的（宁可不挂也不挂错），外部机器上是否稳定未知 |
| **哪一处扣分你不同意**（引用它说的那句） | 直接测判据，是最值钱的反馈 |
| **它漏了什么你或老师指出的问题** | 漏报比误报更难自己发现 |
| **分数 vs 你的预期** | 校准数据；但**别把它当主问题**，分数本来就是最弱的一项 |
| 跑了 `selfcheck.py` 吗？输出是什么 | 环境问题一眼可辨 |

### 7.4 有 GitHub 账号的，走 issue 模板

`.github/ISSUE_TEMPLATE/trial.md` 是同一组问题的表单版。
**但不要指望它**——雅思学习者多半没有 GitHub 账号，私聊里回一句才是常态。

### 7.5 想要真正有价值的那份数据

让试用人**用他自己的 2–3 篇作文**跑一遍，并把 `templates/calibration-log.md` 填了发回来。
这同时得到两样东西：他知道这个工具对他偏多少，项目拿到**第一批真实用户的准确性数据**——
而这是它至今**从未有过**的（现有测量用的是一份公开语料，出处无法独立核实）。

**这一步要在私聊里请，不要写进 README**：那是求人帮忙，不是产品说明。
