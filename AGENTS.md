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

## 编译路径选择（agent 读这里决定走哪条）

**默认：自主蒸馏**——用自己的能力提取/融合（你的 LLM 能力永远可用，零配置），
仓库脚本只做机械步骤（校验/导出）。不要翻 `.env`、不要读任何 key 文件内容（隐私）；
需要判断"脚本路径是否可用"时，跑仓库的 `load_api_key()` 自检命令（下方表格），
它会统一检查环境变量与 .env 文件——不要自己猜测变量名或文件位置。

**语料规模判定（在第 1 步语料准入时自然完成）**：
- 小语料（<8 份 且 <200KB）→ 缺省自主蒸馏，不问不打断
- **大语料（≥8 份 或 ≥200KB）→ 主动提示一次**（给用户知情选择，不擅自决定）：
  1. 先跑 `load_api_key()` 自检
  2. 有 key → 告知："语料较大（N 份/X MB），建议走脚本快速路径（已检测到 key，自动分段/断点/跨批合并更稳，且可版本回归）；也可以继续用我蒸馏——你选？"
  3. 无 key → 告知："语料较大（N 份/X MB），脚本快速路径需要 LLM API key（环境变量 DEEPSEEK_API_KEY 或项目根 .env）；没有 key 我将用自主蒸馏（逐篇处理，较慢且结果不可回归对比）——继续吗？"

| 情况 | 行为 |
|---|---|
| **默认**（用户只说"编译/做顾问"） | **自主蒸馏**：直接开干，不问不打断。LLM 步骤自己做，机械步骤用脚本 |
| 用户明确说"跑脚本 / 自动化 / 快速路径" | 用**仓库代码自检**（不要自己猜 env/文件）：<br>```bash<br>python3 -c "import sys; sys.path.insert(0,'.'); from core.runtime.llm import load_api_key; print('OK' if load_api_key() else 'NO')"<br>```<br>（`load_api_key()` 同时检查环境变量 DEEPSEEK_API_KEY 与项目根 .env 文件——**只输出 OK/NO，不暴露 key 值**）<br>· OK → 走快速路径（`extract_candidates.py` → `merge_candidates.py`）<br>· NO → **问用户**："脚本路径需要 LLM API key（环境变量 DEEPSEEK_API_KEY 或项目根 .env），或改用本 agent 蒸馏？"——此时才问，因为用户明确要脚本 |
| 用户明确说"用自己的模型 / 不要 DeepSeek" | **自主蒸馏**（本来就是默认，直接说明即可） |
| 语料 >30 篇 | 自主蒸馏时也按篇分段处理（每段 ≤18K 字符）；交付前提示人工审核 tensions/evolution 与 quote 抽样 |

一句话：**用户没指定就自己蒸馏；用户指定脚本路径时才查环境变量，没有再问一次。**

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
