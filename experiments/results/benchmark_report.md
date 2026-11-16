# E：实验设计、数据集与性能评估报告

> 由 `experiments/benchmark.py` 自动生成，所有数字均为本次实测，未使用示意值。

## 1. 环境与参数

| 项 | 值 |
|---|---|
| python | 3.13.14 |
| platform | Windows-11-10.0.26200-SP0 |
| Pillow | 11.3.0 |
| numpy | 2.1.3 |
| matplotlib | 3.10.6 |
| impl | core.service |
| carrier_source | cats |
| dataset | FELIX Experimental Study Set (CC licensed) |
| samples | 12 |
| repeats | 3 |
| payloads | [16, 128, 512, 2048, 8192] |
| algorithms | ["sequential", "keyed"] |
| seed | 20261109 |
| target_size | [800, 600] |
| ssim_config | {"version": "wang2004-global-v1", "structure": "Wang et al. 2004 global SSIM", "channel": "RGB -> gray (ITU-R 601-2: 0.299R+0.587G+0.114B)", "window": "11x11 gaussian", "sigma": 1.5, "border": "reflect", "data_range": 255.0, "C1": 6.502500000000001, "C2": 58.522499999999994, "aggregate": "arithmetic mean of SSIM map", "implementation": "numpy (no scikit-image)"} |
| timing_scope | algorithm call only (no HTTP / IO) |
| 生成时间 | 2026-11-16 18:26:56 |
| 用例数 | 360 |
| 记录数 | 360 |

## 2. 数据与配对方式

载体为 30 张 FELIX 猫图（`experiments/dataset/cats/`），统一缩放到 800×600 RGB，
逐图来源与许可见 `experiments/dataset/manifest.csv`（CC BY 2.0 / CC BY-SA 4.0 等，可署名复现）。
每条记录用**原始无封包图 cover** 与**含密图 stego** 逐一配对计算 PSNR/SSIM；
计时只包住 `embed` / `extract` 算法调用本身，不含 HTTP、前端或文件读写，
因此这里的毫秒数是**纯算法耗时**，不能与端到端网页延迟直接比较。

SSIM 口径：RGB -> gray (ITU-R 601-2: 0.299R+0.587G+0.114B)。
窗口 11x11 gaussian，sigma=1.5，data_range=255.0，arithmetic mean of SSIM map 聚合；实现见 `experiments/metrics.py`。

## 3. 结果（按 算法 × 载荷 汇总）

| 算法 | 载荷(B) | n | PSNR均值(dB) | PSNR标准差 | SSIM均值 | SSIM标准差 | 嵌入均值(ms) | 提取均值(ms) | 恢复成功 | 错误数 |
|---|---|---|---|---|---|---|---|---|---|---|
| lsb-sequential | 16 | 36 | 86.299 | 0.121 | 0.999999 | 1e-06 | 9.794 | 9.945 | 36/36 | 0 |
| lsb-keyed | 16 | 36 | 86.206 | 0.212 | 0.999999 |  | 38.679 | 42.069 | 36/36 | 0 |
| lsb-sequential | 128 | 36 | 81.434 | 0.134 | 0.999998 | 1e-06 | 10.913 | 9.87 | 36/36 | 0 |
| lsb-keyed | 128 | 36 | 81.403 | 0.115 | 0.999998 | 1e-06 | 40.414 | 42.869 | 36/36 | 0 |
| lsb-sequential | 512 | 36 | 76.258 | 0.072 | 0.999993 | 3e-06 | 14.828 | 11.918 | 36/36 | 0 |
| lsb-keyed | 512 | 36 | 76.287 | 0.08 | 0.999993 | 3e-06 | 45.725 | 45.016 | 36/36 | 0 |
| lsb-sequential | 2048 | 36 | 70.504 | 0.037 | 0.999973 | 1.2e-05 | 30.628 | 19.139 | 36/36 | 0 |
| lsb-keyed | 2048 | 36 | 70.489 | 0.029 | 0.999974 | 1.1e-05 | 61.831 | 52.66 | 36/36 | 0 |
| lsb-sequential | 8192 | 36 | 64.548 | 0.016 | 0.999899 | 4.5e-05 | 90.52 | 47.605 | 36/36 | 0 |
| lsb-keyed | 8192 | 36 | 64.539 | 0.021 | 0.9999 | 4.4e-05 | 130.711 | 90.223 | 36/36 | 0 |

> `secret_ok/secret_n` 按 UTF-8 字节与原文完全一致判定；
> 未测项留空而非 0；PSNR 无差异记为 `inf`（不计入均值）。

## 4. 图表

- `results/figures/psnr_vs_payload.png`
- `results/figures/ssim_vs_payload.png`
- `results/figures/time_vs_payload.png`

## 5. 结论

- 秘密恢复：360/360 条记录逐字节一致（按 UTF-8 原文判定）。
- lsb-sequential：载荷 16→8192 字节时，PSNR 86.30→64.55 dB，SSIM 0.999999→0.999899；嵌入耗时 9.794→90.520 ms（纯算法）。
- lsb-keyed：载荷 16→8192 字节时，PSNR 86.21→64.54 dB，SSIM 0.999999→0.9999；嵌入耗时 38.679→130.711 ms（纯算法）。
- 顺序 LSB 与密钥置乱 LSB 在相同载荷下的 PSNR 平均差异 0.035 dB——置乱只改变写入顺序，不改变改动像素的数量，图像质量应基本相当。

## 6. 局限

- 载体为统一缩放后的猫图或集成基线，不是 A 的最终艺术融合图；A 接入后需用 `--carrier-source service` 或传入 A 的载体重跑。
- PSNR/SSIM 只衡量像素级失真，不等于人眼主观质量，也不代表隐写是否被检测出来（检测归 C）。
- 本实验不施加 JPEG/噪声/裁剪等干扰，抗干扰结论归 F；扫码成功与否归 A/F，这里留空。
- 载荷用 ASCII 精确控制字节数，便于对比；中文/emoji 的编码边界测试归 B。
- 计时受机器负载影响，取多次重复均值并附标准差；不同硬件不可直接比较绝对值。
- 密钥置乱（keyed）为 Python `random.Random` 确定性实现，跨语言不可假设一致（见 CAT1 协议）。
