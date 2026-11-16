"""唯一集成入口。A/B/D/G 的替换在此完成，不改前端协议。"""
from .baseline import generate, embed, extract

def detect(image):
    return {'status':'unavailable','detail':'等待 C 接入统计检测，提取成功不能用作隐写检测结论'}
