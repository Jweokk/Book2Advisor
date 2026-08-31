# Skill 导出与安装

> 把已编译的方法模型导出为 agent 可加载的「人物咨询 skill」，让 Claude Code / Hermes / Copilot 等 agent 直接咨询。

## 导出

```bash
python3 scripts/export_skill.py \
    --model data/methods/<person>/<model>.yaml \
    --out ~/.claude/skills/<person>-method
```

产物：

```
<person>-method/
  SKILL.md                  frontmatter(name/description) + 人物身份 + 咨询流程 + 核心方法 + 索引
  references/principles.md    全部原则（trigger 触发场景 + 证据链）
  references/rules.md         规则（触发/决策/例外）
  references/cases.md         案例
  references/diagnostics.md   诊断路径 + 观点张力 + 思想演变
```

## 安装（任选宿主，格式通用）

| 宿主 | 位置 |
|---|---|
| Claude Code | `~/.claude/skills/<name>/` |
| Hermes | `~/.hermes/skills/<name>/` |
| Copilot CLI | `~/.copilot/skills/<name>/` |
| 跨 agent 通用 | `~/.agents/skills/<name>/` |

安装后，agent 会在用户问"<人物>会怎么看这个问题"时自动加载该 skill（frontmatter description 负责触发判断）。

## 使用示例

> 用户：巴菲特会怎么看我把全部积蓄投进一只 AI 股票？
>
> agent（加载 skill 后）：
> - **诊断路径**：投资决策 → 匹配「投资诊断路径」
> - **书中依据**：原则「能力圈」：*"我们的原则是，看不懂的生意不做"*（1998 年致股东信，loc）
> - **方法推演**（显式标注）：按方法论外推——单一标的 + 市场最热板块，安全边际不足；建议"输了也不影响生活"的比例参与
> - **越界诚实**：语料未覆盖生成式 AI 行业，以上为方法外推

## 快速体验（无真实模型也可）

仓库自带迷你示例模型：

```bash
python3 scripts/export_skill.py \
    --model data/methods/example/person-example-v0.1.yaml \
    --out /tmp/example-method
# 查看 /tmp/example-method/SKILL.md 即可了解产物结构
```

## 质量边界（诚实说明）

- skill 版没有 Runtime 代码的确定性（8 步链由宿主 agent 按 SKILL.md 指令执行）
- 质量保障来自**流程模板的强约束**（引用/推演分离、越界诚实、证据可溯源——见 `templates/advisor-skill-flow.md`）
- 同一方法模型可同时用于：Web / CLI / API / Skill——形态之间互不影响
- 模型更新后重新导出即可（导出是确定性渲染，可回归）
