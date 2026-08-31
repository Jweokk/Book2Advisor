# Book2Advisor — 把一个人的方法论，变成可以随时咨询的 AI 顾问

> **[English](README.en.md) | 中文**

> 输入一个人的书、文章、演讲、访谈与案例，输出一个**可追溯、可推演**的「人物方法论顾问」——一个 Web 应用。
> 它回答的不只是"这个人说过什么"，而是——**按这个人的方法，他会怎么想**。

## 它解决了什么问题

市面上的"书籍问答"（RAG）能回答"书里说了什么"，但回答不了两类问题：

1. **书外新问题**——书里没有直接答案（如"这位企业家会怎么看 AI 取代工人？"）
2. **决策咨询**——"按这个人的方法，我该先看什么？"

Book2Advisor 用 **Person Method Model（人物方法模型）** 解决：先把人物语料**编译**成结构化的方法论骨架（原则 / 规则 / 案例 / 诊断路径 / 观点张力 / 思想演变），运行时再按骨架**推演**——书内困境直接引用，书外新问题按方法外推，并且**逐条标注"书中依据 vs 方法推演"**，杜绝幻觉引用。

## 方法的核心优点

- **Method Transfer（方法迁移）**：书中没有的新问题，也能按此人的方法论给出可追溯的推演——不依赖原文"恰好提到"，而是依赖对方法论的**结构化理解**。这是本项目与资料问答的本质区别，也是终极验证判据
- **Evidence First（证据优先）**：每条原则/规则绑定原文证据（E1-E5 分级，E5 = 多源印证），全部 quote 逐字可回原文核对——**不编造"他说过"**
- **引用 / 推演分离**：答案中"他说过的"（带出处）与"按他方法推演的"（显式标注）严格区分，读者永远知道哪句是原话、哪句是推理
- **思想演变处理**：观点张力（tensions）+ 思想时间线（evolution），早晚期观点冲突时按时间回答，不平铺矛盾
- **换人只换语料**：Method Model 驱动，切换人物**零代码改动**——已用两位语料形态完全不同的人物（自传体 vs 内部讲话体）验证
- **可审计的推理链**：每次回答输出 8 段 Method Trace（问题理解 → 诊断路径 → 方法定位 → 案例 → 证据 → 推演标注），每一步可回查
- **薄骨架设计**：方法模型只保留高置信度方向性内容（每人物 16-28 条原则），不做全量规则引擎、不做纯 RAG——低成本、可维护、可审计

## 与其他方法对比

### vs 通用 RAG 书籍问答

| 维度 | 通用 RAG | Book2Advisor |
|---|---|---|
| 书外新问题 | 无方法可依，只能拼凑相似片段 | **Method Transfer**：按方法论外推 |
| 引用可信度 | 检索相似段落，易断章取义、张冠李戴 | 原则 ↔ 证据绑定，E1-E5 分级，逐字可溯 |
| 观点冲突 | 相关段落平铺，自相矛盾不自知 | tensions + evolution 时间线处理 |
| 决策咨询 | 给"书中说法"，不给"该怎么办" | 完整决策链：诊断路径 → 方法 → 建议 |
| 人物辨识度 | 谁的书都答成同一套百科腔 | 诊断路径与原则组合体现人物差异（**Method Differentiation**） |

### vs 把全部语料塞进 LLM 长上下文

| 维度 | 长上下文直塞 | Book2Advisor |
|---|---|---|
| 成本 | 每问都吃全部语料（几十万字 token） | 语料**预编译**为薄骨架，运行时只定位相关原则 |
| 一致性 | 长输入下输出漂移、遗忘、幻觉 | Schema 约束 + 证据绑定 + 引用/推演强制分离 |
| 可审计性 | 黑箱，无法解释"为什么这么答" | 8 段 Method Trace 全程可查 |

### vs book-to-skill 类"书 → Agent 技能"项目

book-to-skill（本项目 Book Compiler 层的参考）把书编译为 agent 可加载的技能文件。Book2Advisor 在其之上补上了**方法论顾问缺失的三块**：

1. **Person Method Compiler**：多源融合（同义合并 / 跨源印证升级 / 冲突检测 / 思想演变）——单本书之外，访谈、演讲、案例统一进入模型
2. **Method Runtime**：8 步推理链（问题分类 → 诊断路径 → 方法定位 → 案例检索 → 证据收集 → 推演 → 标注）——从"技能文件"升级为"完整推理引擎"
3. **评估体系**：40 题评估集 + 独立评分标准（rubric）+ 版本间回归对比 + Method Differentiation 验证——方法论的**质量可量化、可回归**

## 架构

```
                     ┌─────────────────────────────────────┐
  书 / 文章 / 演讲    │  编译通道（离线，确定性 pipeline）     │
  / 访谈 / 案例 ────► │  Package Compiler → Person Method    │
                     │  Compiler（同义合并/跨源印证/冲突检测） │
                     └──────────────────┬──────────────────┘
                                        │ Person Method Model
                     ┌──────────────────▼──────────────────┐
                     │  运行时（Method Runtime）              │
  用户问题 ─────────► │  问题分类 → 诊断路径 → 方法定位 →       │
                     │  案例检索 → 证据收集 → 推演 → Method   │
                     │  Trace（8 段，LLM 推理）               │
                     └─────────────────────────────────────┘
```

## 快速开始（Web 方式）

```bash
# 1. 克隆并安装依赖
git clone https://github.com/jweokk/Book2Advisor.git
cd book2advisor
pip install -r web/requirements.txt
#    可选：文档/语料转换回退器（convert.py 在 anydoc 不可用时自动回退）
#    pip install markitdown

# 2. 配置环境变量
cp .env.example .env
#    编辑 .env：DEEPSEEK_API_KEY（LLM API key，默认 DeepSeek）
#              METHOD_MODEL（方法模型路径，必填——见步骤 3-5 编译生成）
#    换模型：LLM_BASE_URL / LLM_MODEL 环境变量（任意 OpenAI 兼容端点，默认 DeepSeek 不变）

# 3. 转换语料（书/文档 → markdown）
python3 scripts/convert.py <your-book.pdf> --person <person> --type book

# 4. 编译方法模型（语料 → 候选提取 → 融合 → Method Model，完整流程见 docs/COMPILING.md）
python3 scripts/extract_candidates.py --src data/sources/<person>/book --out /tmp/<person>-extract
#    （融合汇总为 data/methods/<person>/<model>-v0.1.yaml，含三重验证门槛）

# 5. 校验（必须 exit 0）
python3 scripts/validate_schema.py data/methods/<person>/<model>-v0.1.yaml

# 6. 启动 Web 顾问
cd web && uvicorn app.main:app --host 0.0.0.0 --port 8000
# 或 Docker：docker compose -f web/docker-compose.yml up -d --build

# 7. 浏览器访问 http://localhost:8000 ，开始咨询
```

## 导出 Skill（让 Claude Code / Hermes 等 agent 直接咨询）

方法模型编译好后，一条命令导出为 agent 可加载的人物咨询 skill：

```bash
python3 scripts/export_skill.py --model data/methods/<person>/<model>.yaml --out ~/.claude/skills/<person>-method
# 产物：SKILL.md + references/{principles,rules,cases,diagnostics}.md
# 安装：复制到 ~/.claude/skills/（Claude Code）、~/.hermes/skills/（Hermes）、~/.copilot/skills/ 等
# 立即体验：python3 scripts/export_skill.py --model data/methods/example/person-example-v0.1.yaml --out /tmp/example-method
```

之后 agent 会在你问"<人物>会怎么看这个问题"时自动加载该 skill，按「书中依据 vs 方法推演」强制分离的方式回答（详见 docs/SKILL-EXPORT.md）。

**两种蒸馏路径**（编译人物模型时）：
- **脚本快速路径**：`scripts/extract_candidates.py` → `scripts/merge_candidates.py`（脚本自动调 LLM，默认 DeepSeek，可换模型）——见 docs/COMPILING.md
- **Agent 自主蒸馏**：用自己的 agent + 任意 LLM 完成提取与融合（不依赖本仓库的 LLM 脚本）——见 docs/AGENT-DISTILLATION.md，或让 agent 加载 `skills/book2advisor-compiler` 生成器 skill


> CLI 方式：`python3 scripts/ask.py "你的问题"`（自动加载 METHOD_MODEL）。
> 语料准入标准见 [docs/CORPUS-STANDARD.md](docs/CORPUS-STANDARD.md)，编译全流程（提取/融合/三重验证/trigger/评估）见 [docs/COMPILING.md](docs/COMPILING.md)。

**评估（可选但强烈推荐）**：建 `evaluations/<person>/`（复制 `evaluations/example/` 模板并改写），跑四组评估——`batch_ask.py --person <person> --model <model.yaml> --group core|lures|confusions|out-of-scope` + `score_answers.py --person <person> --group <group>`（judge 模型独立于答题模型，双 agent 盲测）。详见 docs/COMPILING.md 第 6 节。

## 目录结构

```
core/                   # 核心代码
  runtime/              #   运行时：8 步推理链（ask.py / llm.py / prompts.py）
schemas/                # Person Method Model Schema（JSON Schema，9 类实体）
scripts/                # CLI：convert / extract_candidates / validate_schema / ask
                        #      / gen_triggers / merge_triggers / batch_ask / score_answers
skills/                 # 生成器 skill（book2advisor-compiler：agent 自主蒸馏指令）
templates/              # 咨询流程模板（export_skill 渲染进每份人物 skill）
data/methods/example/   # 示例方法模型（导出演示 + 测试 fixture）
web/                    # Web Advisor：FastAPI + 原生前端（Method Trace 展示）
tests/                  # pytest（真实 LLM 集成测试：运行时 / schema / 转换单测）
docs/                   # 方法论文档（语料准入标准 / 编译指南）
data/
  methods/              # 方法模型（无内置模型——具体人物模型需自行编译，见快速开始）
  sources/              # 语料（版权内容，不随仓库分发）
evaluations/            # 评估集：example 模板（questions/ + rubric）+ 各人物的运行产物
```


## 方法论借鉴与独立改进

Book2Advisor 在演进中吸收了「书/人 → AI 技能」方向两个开源项目的方法论，并结合自身的"可追溯 Web 顾问"形态做了独立改进：

**借鉴 [cangjie-skill](https://github.com/kangarooking/cangjie-skill)（RIA-TV++ 流水线）**

- **principle.trigger 触发场景设计**（scenes / signals / not_for 三段式）——解决"原则选不准"：方法定位优先按 trigger 匹配，not_for 防「万能原则」（名字沾边即乱入）误触发
- **三重验证（V2 预测力 / V3 独特性）**——融合阶段显式门槛：淘汰"只能复述例子"与"普通聪明人也能说的常识"候选，1 重验证通过的降级为规则而非直接淘汰
- **压力测试三组制（诱饵题 / 混淆题）**——评估不只测"答得好"，还测"会不会乱调用、会不会选错原则"

**借鉴 [nuwa-skill](https://github.com/alchaincyf/nuwa-skill)（女娲）**

- **边缘诚实度（超范围题）**——语料未覆盖的话题必须显式声明"此为方法外推"，斩钉截铁编造本人立场 = 0 分
- **双 agent 盲测评分**——答题 agent 与评分 agent 分离（LLM 自评 skill 质量准确率仅约 46%），评分模型可独立指定
- **泛问识别（GENERAL_QA 分类）**——概念讨论/闲聊不再被强行套用经营原则，改为礼貌引导用户补充具体决策场景
- **边界声明（coverage）**——推演 prompt 强制对语料空白话题显式标注推断性质

**独立改进（超越参考项目的部分）**

- **交付形态**：静态 skill 文件 → 可追溯的 Web 顾问（证据 E1-E5 分级、quote 逐字可回原文、引用/推演强制分离）
- **Method Transfer**：书外新问题按方法论结构化外推，输出可审计的 8 段 Method Trace
- **思想演变处理**：观点张力（tensions）+ 时间线（evolution），早晚期观点冲突按时间回答，不平铺矛盾
- **换人只换语料**：Method Model 驱动，双人物（自传体 vs 内部讲话体）零代码改动验证
- **评估四组化**：core（正向质量）+ lures（诱饵，容错 0）+ confusions（选择唯一性）+ out-of-scope（边缘诚实度），题目/评分标准可回归对比

## 致谢

本项目在设计实现中参考了以下开源项目与工具：

- **[cangjie-skill](https://github.com/kangarooking/cangjie-skill)** — trigger 触发场景设计、三重验证门槛、诱饵/混淆压力测试（见上节）
- **[nuwa-skill](https://github.com/alchaincyf/nuwa-skill)** — 边缘诚实度评分、双 agent 盲测、泛问识别、边界声明（见上节）
- **[book-to-skill](https://github.com/virgiliojr94/book-to-skill)** — Book Compiler 层的主要参考：`structure-not-summary` 抽取规范、方法骨架轻量化、evidence 分层存储
- **[anydoc](https://www.npmjs.com/package/anydoc)** — 文档转换器（office/文本 PDF → markdown）
- **[markitdown](https://github.com/microsoft/markitdown)** — 回退转换器
- **[MinerU](https://github.com/opendatalab/MinerU)** — 扫描型 PDF 转换
## License

MIT
