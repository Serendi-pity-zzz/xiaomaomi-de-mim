# C 的检测实验交付

2026-11-17 复测。只涉及 C 的隐写统计检测，不代表系统集成或 E 的自然图像数据集验收。

## 文件

- `eval_results.csv`：544 条分析记录（26 条正常样本、456 条含密样本、52 条区域/整图对照、10 条随机 LSB 边界对照）。
- `rs_results.csv`：30 条 RS 辅助特征记录。
- `summary.json`：阈值标识、实际运行环境、分条件指标与 PNG 重存检查。
- `summary.md`：可阅读的实测表，含混淆矩阵、准确率、误报率、漏报率和判定覆盖率。

## 复现

在项目根目录运行（沿用项目 Pillow、qrcode 依赖）：

```powershell
python -m unittest discover -s tests -p test_steganalysis.py -v
python tests/eval_steganalysis.py --output-dir docs/C_results
python tests/calibrate_steganalysis.py --output outputs/steganalysis/recalibration.json
```

最后一条写入独立校准文件，便于核对，保留正式校准 ID。此次重新校准仍得到阈值 0.5，
覆盖最大分数 0.000046、选定含密子集最小分数 0.593774，与原文件相同。

## 结果的适用范围

内置猫载体顺序 ASCII 满容量检出 36/36，正常样本误报 0/12；≤10240 字节的 60 条
顺序 ASCII 样本全部漏报，顺序中文满容量 0/36 检出。4 次 PNG 重存前后分数一致。
这些数字描述本项目的固定载体和给定载荷条件，不是通用检测准确率。

正常样本合计 26 条，0 个误报、1 个无法判定。混淆矩阵中的未知单列，不计作 TN/FN；
`accuracy_decided`、`fpr_decided`、`fnr_decided` 的分母只包含已判定样本，必须同时看
`decision_coverage`。TPR 表使用全部含密样本为分母，含未知；1−TPR 表示未检出率。
各条件重复使用同类正常样本，不能将各矩阵相加当作独立实验。

载体都是程序生成。12 个内置猫图的检测区域相同，合成图也有重复结构；校准/评估虽使用
不同文本、种子，仍不是独立自然照片划分。Wilson 区间仅描述重复实验计数，未做聚类修正。
真实猫图由 E 提供后，C 才能重新校准并报告该数据集上的表现。

## C 的验收状态

37 项 C 测试：36 通过，1 项可选 SciPy 交叉验证因未安装而跳过。固定数值与单调性测试已通过。
全仓库回归共 39 项：38 通过、同一项跳过。没有改动其他成员的算法、公共服务或前端。
组长按 `docs/C_隐写统计检测_算法与结果.md` 第 8 节接入 `analyze`；当前 HTTP 检测状态仍为 unavailable。
