"""适配层：每个厂商一个目录。python-can 已有后端只放 profiles.py；没有的才放 backend。

上层只通过 registry 打开设备，不在 core / cli / mcp 里写厂商名。
"""
