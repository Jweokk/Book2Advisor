# Agent 自主蒸馏指南（用自己的 agent + 任意 LLM）

> 这是第二条编译路径：**不使用本仓库的 LLM 脚本**（extract/merge），由你自己的 agent 用自己的模型完成提取与融合——本仓库只提供方法论（准入标准/三重验证/schema）与机械工具（校验/导出）。
> 适用人群：想用自己的 Claude / GPT / Gemini / 其他 agent 蒸馏人物，不想依赖 DeepSeek 或我们的代码。

## 为什么存在这条路径

仓库的脚本快速路径（`docs/COMPILING.md`）自动调用 LLM（默认 DeepSeek，可用 `LLM_MODEL`/`LLM_BASE_URL` 环境变量换成任意 OpenAI 兼容端点）。如果你希望**完全用自己的工具链**（如 Claude Code + Anthropic 模型），就用本指南——LLM 步骤由你的 agent 亲自完成，本仓库脚本只做确定性机械工作。

## 两种蒸馏路径对比

| | 脚本快速路径（COMPILING.md） | Agent 自主蒸馏（本指南） |
|---|---|---|
| LLM 步骤执行者 | 仓库脚本（调 LLM API） | 你的 agent（用自己的模型） |
| 换模型 | `LLM_MODEL` 环境变量（OpenAI 兼容） | 任意（你的 agent 用什么都行） |
| 依赖 DeepSeek？ | 默认是（可换） | 否 |
| 适合 | 想省事、命令行熟练 | 想完全掌控蒸馏过程 |

## 流程（7 步，agent 执行）

### 1. 语料准入
按 `docs/CORPUS-STANDARD.md`：一手来源（本人书/演讲/访谈/致股东信等）5-15 份，时间覆盖全时期；排除二手传记/标题党/AI 生成。

### 2. 逐篇提取候选（用你自己的能力）
对每份语料（超长分段，每段 ≤18K 字符）提取：principles / rules / cases / anti_patterns / diagnostics。
**quote 必须逐字来自原文（≤60 字）**——提取时就保留原文短句，禁止改写。

### 3. 融合（三重验证门槛）
| 门槛 | 问句 | 不通过 |
|---|---|---|
| V1 跨域 | ≥2 个独立语境/语料出现？ | 降级 evidence |
| V2 预测力 | 能推断语料没明说的新问题？ | 降级规则 |
| V3 独特性 | 普通聪明人说得出吗？ | 淘汰 |

跨篇同义合并为一个原则（多 evidence）；证据分级 E3（单源）/ E4（双源）/ E5（三源+）。

### 4. 组装骨架
按 `schemas/method.schema.yaml` 输出 yaml。易错点：
- `sources` 是顶层实体；`evidence.source` 引用 `sources[].id`
- `case.principle` 是数组且至少 1 条；`case.problem` 必填
- rule 的 `trigger`/`diagnose` ≥1 条；principle 的 `confidence` ∈ {high, medium, low}
- 规模参考（薄骨架）：原则 14-20 / 规则 6-10 / 案例 8-12 / 诊断 3-5 / 张力 3-5 / 演变 3-4

### 5. 校验（机械，用仓库脚本）
```bash
python3 scripts/validate_schema.py <model>.yaml    # 必须 exit 0
```
失败按报错逐条修。

### 6. 引用核对（质量红线）
取 evidence quote 前 20 字 grep 原文逐条核对——编造/改写必替换。

### 7. 导出 skill 或使用
```bash
python3 scripts/export_skill.py --model <model>.yaml --out ~/.claude/skills/<person>-method
# 或走 Web/CLI：export METHOD_MODEL=<model>.yaml && python3 scripts/ask.py "问题"
```

## 也可让 agent 直接执行（生成器 skill）

仓库自带生成器 skill（`skills/book2advisor-compiler/SKILL.md`）——把上述 7 步写成 agent 可执行的指令。让 Claude Code 等 agent 加载它，全程自动蒸馏（它会自主完成 LLM 步骤，必要时调用本仓库的机械脚本）。

## 机械工具一览（不依赖 LLM，自由使用）

| 工具 | 作用 |
|---|---|
| `scripts/convert.py` | 文档 → markdown 转换 |
| `scripts/validate_schema.py` | 方法模型结构校验（唯一事实源：schemas/method.schema.yaml） |
| `scripts/export_skill.py` | 方法模型 → 人物咨询 skill 渲染 |
| `templates/advisor-skill-flow.md` | 咨询流程模板（导出 skill 的指令核心） |
