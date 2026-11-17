import qrcode
from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H
from PIL import Image
import numpy as np

# 纠错等级映射
_CORRECTION_MAP = {
    "L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M,
    "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H,
}

def generate(public: str, config: dict) -> dict:
    """
    根据统一接口规范实现。
    返回：image, region, protected_mask, qr_version, correction
    """
    # ---------------- 1. 异常边界处理 ----------------
    if not public or not str(public).strip():
        raise ValueError("公开文本 public 不能为空")
    if len(public.encode("utf-8")) > 1200:
        raise ValueError("public 超过 1200 UTF-8 字节限制")

    correction = config.get("correction", "H").upper()
    if correction not in _CORRECTION_MAP:
        raise ValueError(f"不支持的纠错等级: {correction}。仅支持 L/M/Q/H")

    box_size = int(config.get("box_size", 10))
    border = int(config.get("border", 4))
    cat_width = int(config.get("cat_width", 200))
    cat_height = int(config.get("cat_height", 256))
    cat_image = config.get("cat_image") # 接收 PIL.Image 对象

    # ---------------- 2. 生成标准二维码 ----------------
    qr = qrcode.QRCode(
        version=config.get("qr_version"), # 默认 None，自动分配
        error_correction=_CORRECTION_MAP[correction],
        box_size=box_size,
        border=border,
    )
    qr.add_data(public)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_w, qr_h = qr_img.size

    # ---------------- 3. 建立画布与计算 region ----------------
    # 最终输出图宽度 = 二维码宽度 + 右侧猫图条带宽度
    out_w = qr_w + cat_width
    out_h = max(qr_h, cat_height)
    
    # 创建白色底图
    canvas = Image.new("RGB", (out_w, out_h), "white")
    canvas.paste(qr_img, (0, 0)) # 二维码放左边

    # 严格遵循文档 CAT1 协议：右侧条带区域固定坐标
    rx, ry, rw, rh = out_w - 180, 32, 160, 200
    region = (rx, ry, rw, rh)

    # ---------------- 4. 生成 protected_mask (保护罩) ----------------
    # 尺寸与最终图像一致，True 代表禁止改动/禁止覆盖
    mask = np.zeros((out_h, out_w), dtype=bool)
    
    # 策略 A：二维码区域全保护（防止猫图遮挡导致扫不出，最稳妥的做法）
    mask[0:qr_h, 0:qr_w] = True
    
    # 策略 B：CAT1 隐藏区域绝对保护（因为 B 要在这个区域的最低比特位藏数据）
    mask[ry:ry+rh, rx:rx+rw] = True

    # ---------------- 5. 猫咪艺术融合（只在安全区融合） ----------------
    if cat_image is not None:
        # 把用户传的猫图缩放到右侧条带的大小
        cat = cat_image.convert("RGB").resize((cat_width, out_h))
        cat_np = np.array(cat)
        canvas_np = np.array(canvas)
        
        # 找到右侧条带的目标区域
        target = canvas_np[:, qr_w:out_w, :]
        # 获取右侧条带中允许被猫图覆盖的像素（即 mask 为 False 的地方）
        allowed = ~mask[:, qr_w:out_w] 
        
        # 融合：只在 allowed 为 True 的地方把原底图替换为猫图像素
        target[allowed] = cat_np[allowed]
        canvas_np[:, qr_w:out_w, :] = target
        canvas = Image.fromarray(canvas_np)

    # ---------------- 6. 返回字典 ----------------
    return {
        "image": canvas,             # Pillow RGB Image
        "region": region,            # tuple (x, y, w, h)
        "protected_mask": mask,      # numpy bool array
        "qr_version": qr.version,    # int
        "correction": correction     # str
    }