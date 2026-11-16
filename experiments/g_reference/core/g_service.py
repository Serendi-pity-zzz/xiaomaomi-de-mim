# === 文件说明 ===
# 来源：原项目服务入口的历史副本；本文件仅增加中文文件说明，原始正文保留。
# 用途：记录实验使用版本的服务接口关系，仅用于来源审阅，不是 G 的运行入口。
# 关联文件：原文件为 core/service.py，同批基线副本为 g_baseline.py；来源记录见 ../g_manifest.json。
# === 原代码 ===
"""唯一集成入口。A/B/D/G 的替换在此完成，不改前端协议。"""
from .baseline import generate, embed, extract

def detect(image):
    return {'status':'unavailable','detail':'等待 C 接入统计检测，提取成功不能用作隐写检测结论'}
