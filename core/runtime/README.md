# core/runtime — 运行时

职责：

- **诊断**：给定用户问题，按人物的 diagnostic.order 走诊断路径
- **方法定位**：匹配 principle / rule（trigger → diagnose → decisions）
- **推演**：结合 case 与 tension 做情境推演（Novel / Conflict / Boundary 类问题）

输入：`data/methods/<person>.method.yaml`（compiler 编译产物）
对外：方法顾问问答接口（8 步推理链）
