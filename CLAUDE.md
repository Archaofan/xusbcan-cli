# CLAUDE.md（xusbcan-cli 项目规则）

面向 AI Agent 的 CAN 总线调试工具（Python + python-can + CLI + MCP）。

## 隐私与开源管理规则（硬约束，最高优先级）

1. **`docs/` 不进 git**：`docs/` 是内部设计文档（架构方案、评审记录等），含实现细节与决策过程，**禁止提交到 git**，已加入 `.gitignore`。内部方案只留在本地。
2. **README 只写「使用方式 + 目标展望 + 参与号召」**：README 面向外部（将来开源公开），禁止出现架构分层、内部实现、厂商 SDK 封装细节、设计决策、评审结论等内容。
3. **git 按开源公开标准管理**：提交内容、commit message、代码注释都要经得起公开审查——不得出现本机绝对路径（如 `D:\...`）、真实客户/项目/ECU 名称、内部 IP、账号、密钥、令牌。
4. **厂商 SDK 二进制不进仓库**：如 `zlgcan.dll` 等由用户自取；第三方许可证原文放 `third_party/NOTICES`。
5. **提交前隐私自查**：每次 `git add` 前，检查 diff 是否含敏感信息（绝对路径、真实客户名、密钥等）。

## 技术约定

- 核心运行时依赖仅 `python-can`；MCP 依赖走 `[mcp]` optional extra。
- 厂商差异隔离在 `src/xusbcan/adapters/`，core / cli / mcp 不得出现厂商概念。
- 输出契约：`Result`（`error.code` 枚举化）+ `CanFrame` 序列化契约（`data` 为小写十六进制、`channel` 不进 JSON）。
- 测试：pytest（用 `virtual` 后端 + 注入假适配器），无硬件可全部跑通。
- 真机验证相关脚本放 `scripts/`，不混入正式包。

## 常用命令

```bash
python -m pytest tests/ -q          # 跑全部测试（无硬件）
python -m ruff check src tests      # lint
python -m mypy src/xusbcan          # 类型检查
python -m xusbcan.cli list          # CLI 冒烟
python tests/test_mcp_stdio.py      # MCP stdio 端到端
```
