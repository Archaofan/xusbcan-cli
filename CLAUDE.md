# CLAUDE.md（xusbcan-cli 项目规则）

面向二次开发与 AI Agent 的**公开**约定。真机验证、架构细节、本机脚本只在本地 `docs/` / `scripts/`（不进 git）。

Cursor 另有始终生效规则：`.cursor/rules/privacy-git.mdc`（与本节一致，提交前必遵）。

## 隐私与开源管理（硬约束）

1. **`docs/` 与 `scripts/` 不进 git**：内部架构/评审与真机脚本（可含本机路径）仅留本地；禁止 `git add -f` 强行加入。
2. **README 只写「使用方式 + 目标展望 + 参与号召」**：禁止架构分层、厂商 SDK 封装细节、设计决策等。
3. **提交须可公开审查**：无本机绝对路径、真实客户/项目/ECU 名、内部 IP、账号、密钥、令牌。
4. **厂商 SDK 二进制不进仓库**：用户自备；许可证原文放 `third_party/NOTICES`。
5. **未要求勿提交**；`git add` 前自查 diff / status。

## 二次开发约定

- 核心运行时依赖仅 `python-can`；MCP 走 `[mcp]` optional extra。
- 厂商差异只在 `src/xusbcan/adapters/`；core / cli / mcp 不出现厂商概念。
- 输出：`Result`（`error.code` 枚举）+ `CanFrame`（`data` 小写十六进制，`channel` 不进 JSON）。
- 无硬件测试：`pytest`（`virtual` + 假适配器）须全绿。

## 常用命令（公开）

```bash
python -m pytest tests/ -q
python -m ruff check src tests
python -m mypy src/xusbcan
python -m xusbcan.cli list
python tests/test_mcp_stdio.py
```
