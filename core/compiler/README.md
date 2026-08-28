# core/compiler — 编译层（占位，P1 不实现）

未来职责（对应计划书第 5.2 节「必须自研」部分）：

- **原则提炼**：多书 + 访谈 + 演讲 + 案例 → 统一方法论（Method Fusion）
- **证据加权**：观点跨源同现 → 置信度（Evidence Weighting）
- **证据链绑定**：每条原则/规则绑定 来源·章节·原文摘录（Evidence Traceability）
- **冲突与演变**：原则优先级（tension）、思想演变时间线（evolution）

输入：`data/sources/<person>/<type>/*.md`（由 scripts/convert.py 产出）
输出：符合 `schemas/method.schema.yaml`（v0.1）的 method YAML，
      并经 `scripts/validate_schema.py` 校验通过后写入 `data/methods/`。
