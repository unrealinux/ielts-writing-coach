# WorkBuddy 上架指南

> 一句话：**跑 `python3 scripts/build_workbuddy.py`，拿到 `dist/ielts-writing-coach-workbuddy-v<版本>.zip`，在 [open.workbuddy.cn](https://open.workbuddy.cn) 创建技能并提交审核。**

WorkBuddy（腾讯，CodeBuddy 同族）的技能市场读的是**另一套 frontmatter**：`display_name` / `description_zh` / `examples_zh` / 顶层 `version` / `author` 都是必填，而本仓库原来的 SKILL.md 只有 `name` + `description`。所以不能直接传仓库，需要一份**专供上架的 zip**。

## 1. 一条命令打上架包

```bash
python3 scripts/build_workbuddy.py --author "你的入驻主体名称"
```

- `--author` 必须与开放平台认证的**主体名称一致**，否则审核过不了。默认值是 `xieyingfei`（与 `LICENSE` 相同）。
- 输出 `dist/ielts-writing-coach-workbuddy-v1.17.2.zip`，**包内只有一个顶层目录** `ielts-writing-coach/`（平台要求 `{skill-name}/SKILL.md` 这个形状）。
- 版本号**不写死在包外**：脚本从 `SKILL.md` 的 `metadata.version` 取，所以跟着仓库版本走，不会出现第二处版本号。

脚本自己校验这四件事，任一条不成立就直接失败，不会产出坏包：

1. 顶层只有 `ielts-writing-coach/` 一个目录
2. WorkBuddy 的 8 个必填字段都在
3. 包内版本 == `metadata.version`
4. SKILL.md 里提到的 `references/` `templates/` `scripts/` 文件全部真的在包里

## 2. 包里放了什么

| 内容 | 说明 |
|---|---|
| `SKILL.md` | 生成的 WorkBuddy frontmatter + 仓库原有正文（正文一字未改） |
| `references/` `templates/` | 原样 |
| `scripts/` | 运行时脚本（`analyze_essay.py` 等 6 个 + `report_format.py`）；**排除** `selfcheck.py`、`check_stdlib_only.py`、`build_workbuddy.py`——它们依赖 README/USAGE/evals，装进用户机器只会显得是坏的 |
| `examples/` | 现成批改报告 + 带 22 条批注的 docx，给用户看产物长什么样 |
| `LICENSE` `NOTICE.md` | 上架资产的授权声明，别省略 |

**不包含**：`evals/`、`.github/`、`README*.md`、`USAGE*.md`、`RELEASING.md`。市场详情页的展示文案来自 frontmatter，不读 README。

## 3. 上架流程（开放平台）

1. 打开 <https://open.workbuddy.cn> → 「立即入驻」
2. 完成认证：个人（中国大陆二代身份证 + 人脸）或企业（营业执照 + 法人/腾讯云/公众号授权）
3. 认证通过后到「设置 → 开发者信息」填**开发者昵称**——不填不能发布资产
4. 进入技能业务，**创建技能**，上传第 1 步的 zip
5. 填基础信息（名称、图标、分类、简介按页面要求；文案直接用 frontmatter 里的 `description_zh` / `description_en`）
6. **提交审核** → 通过后发布上线
7. 上线后在客户端「专家·技能·连接器 → 技能 → 技能市场」里可搜到，卡片展示使用量/安装量

上传后解析失败，先对照 [技能基础结构](https://open.workbuddy.cn/docs/skill#技能基础结构) 自查目录形状；仍定位不到就发邮件到 `openworkbuddy@tencent.com`（官方文档给的通道）。

## 4. 审核前必查

- [ ] `python3 scripts/selfcheck.py` 全绿（仓库本体没坏）
- [ ] `python3 scripts/build_workbuddy.py --author "主体名称"` 输出四行校验全过
- [ ] 解压 zip，用 `ielts-writing-coach/SKILL.md` 起一段真实对话，确认能跑通一次批改
- [ ] 详情页文案没有承诺「官方评分」——技能正文明确写「预估分，非官方成绩」，上架文案也要一致
- [ ] 示例（`examples_zh/en`）里**不含真实用户作文**；仓库的 `.gitignore` 已把 `ielts-reports/` `*.docx` 挡在版本库外，别手动塞进去

## 5. 已知风险（没验证过的，不要当成已验证）

| 风险 | 说明 |
|---|---|
| **客户端要 python3** | 技能靠 `python3 scripts/*.py` 干活，只用标准库。WorkBuddy 有 Windows 客户端，**Windows 上 `python3` 是否存在、是否要写 `python`，没验证过**。若目标用户多是 Windows，SKILL.md 里需要加一句回退写法。 |
| **积分消耗** | 平台按任务复杂度扣积分；本技能一次批改要读多个 `references/` 文件，官方提示「复杂技能积分消耗通常较高」。 |
| **数据外发** | 用户贴进来的作文是私人内容。技能本身不联网，但**执行环境的模型调用会读全文**；上架文案要如实说明「作文内容会随对话发送到模型」。 |
| **审核标准未知** | 审核时长、是否需要图标/截图规格、zip 体积上限，官方文档都没写——按平台页面要求来，别猜。 |

## 6. 和本地安装版的差别

| | 本地（Claude Code / Pi / `npx skills add`） | WorkBuddy 市场 |
|---|---|---|
| SKILL.md frontmatter | `name` + `description` + `metadata.version` | 8 个必填字段 + 顶层 `version`；正文相同 |
| 安装方式 | 解压到 `~/.agents/skills/` 或从 git 仓库 | 市场点「+」安装 |
| 版本真源 | `SKILL.md` 的 `metadata.version` | 同一个（构建时注入） |

两份 SKILL.md 的**正文永远相同**——`build_workbuddy.py` 每次从仓库那份重新生成，不要手改包里的文件。
