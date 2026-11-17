# A 模块说明：二维码生成与猫咪融合

## 1. 接口说明
`generate(public: str, config: dict) -> dict`
- 输入 `public`：要嵌入的公开文本。
- 输入 `config`：配置字典，支持 `correction` (默认 'H'), `box_size` (默认 10), `cat_width` (默认 200), `cat_height` (默认 256), `cat_image` (PIL.Image格式)。
- 返回：`image`, `region`, `protected_mask`, `qr_version`, `correction`。

## 2. Mask 保护策略
`protected_mask` 尺寸与输出图像完全一致，`True` 代表**禁止改动/禁止被猫图覆盖**。
本模块已将二维码矩阵区以及 `(w-180, 32, 160, 200)` 的 CAT1 隐藏区标为 `True`，绝对保证 B 同学的 LSB 数据不受干扰。

## 3. 验证记录
- **自动扫码**：运行 `python -m tests.scan_test_A` 成功，CSV 见 `outputs/qr_test/scan_results.csv`。
- **真实扫码**：手机真机扫描 `outputs/qr_test/case_1_H_level.png` 成功，截图见 `docs/proof_A_phone_scan.png`。
- **失败样例**：故意输入空文本，系统正确抛出 ValueError 并记录在 `outputs/qr_test/failures/`。

## 4. 合规声明
本模块严格保留 CAT1 区域的坐标约定，不影响二维码定位图案，不改变隐写包格式，不修改前端和 `app.py`。