# core/runtime — 运行时（占位，P1 不实现）

未来职责（对应计划书第 7.1 节「五类测试问题」）：

- **诊断**：给定用户问题，按人物的 diagnostic.order 走诊断路径
- **方法定位**：匹配 principle / rule（trigger → diagnose → decisions）
- **推演**：结合 case 与 tension 做情境推演（Novel / Conflict / Boundary 类问题）

输入：`data/methods/<person>.method.yaml`（compiler 编译产物）
对外：方法顾问问答接口（P2+ 实现）
