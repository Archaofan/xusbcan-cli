"""xusbcan —— 面向 AI Agent 的 CAN 总线调试工具。

顶层包不得 import 任何厂商相关模块（如 adapters.zlg），以保证在 Linux
（无 zlgcan.dll）上也能 `import xusbcan`，`virtual` 后端测试才能运行。
"""

__version__ = "0.1.0"
