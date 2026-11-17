"""周立功兼容层：型号登记在 profiles.py，DLL 后端在 backend.py。

导入本包不会加载 DLL。python-can 入口是 ``xusbcan.adapters.zlg.backend:ZlgBus``。
"""
