# E 模块说明：实验设计、数据集与性能评估

对应分工：**E——实验设计、数据集与性能评估**。
交付：`experiments/metrics.py`、`experiments/benchmark.py`、合法数据集、实测 CSV/图表/报告、本说明、PPT 内容。

## 1. 做了什么

用一组**可合法使用、可署名复现**的猫图作原始载体，对 CAT1 隐写做质量 / 容量 / 纯算法耗时的对比实验：

1. 对每张原始图 `cover` 嵌入不同长度的 UTF-8 秘密，得到含密图 `stego`；
2. 在**这一对**图上算 PSNR 与 SSIM，衡量 LSB 嵌入造成的像素失真；
3. 记录 `embed` / `extract` 的**纯算法耗时**（只包住算法调用，不含 HTTP / 前端 / 文件 IO）；
4. 提取后按 UTF-8 字节与原文**完全一致**判定恢复成功；
5. 多样本 × 多载荷 × 两算法 × 多次重复，逐条写入原始 CSV，再汇总出统计图与报告。

对比基础 LSB（顺序）与密钥置乱 LSB，回应分工里「不同隐藏容量、图片尺寸、嵌入算法的对比」以及和 B/G 的对照。

## 2. 指标口径

| 指标 | 定义 | 说明 |
|---|---|---|
| PSNR | 10·log10(255²/MSE)，RGB 三通道 | 无差异记 `inf`，不作为均值；尺寸不一致留空 |
| SSIM | Wang et al. 2004 全局 SSIM | RGB→灰度(ITU-R 601-2)，11×11 高斯窗 σ=1.5，reflect 边界，data_range=255 |
| embed_ms / extract_ms | `perf_counter` 包住算法调用 | **纯算法耗时**，不是网页端到端延迟 |
| payload_bytes | 秘密的 UTF-8 字节数 | 容量上限 11960（CAT1 净载荷） |
| secret_success | 提取 status=passed 且字节完全一致 | 错误密钥/损坏不记为成功 |

SSIM 的完整口径由 `metrics.ssim_config()` 给出，写进 env 快照与报告，避免「只报数不报口径」。实现只用 Pillow + numpy，不依赖 scikit-image。

## 3. 数据集与授权

- 来源：**FELIX**（DeepMicroscopy/FELIX，*Feline Evaluation with Layperson and ML Interaction Experience*），Experimental Study Set 共 30 张。
- 许可：逐图不同，**CC BY 2.0 / CC BY-SA 4.0 / CC BY-SA** 等，均为 Creative Commons 授权，可署名复现。
- 逐图 `source_url` / `artist` / `license` 见 `experiments/dataset/manifest.csv`；原始逐图数据见 `FELIX_Image_Level_Data.csv`（来自该仓库 `study_data/`）。
- 统一处理：全部缩放为 800×600 RGB（LANCZOS），不做裁剪或像素预处理，避免引入与隐写无关的变化。
- 本实验只把图片作为**统计意义上的自然载体**，不用于训练，不上传任何私人图片；CSV 的 `source` / `license` 列如实引用原始出处。

> 若你自有更合适的猫咪图，替换 `experiments/dataset/cats/` 并更新 `manifest.csv` 即可，`benchmark.py` 会自动读取。

## 4. 运行

本项目的 Python 依赖装在用户 site（`pip install --user`），因为本机应用控制策略会拦截 `.deps` 里 numpy 的 DLL。若在你的机器上可正常使用虚拟环境，任一种方式均可。

```bash
# 依赖
python -m pip install --user "Pillow==11.3.0" "qrcode==8.2" "numpy==2.1.3" "matplotlib==3.10.6"

# 自检（正常/边界/异常，不跑完整实验）
python -m experiments.metrics --self-test
python -m experiments.benchmark --self-test
python tests/test_benchmark_metrics.py

# 本次报告对应的完整实验（12 样本 × 5 载荷 × 2 算法 × 3 重复 = 360 条）
python -m experiments.benchmark --samples 12 --repeats 3 --out experiments/results

# 自定义
python -m experiments.benchmark --samples 30 --payloads 16,512,2048,8192 \
    --algorithms sequential,keyed --repeats 5 --seed 20261109

# 改用集成载体（A 的融合方案接入后，用它覆盖最终载体重跑）
python -m experiments.benchmark --carrier-source service
```

作为库调用（对齐 docs §5 的 E 接口）：

```python
from experiments.metrics import evaluate          # evaluate(original, stego) -> dict
from experiments.benchmark import run, make_case, load_covers

covers = load_covers(limit=3)
cases = [make_case(c["sample_id"], c["image"], 512, "keyed", c["source"], c["license"])
         for c in covers]
records = run(cases, {"seed": 20261109})
```

## 5. 输出

```
experiments/results/
  benchmark_raw.csv       每次运行一行，本次 360 行（§7 统一列 + repeat）
  benchmark_summary.csv   按 算法×载荷 汇总：均值/标准差/成功率/错误数
  benchmark_report.md     自动生成：环境、配对方式、结果表、结论、局限
  benchmark_env.json      环境、参数与 SSIM 口径快照
  figures/psnr_vs_payload.png / ssim_vs_payload.png / time_vs_payload.png
```

CSV 严格按 §7 列序。E 不做的部分如实留空：`scan_success`（归 A/F）、`detection_score`（归 C）、`attack`/`strength`（归 F）。密钥只以 `lsb-sequential` / `lsb-keyed` 体现，不写具体值。

## 6. 本次实测结论（12 样本 × 3 重复，seed=20261109）

| 载荷(B) | 顺序 LSB PSNR(dB) | 密钥 LSB PSNR(dB) | 顺序嵌入(ms) | 密钥嵌入(ms) | 恢复 |
|---|---|---|---|---|---|
| 16 | 86.30 | 86.21 | 9.79 | 38.68 | 36/36 |
| 128 | 81.43 | 81.40 | 10.91 | 40.41 | 36/36 |
| 512 | 76.26 | 76.29 | 14.83 | 45.73 | 36/36 |
| 2048 | 70.50 | 70.49 | 30.63 | 61.83 | 36/36 |
| 8192 | 64.55 | 64.54 | 90.52 | 130.71 | 36/36 |

1. **载荷越大、失真越大**：PSNR 从 16 B 的 ~86 dB 降到 8192 B 的 ~64.5 dB；LSB 只改最低位，即便满载人眼也难以察觉，但数值上随写入位数增加而单调下降。
2. **两种算法画质相当**：相同载荷下 PSNR 平均差仅 0.035 dB——置乱只改写入位置顺序，不改改动位数，这是符合预期的。
3. **密钥置乱更慢**：shuffle 整个 96000 位位置表带来固定开销，嵌入耗时约为顺序 LSB 的 3–4 倍（16 B 时 38.7 vs 9.8 ms），是时间复杂度上的明确代价。
4. **恢复稳定**：全部 360 条记录逐字节一致，说明 CAT1 封包与提取规则在当前载体上一致可靠。

## 7. 局限（写进 PPT）

- 载体是统一缩放的猫图 / 集成基线，不是 A 的最终艺术融合图；A 接入后要重跑。
- PSNR/SSIM 只衡量像素失真，不等于主观质量，也不代表能否被检测（检测归 C）。
- 不施加 JPEG/噪声/裁剪干扰（归 F），不测扫码（归 A/F），两类列都留空。
- 载荷用 ASCII 精确控制字节数；中文/emoji 编码边界归 B。
- 计时受机器负载影响，取多次均值并附标准差，不同硬件不可直接比绝对值。
- 密钥置乱是 Python `random.Random` 确定性实现，跨语言不可假设一致。

## 8. 与别人的接口关系

- 只读调用 `core.service` 的 `generate / embed / extract`，**不修改任何他人模块**；适配层兼容 baseline（返回 Image）与 B（返回 dict）两种形态，A/B/G 接入后自动跟随。
- 与 F 共用同一套 §7 CSV 列，F 的 `robustness.py` 把 SSIM 定义留给了本模块（`metrics.py`）。
- 与 C：检测分数列留空，不做隐写检测；与 B：容量边界与编码测试归 B。
- 若要暴露成 HTTP，建议组长在 `core/service.py` 加适配层，路由见 §6 的 `/api/experiments/compare`。
