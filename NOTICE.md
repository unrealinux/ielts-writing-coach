# 说明与致谢

`LICENSE` 只包含标准的 MIT 正文——这样 GitHub 与各类许可证扫描器才能正确识别为 MIT。
与许可相关的说明、以及对第三方思路的致谢放在这里。

## 许可

本项目以 **MIT License** 发布，全文见 [`LICENSE`](LICENSE)。

## 版权署名

`LICENSE` 里的署名为 `xieyingfei`，取自 `git config --global user.name`。
想换成真实姓名或组织名：

```bash
sed -i '' 's/^Copyright (c) 2026 .*/Copyright (c) 2026 你的名字 or Org/' LICENSE
```

## 关于第三方

本项目的**代码与文字全部为原创**，未复制任何第三方源码。

以下设计**受公开项目启发**（仅思路，非代码或文字）：

- 「教师式页边短标签」与「一处缺陷不重复扣分」两条思路，受
  [ChanglinY/IELTS-essay-grading-agent](https://github.com/ChanglinY/IELTS-essay-grading-agent)（MIT）
  的公开说明启发。相关致谢也写在 [`README.md`](README.md) 的版本记录里。
- 「输出侧结构校验」的做法，参考了
  [AaronL725/ielts-writing-review-skills](https://github.com/AaronL725/ielts-writing-review-skills)（MIT）
  公开的校验脚本设计思路。

## 关于 IELTS

评分标准部分（[`references/band-descriptors.md`](references/band-descriptors.md)）是对 IELTS 公开评分标准的
**中文改写摘要**，非逐字引用；正式评分以剑桥、英国文化教育协会（British Council）与 IDP 发布的
官方 Public Band Descriptors 为准。

IELTS 是 British Council、IDP 与 Cambridge 的商标。本项目与三者**无关联、未获其背书**，
也不是官方产品。所有分数均为**预估**，不构成官方成绩。
