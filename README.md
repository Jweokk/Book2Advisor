# Book2Advisor — 把一个人的方法论，变成可以随时咨询的 AI 顾问

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

# 2. 配置环境变量
cp .env.example .env
#    编辑 .env：DEEPSEEK_API_KEY（DeepSeek，OpenAI 兼容接口）
#              ADVISOR_PASSWORD（Web 登录密码）
#              METHOD_MODEL（方法模型路径，必填——见步骤 3/4 编译生成）

# 3. 转换语料（书/文档 → markdown）
python3 scripts/convert.py <your-book.pdf> --person jack-welch --type book

# 4. 编译方法模型（语料 → Method Model，校验必须通过）
python3 scripts/validate_schema.py data/methods/<person>/<model>.yaml

# 5. 启动 Web 顾问
cd web && uvicorn app.main:app --host 0.0.0.0 --port 8000
# 或 Docker：docker compose -f web/docker-compose.yml up -d --build

# 6. 浏览器访问 http://localhost:8000 ，输入密码登录，开始咨询
```

> CLI 方式：`python3 scripts/ask.py "你的问题"`（自动加载 METHOD_MODEL 或默认模型）。
> 语料准入标准与编译方法论见 [docs/CORPUS-STANDARD.md](docs/CORPUS-STANDARD.md)。

## 目录结构

```
core/                   # 核心代码
  runtime/              #   运行时：8 步推理链（ask.py / llm.py / prompts.py）
schemas/                # Person Method Model Schema（JSON Schema，9 类实体）
scripts/                # CLI：convert / validate_schema / ask / batch_ask / score / diff
web/                    # Web Advisor：FastAPI + 原生前端（密码登录 + Method Trace 展示）
tests/                  # pytest（14 用例：schema 校验 / 运行时 / 中文化）
docs/                   # 方法论文档（语料准入标准等）
data/
  methods/              # 方法模型（无内置模型（具体人物模型需自行编译，见快速开始））
  sources/              # 语料（版权内容，不随仓库分发）
evaluations/            # 40 题评估集与评分报告（运行产物）
```

## 评估结果

- **40 题评估集**（横跨书内困境到书外新问题 5 类题型），每位人物使用**独立编写的评分标准**（rubric，防循环论证），两位验证人物平均分 **8.5+ / 10**
- **Method Differentiation 成立**：同一问题（如"危机收缩""老功臣处理"），两位人物产出**完全不同的诊断路径**（一位答"亲证数据、观宏观"，一位答"现金流命脉、组织机制"）——核心代码零改动，只换 Method Model
- **Evidence 真实性**：累计 200+ 条证据全部回原文核对（前 20 字 → 中段 → 全文三级匹配），发现并修复的 LLM 编造引用为零容忍
- **版本回归**：多源融合逐版（v0.1→v0.4）评估不退化，组合类题型显著提升

## 致谢

本项目在设计实现中参考了以下开源项目与工具：

- **[book-to-skill](https://github.com/virgiliojr94/book-to-skill)** — Book Compiler 层的主要参考：`structure-not-summary` 抽取规范、方法骨架轻量化、evidence 分层存储
- **[anydoc](https://www.npmjs.com/package/anydoc)** — 文档转换器（office/文本 PDF → markdown）
- **[markitdown](https://github.com/microsoft/markitdown)** — 回退转换器
- **[MinerU](https://github.com/opendatalab/MinerU)** — 扫描型 PDF 转换
- **[DeepSeek API](https://platform.deepseek.com/)** — 默认模型推理服务（OpenAI 兼容接口，可替换）

## License

MIT
