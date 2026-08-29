# 编译指南：从语料到 Method Model

> 目标人物的一句话方法论如何变成可运行的 Method Model（yaml）。
> 完整链路：**语料收集 → convert → 提取候选 → 融合（含验证门槛）→ 校验 → 生成 trigger**。
> 全程约 1-2 小时（语料就绪后），LLM 调用为主，可断点续跑。

## 0. 语料收集（按 docs/CORPUS-STANDARD.md）

- 一手来源：本人演讲/访谈实录、书/自传、官方发布；排除二手解读、AI 生成、软文
- 目标 5-15 份，时间覆盖全时期（思想演变需要）
- 入库格式：`data/sources/<person>/<type>/<id>.md`，带 frontmatter：`source/title/type/date`

## 1. 转换（书/文档 → markdown）

```bash
python3 scripts/convert.py <your-book.pdf> --person <person> --type book
# 或访谈文字稿直接存为 .md 放入 data/sources/<person>/speech/
```

## 2. 提取候选（语料 → 候选 JSON）

```bash
python3 scripts/extract_candidates.py --src data/sources/<person>/speech --out /tmp/<person>-extract
# 每篇一个 JSON（principles/rules/cases/anti_patterns/diagnostics 候选），断点续跑
```

注意：`max_tokens=12000` 已内置（推理模型思考吃预算，太低会截断返回空）；单篇 >18K 字符会截取前段（超长语料请先拆分为多篇 .md）。

## 3. 融合（候选 → Method Model yaml）

```bash
python3 scripts/merge_candidates.py \
    --src /tmp/<person>-extract \
    --person <id> --name <中文名> --domain <领域> --brief <一句话简介> \
    --out data/methods/<person>/<model>-v0.1.yaml
```

两阶段自动融合：LLM 按三重验证门槛（下表）分组决策（合并同义/降级/淘汰）→ 脚本确定性组装 yaml（跨篇候选合并为多 evidence：跨源 ≥3 → E5，=2 → E4，单篇 → E3）并自动过 validate_schema。产物是**骨架初稿**——请人工审核后再用（尤其：补充 tensions/evolution、精修 rule 的 exceptions、核对 evidence quote）。

- **同义合并、跨篇印证**：同一原则多篇出现 → 一个原则多 evidence（"聚焦"= "压强" = "城墙口" → 一个原则）
- **实体规模参考**（薄骨架）：原则 14-20 / 规则 6-10 / 案例 8-12 / 诊断 3-5 / 张力 3-5 / 演变 3-4 段
- 每个实体带中文 `name`；evidence 的 quote **逐字来自原文**（≤60 字）

> ⚠️ 组装易错点（validate 会报但早知早省）：
> - `sources` 是**顶层实体**（与 principles 平级），不是 person 的子字段
> - `case.principle` 是原则 id 的**数组**（`[id]`）；`case.problem` 必填
> - `evidence.source` 必须引用 `sources[].id`（跨实体引用校验）

### 融合门槛（三重验证，宁缺毋滥）

每个候选原则问三句，全部通过才独立成原则：

| 门槛 | 问句 | 不通过 |
|---|---|---|
| V1 跨域 | 该框架出现在 ≥2 个独立语境/语料？ | 只是"一处金句"→ 降级 evidence |
| V2 预测力 | 能推断语料里没明说的新问题？ | 只能复述例子 → 降级为规则 |
| V3 独特性 | 抹掉人名，普通聪明人说得出来吗？ | 常识废话（"要努力"）→ 淘汰 |

- 只过 1 项 → **降级为 rule 或 evidence**（不直接淘汰）
- 0 项 → 淘汰，写入 `data/methods/<person>/rejected/`（含原因，可事后捞回）
- 抄录 V2/V3 判定结果便于追溯

## 4. 校验

```bash
python3 scripts/validate_schema.py data/methods/<person>/<model>-v0.1.yaml   # 必须 exit 0
```

## 5. 生成 trigger（可选但推荐）

principle 加 `trigger: {scenes, signals, not_for}` 能显著提升方法定位准确率：

```bash
python3 scripts/gen_triggers.py   # statement+evidence → LLM 生成 trigger 初稿
python3 scripts/merge_triggers.py # 合并进主 yaml（改前备份 .bak）
```

- `scenes`：用户会在什么情境下问到这个原则；`signals`：典型信号词；`not_for`：不应误触发的情况
- **not_for 是防「万能原则」的关键**：名字带勤/诚/心等泛德性词的原则会被 LLM 无条件选中，not_for 必须覆盖技术选型/外包决策/优先级排序/商务人事协调等泛场景，并针对实际误触发迭代精修

## 6. 评估（四组化，可选但强烈推荐）

```bash
# 1) 为你的模型建评估目录（复制示例模板）
cp -r evaluations/example evaluations/<person>

# 2) 按目标人物改写 questions/ 与 eval-rubric-*.md（rubric 独立编写：只读题面+模型，不读答案）

# 3) 答题（四组：core 40 / lures 10 / confusions 10 / out-of-scope 5）
python3 scripts/batch_ask.py --person <person> --model data/methods/<person>/<model>.yaml --group core
python3 scripts/batch_ask.py --person <person> --model data/methods/<person>/<model>.yaml --group lures
python3 scripts/batch_ask.py --person <person> --model data/methods/<person>/<model>.yaml --group confusions
python3 scripts/batch_ask.py --person <person> --model data/methods/<person>/<model>.yaml --group out-of-scope

# 4) 评分（judge 模型独立于答题模型——双 agent 盲测）
python3 scripts/score_answers.py --person <person> --group core
python3 scripts/score_answers.py --person <person> --group lures --judge-model <其他模型>
python3 scripts/score_answers.py --person <person> --group confusions
python3 scripts/score_answers.py --person <person> --group out-of-scope
```

四组各测什么：

| 组 | 题数 | 测什么 | 评分要点 |
|---|---|---|---|
| core | 40 | 正向质量（答得好不好） | 每题 5 判分点 × 0-2 |
| lures | 10 | 诱饵：字面触发实际不该触发 | 误触发 = 0（容错 0） |
| confusions | 10 | 该触发 A 而非 B（答案须唯一） | 选错陪跑原则扣分 |
| out-of-scope | 5 | 语料空白话题的诚实度 | 显式声明"此为方法外推"=满分，斩钉截铁=0 |

> 评估是「可回归的质检」：模型迭代后重跑同一套题，对比 score-report 即可量化改进/回退。

## 7. 启动

```bash
export METHOD_MODEL=$(pwd)/data/methods/<person>/<model>.yaml
python3 scripts/ask.py "你的问题"            # CLI
cd web && uvicorn app.main:app --port 8000   # Web
```

## 常见坑

1. **max_tokens 不足**：deepseek 系推理模型思考计入预算，提取/推演 ≥12000，评分 ≥800
2. **LLM 空响应/JSON 格式错误**：重试 3-5 次（脚本已内置），仍失败单独重跑该篇
3. **quote 编造**：融合后必须抽检 evidence quote 回原文核对（前 20 字 grep 原文），编造必替换
4. **schema 校验失败**：validate_schema.py 会指出具体字段，逐条修（常见：缺 name、trigger 结构、evidence level 枚举）
