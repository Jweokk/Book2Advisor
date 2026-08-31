# AGENTS.md — 给 agent 的仓库指南

> 本文件被 Claude Code / Codex / Copilot 等 agent 自动读取。在仓库内工作时请先读本节。

## 项目是什么

**Book2Advisor**：把一个人的书/文章/演讲/访谈编译成结构化的「人物方法模型」（Person Method Model），变成可咨询的 AI 顾问（Web / CLI / API / Skill 四种形态）。

核心概念：
- **Person Method Model**：yaml 骨架（原则/规则/案例/诊断路径/观点张力/思想演变 + 证据链）
- **Method Transfer**：书外新问题按方法论推演（回答标注「书中依据 vs 方法推演」）
- **证据优先**：每条原则绑定原文证据（quote ≤60 字，E1-E5 分级），杜绝编造

## 目录速览

```
core/runtime/       运行时：ask.py（8 步推理链）/ llm.py（LLM 封装）/ prompts.py
scripts/            编译工具链：convert → extract_candidates → merge_candidates
                    → validate_schema → gen_triggers/merge_triggers → export_skill
schemas/            method.schema.yaml（方法模型的唯一事实源）
skills/             book2advisor-compiler（生成器 skill：agent 自主蒸馏指令）
templates/          advisor-skill-flow.md（咨询流程模板，export_skill 渲染用）
docs/               方法论文档（CORPUS-STANDARD 语料准入 / COMPILING 编译指南
                    / SKILL-EXPORT 导出 / AGENT-DISTILLATION agent 自主蒸馏）
evaluations/example/ 四组评估模板（core/lures/confusions/out-of-scope）
web/                FastAPI + 原生前端（可选消费端之一）
data/methods/example/ 示例模型（导出演示 + 测试 fixture）
```

## 常用命令链

```bash
# 编译新人物（脚本快速路径）
python3 scripts/convert.py <book.pdf> --person <id> --type book
python3 scripts/extract_candidates.py --src data/sources/<person>/<type> --out /tmp/<person>-extract
python3 scripts/merge_candidates.py --src /tmp/<person>-extract --person <id> --name <中文名> \
    --domain <领域> --brief <简介> --out data/methods/<person>/<model>-v0.1.yaml
python3 scripts/validate_schema.py data/methods/<person>/<model>-v0.1.yaml   # 必须 exit 0

# 导出人物咨询 skill
python3 scripts/export_skill.py --model data/methods/<person>/<model>.yaml --out <skill 目录>

# 使用
export METHOD_MODEL=$(pwd)/data/methods/<person>/<model>.yaml
python3 scripts/ask.py "问题"                    # CLI
cd web && uvicorn app.main:app --port 8000       # Web
```

## 硬约束（违反即失败）

1. **validate_schema.py 必须 exit 0**——任何方法模型改动后必须校验
2. **evidence quote 必须逐字来自原文**（≤60 字）——融合/修改后抽检（前 20 字 grep 原文）
3. **三重验证门槛**（V1 跨域 / V2 预测力 / V3 独特性）——常识废话不得作为原则
4. **代码规范**：中文注释与报错；异常细化（LLMError 统一）；绝对路径；子进程超时 120s
5. **LLM 配置**：`core/runtime/llm.py` 读 `LLM_BASE_URL` / `LLM_MODEL` 环境变量（默认 DeepSeek，OpenAI 兼容）——不得硬编码其他厂商
6. **仓库洁净**：`.env` / tokens / 人物真实模型（data/methods/ 除 example/）/ 版权语料（data/raw、data/sources）不进 git；example/ 除外
7. **merge 产物是骨架初稿**——交付前提示人工审核（tensions/evolution/quote 抽样）

## 常用参考

- 语料准入标准：`docs/CORPUS-STANDARD.md`
- 完整编译指南（含 agent 自主蒸馏路径）：`docs/COMPILING.md` + `docs/AGENT-DISTILLATION.md`
- 方法模型 schema：`schemas/method.schema.yaml`（改模型结构前必读）
- 测试：`tests/`（导出器测试 `tests/test_export_skill.py`；修改脚本后跑 `pytest tests/`）
