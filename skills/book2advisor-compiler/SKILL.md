---
name: book2advisor-compiler
description: "把一个人的书/文章/演讲/访谈/案例编译为「人物方法论顾问」skill（Person Method Model + 可咨询技能）。Use when the user wants to build a person-method advisor for someone from their materials (e.g. '把巴菲特资料做成顾问'), distill a person's methodology into a reusable agent skill, or asks how to create a Book2Advisor-style skill for a new person. 输入：人物资料目录；输出：可安装的人物咨询 skill。"
---

# Book2Advisor 人物方法论编译器

把一个人的资料编译成**人物方法论顾问 skill**——产出物可被任何 agent 加载，回答"XX会怎么看/怎么做这个问题"。

## 输出目标（先看结构再动手）

产出目录 `<person>-skill/`：

```
SKILL.md                  frontmatter(name/description) + 人物身份 + 咨询流程 + 索引
references/principles.md  原则（statement + trigger 场景/信号/not_for + 证据链）
references/rules.md       规则（触发条件/决策映射/例外）
references/cases.md       案例
references/diagnostics.md 诊断路径 + 观点张力 + 思想演变
```

**方法模型结构**（骨架数据，最终以 `schemas/method.schema.yaml` 为准）：
- `person`：id（snake_case）/ name（中文名）/ domain / brief
- `sources`：语料来源表（顶层实体，evidence.source 必须引用它）
- `principles`：原则 14-20 条（statement 一句话 + confidence + trigger{scenes,signals,not_for} + evidence[]）
- `rules`：规则 6-10 条（trigger[] + decisions{条件:决策} + exceptions[] + evidence[]）
- `cases`：案例 8-12 个（context/problem/decision/action/outcome/reasoning/principle[] + evidence[]）
- `diagnostics`：诊断路径 3-5 条（order[] 步骤）
- `tensions`：观点张力 3-5 组（a/b/when_a/when_b）
- `evolution`：思想演变 3-4 段（period/notes）

## 编译流程（7 步）

### 第 1 步 · 语料准入（严格）
按 `docs/CORPUS-STANDARD.md`：
- ✅ 一手来源：本人书/自传、演讲访谈实录、官方发布、致股东信等
- ❌ 排除：二手传记/解读、标题党、AI 生成内容、八卦
- 目标 5-15 份、时间覆盖全时期（思想演变需要）
- 每份标注：来源类型 / 日期 / 篇名

### 第 2 步 · 逐篇提取候选
对每份语料（超长先分段，每段 ≤18K 字符）：
- 用自己的能力提取方法论候选：principles / rules / cases / anti_patterns / diagnostics
- **quote 必须逐字来自原文**（≤60 字，去引号标点差异）——禁止改写、禁止编造
- 宁缺毋滥：只收方法论密度高的；某类无内容则留空

### 第 3 步 · 融合（三重验证门槛，每候选问三句）
| 门槛 | 问句 | 不通过 |
|---|---|---|
| V1 跨域 | 该框架出现在 ≥2 个独立语境/语料？ | 一处金句 → 降级 evidence |
| V2 预测力 | 能推断语料没明说的新问题？ | 只能复述例子 → 降级规则 |
| V3 独特性 | 抹掉人名，普通聪明人说得出吗？ | 常识废话 → 淘汰 |

- 跨篇同义合并：一个原则多 evidence（"聚焦"="压强"="城墙口" → 一个原则）
- 证据分级：跨源 ≥3 → E5，=2 → E4，单篇 → E3
- 通过 1-2 项 → 降级为 rule；0 项 → 淘汰（记录原因，可事后捞回）

### 第 4 步 · 骨架组装
按第 2 节结构组装 yaml，注意易错点：
- `sources` 是**顶层实体**（与 principles 平级）
- `case.principle` 是原则 id 的**数组**；`case.problem` 必填
- `evidence.source` 必须引用 `sources[].id`
- 每个实体带中文 `name`；rule 的 `trigger`/`diagnose` 至少 1 条

### 第 5 步 · 机械校验（用仓库脚本，不依赖 LLM）
```bash
python3 scripts/validate_schema.py <model>.yaml     # 必须 exit 0
```
校验失败 → 按报错逐条修（常见：缺 name、trigger 结构、evidence level 枚举）。

### 第 6 步 · 引用核对（质量红线）
- 抽检 evidence quote：取前 20 字 grep 原文，逐条核对
- 编造/改写 → 替换为原文真实句
- 这是本编译器的信任基石：**quote 必须可溯源**

### 第 7 步 · 导出 skill
```bash
python3 scripts/export_skill.py --model <model>.yaml --out ~/.claude/skills/<person>-method
```
产物即第 2 节结构。安装到 Claude Code / Hermes / Copilot 任一宿主即可使用。

## 脚本辅助对照表（全部不依赖 LLM，可自由使用）

| 场景 | 脚本 |
|---|---|
| 文档转换（PDF/EPUB → markdown） | `scripts/convert.py` |
| 结构校验（骨架是否符合 schema） | `scripts/validate_schema.py` |
| 导出人物咨询 skill | `scripts/export_skill.py` |
| 可选：批量提取候选（脚本自动调 LLM） | `scripts/extract_candidates.py`（如使用请设 LLM_MODEL 环境变量） |
| 可选：自动融合（脚本自动调 LLM） | `scripts/merge_candidates.py`（同上） |

> 推荐：LLM 步骤（提取/融合）**用自己的能力完成**（保证用你自己的模型/agent 蒸馏）；
> 机械步骤（转换/校验/导出）用仓库脚本。两者可自由组合。

## 质量红线（违反即失败）

1. evidence quote 必须逐字来自原文（可 grep 验证），禁止编造
2. validate_schema.py 必须 exit 0
3. 三重验证门槛必须执行（V1/V2/V3），常识废话不得作为原则
4. 产物是**骨架初稿**——交付前提示用户"建议人工审核 tensions/evolution 与 quote 抽样"
