# CLAUDE.md（xusbcan-cli 项目规则）

面向二次开发与 AI Agent 的**公开**约定。真机验证、架构细节、本机脚本只在本地 `docs/` / `scripts/`（不进 git）。公开 CAN 用法在 `skills/xusbcan/`（安装：`npx skills add Archaofan/xusbcan-cli --skill xusbcan`）。

Cursor 始终生效规则：`.cursor/rules/privacy-git.mdc`（与本节一致）。

## 隐私与开源管理（硬约束）

1. **`docs/` 与 `scripts/` 不进 git**，也不得原文抄进 `skills/` 或 README。禁止 `git add -f`。
2. **README 写「使用方式 + 目标展望 + 参与号召」**（外加 Skill 安装）。允许公开层级摘要与贡献契约（去耦合 / Skill 按需加载）；禁止厂商 SDK 封装细节、板级结论、设计长文。深度架构只在本地 `docs/`。
3. **提交须可公开审查**：无本机绝对路径、真实客户/项目/ECU 名、内部 IP、账号、密钥、令牌、设备序列号。
4. **厂商 SDK 二进制不进仓库**：用户自备；许可证原文放 `third_party/NOTICES`。
5. **未要求勿提交**。每次 `git add` / `commit` 必须按下面清单全量检查。

### 每次 git 全量脱敏

1. `git status`：无 `docs/`、`scripts/`、DLL。
2. `git diff` 与 `git diff --cached`：扫描绝对路径、内网 IP、账号、令牌、客户/ECU 名、序列号。
3. 若包含 `skills/`：对照本地 `docs/`，不得出现 docs 独有路径或板级细节。
4. commit message 同样可公开。
5. 未要求不 push；push 前再看 `git log -1 -p`。

## 二次开发约定

- 核心运行时依赖仅 `python-can`；MCP 走 `[mcp]` optional extra。
- 配置里的 `interface` 使用 python-can 已声明的后端名即可打开，不必先登记型号。`vendor` / `model` 只用于通道映射和专有参数。
- 公开文档和 skill 把「真机确认」和「仅登记」分开写。厂商驱动、环境变量、踩坑只写在对应型号下。新增一家需用户自备 SDK 的厂商时，README 免责声明追加一条。
- 厂商差异只在 `src/xusbcan/adapters/<厂商>/`。`registry` 会自动收集该目录的 `profiles.py`。python-can 已有后端只加这个文件；没有的才在该目录加 backend，并注册 `can.interface` 入口。core / cli / mcp 不出现厂商概念，只调用 python-can 通用接口（如 `set_filters` / `send_periodic`）；适配器可在后端钩子内使用厂商专有 API 做硬件加速或特殊能力。
- Skill 按需加载：根 `SKILL.md` 只写通用契约；路由表在 `skills/xusbcan/references/catalog.md`；某一型号页须先经 catalog 匹配后再读，结构为 Quick start → How this backend behaves → Field notes（前人现场报告，未必可复现，不作正式「不支持」清单）。禁止把各型号症状写进 YAML `description`。新增型号用 `references/_template-model.md`，只加 catalog 一行 + 型号页，避免上下文与文档耦合膨胀。
- 贡献入口：README「参与」与 `third_party/ABI_PROVENANCE.md` 贡献摘要须与上述去耦合 / Skill / 合规约定一致；PR 不得把厂商逻辑渗入 core/cli/mcp。
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
