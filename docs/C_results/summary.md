# C 模块实测汇总（自动生成）

- 校准文件：`core/steganalysis_calibration.json`
- calibration_id：`sha256:c5f8c169f403ebb7f996d5c326348060e4c2ed6bc01b2fe36ab98ecba13a65e7`
- 阈值：0.5；依据：结构化覆盖样本最大分数加 0.05 裕量为下界，可检测含密样本最小分数为上界；区间 [0.05, 0.59] 内取可解释的 0.5，兼顾裕量与检出率。
- 评估环境：{'python': '3.12.14', 'pillow': '13.0.0', 'platform': 'Windows-11-10.0.26200-SP0'}
- 指标口径：混淆矩阵按载体和载荷条件分组，复用同类覆盖样本；未知单列。accuracy/fpr/fnr_decided 仅用已判定样本，结合 decision_coverage 阅读。TPR 为检出数/全部含密样本，含未知；1-TPR 是未检出率。内置猫区域重复，不能视为独立照片。

## 覆盖样本（误报）

| 载体 | 样本数 | 判为可疑 | 无法判定 | FPR |
|---|---:|---:|---:|---|
| builtin_cat_qr | 12 | 0 | 0 | 0.0% (95% CI 0.0%–24.3%) |
| synthetic_checker | 2 | 0 | 1 | 0.0% (95% CI 0.0%–65.8%) |
| synthetic_flat | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| synthetic_gradient | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| synthetic_noise | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| synthetic_plasma | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| synthetic_radial | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| synthetic_stripes | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |

## 含密样本（检出率）

| 条件 | 载体 | 算法 | 载荷字节 | 消息 | 样本数 | 检出 | 无法判定 | TPR |
|---|---|---|---:|---|---:|---:|---:|---|
| keyed_ascii_full | builtin_cat_qr | lsb-keyed | 11960 | ascii | 36 | 36 | 0 | 100.0% (95% CI 90.4%–100.0%) |
| keyed_ascii_full | synthetic_checker | lsb-keyed | 11960 | ascii | 8 | 6 | 0 | 75.0% (95% CI 40.9%–92.9%) |
| keyed_ascii_full | synthetic_flat | lsb-keyed | 11960 | ascii | 8 | 8 | 0 | 100.0% (95% CI 67.6%–100.0%) |
| keyed_ascii_full | synthetic_gradient | lsb-keyed | 11960 | ascii | 8 | 8 | 0 | 100.0% (95% CI 67.6%–100.0%) |
| keyed_ascii_full | synthetic_noise | lsb-keyed | 11960 | ascii | 8 | 8 | 0 | 100.0% (95% CI 67.6%–100.0%) |
| keyed_ascii_full | synthetic_plasma | lsb-keyed | 11960 | ascii | 8 | 8 | 0 | 100.0% (95% CI 67.6%–100.0%) |
| keyed_ascii_full | synthetic_radial | lsb-keyed | 11960 | ascii | 8 | 8 | 0 | 100.0% (95% CI 67.6%–100.0%) |
| keyed_ascii_full | synthetic_stripes | lsb-keyed | 11960 | ascii | 8 | 8 | 0 | 100.0% (95% CI 67.6%–100.0%) |
| keyed_zh_full | builtin_cat_qr | lsb-keyed | 11960 | zh | 36 | 36 | 0 | 100.0% (95% CI 90.4%–100.0%) |
| keyed_zh_full | synthetic_checker | lsb-keyed | 11960 | zh | 6 | 6 | 0 | 100.0% (95% CI 61.0%–100.0%) |
| keyed_zh_full | synthetic_flat | lsb-keyed | 11960 | zh | 6 | 6 | 0 | 100.0% (95% CI 61.0%–100.0%) |
| keyed_zh_full | synthetic_gradient | lsb-keyed | 11960 | zh | 6 | 6 | 0 | 100.0% (95% CI 61.0%–100.0%) |
| keyed_zh_full | synthetic_noise | lsb-keyed | 11960 | zh | 6 | 6 | 0 | 100.0% (95% CI 61.0%–100.0%) |
| keyed_zh_full | synthetic_plasma | lsb-keyed | 11960 | zh | 6 | 6 | 0 | 100.0% (95% CI 61.0%–100.0%) |
| keyed_zh_full | synthetic_radial | lsb-keyed | 11960 | zh | 6 | 6 | 0 | 100.0% (95% CI 61.0%–100.0%) |
| keyed_zh_full | synthetic_stripes | lsb-keyed | 11960 | zh | 6 | 6 | 0 | 100.0% (95% CI 61.0%–100.0%) |
| seq_ascii | builtin_cat_qr | lsb-sequential | 64 | ascii | 12 | 0 | 0 | 0.0% (95% CI 0.0%–24.3%) |
| seq_ascii | builtin_cat_qr | lsb-sequential | 1024 | ascii | 12 | 0 | 0 | 0.0% (95% CI 0.0%–24.3%) |
| seq_ascii | builtin_cat_qr | lsb-sequential | 4096 | ascii | 12 | 0 | 0 | 0.0% (95% CI 0.0%–24.3%) |
| seq_ascii | builtin_cat_qr | lsb-sequential | 8192 | ascii | 12 | 0 | 0 | 0.0% (95% CI 0.0%–24.3%) |
| seq_ascii | builtin_cat_qr | lsb-sequential | 10240 | ascii | 12 | 0 | 0 | 0.0% (95% CI 0.0%–24.3%) |
| seq_ascii | synthetic_checker | lsb-sequential | 64 | ascii | 2 | 1 | 0 | 50.0% (95% CI 9.5%–90.5%) |
| seq_ascii | synthetic_checker | lsb-sequential | 1024 | ascii | 2 | 1 | 0 | 50.0% (95% CI 9.5%–90.5%) |
| seq_ascii | synthetic_checker | lsb-sequential | 4096 | ascii | 2 | 1 | 0 | 50.0% (95% CI 9.5%–90.5%) |
| seq_ascii | synthetic_checker | lsb-sequential | 8192 | ascii | 2 | 1 | 0 | 50.0% (95% CI 9.5%–90.5%) |
| seq_ascii | synthetic_checker | lsb-sequential | 10240 | ascii | 2 | 1 | 0 | 50.0% (95% CI 9.5%–90.5%) |
| seq_ascii | synthetic_flat | lsb-sequential | 64 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_flat | lsb-sequential | 1024 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_flat | lsb-sequential | 4096 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_flat | lsb-sequential | 8192 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_flat | lsb-sequential | 10240 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_gradient | lsb-sequential | 64 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_gradient | lsb-sequential | 1024 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_gradient | lsb-sequential | 4096 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_gradient | lsb-sequential | 8192 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_gradient | lsb-sequential | 10240 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_noise | lsb-sequential | 64 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_noise | lsb-sequential | 1024 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_noise | lsb-sequential | 4096 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_noise | lsb-sequential | 8192 | ascii | 2 | 2 | 0 | 100.0% (95% CI 34.2%–100.0%) |
| seq_ascii | synthetic_noise | lsb-sequential | 10240 | ascii | 2 | 2 | 0 | 100.0% (95% CI 34.2%–100.0%) |
| seq_ascii | synthetic_plasma | lsb-sequential | 64 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_plasma | lsb-sequential | 1024 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_plasma | lsb-sequential | 4096 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_plasma | lsb-sequential | 8192 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_plasma | lsb-sequential | 10240 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_radial | lsb-sequential | 64 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_radial | lsb-sequential | 1024 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_radial | lsb-sequential | 4096 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_radial | lsb-sequential | 8192 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_radial | lsb-sequential | 10240 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_stripes | lsb-sequential | 64 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_stripes | lsb-sequential | 1024 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_stripes | lsb-sequential | 4096 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_stripes | lsb-sequential | 8192 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii | synthetic_stripes | lsb-sequential | 10240 | ascii | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| seq_ascii_full | builtin_cat_qr | lsb-sequential | 11960 | ascii | 36 | 36 | 0 | 100.0% (95% CI 90.4%–100.0%) |
| seq_ascii_full | synthetic_checker | lsb-sequential | 11960 | ascii | 6 | 6 | 0 | 100.0% (95% CI 61.0%–100.0%) |
| seq_ascii_full | synthetic_flat | lsb-sequential | 11960 | ascii | 6 | 6 | 0 | 100.0% (95% CI 61.0%–100.0%) |
| seq_ascii_full | synthetic_gradient | lsb-sequential | 11960 | ascii | 6 | 0 | 0 | 0.0% (95% CI 0.0%–39.0%) |
| seq_ascii_full | synthetic_noise | lsb-sequential | 11960 | ascii | 6 | 6 | 0 | 100.0% (95% CI 61.0%–100.0%) |
| seq_ascii_full | synthetic_plasma | lsb-sequential | 11960 | ascii | 6 | 0 | 0 | 0.0% (95% CI 0.0%–39.0%) |
| seq_ascii_full | synthetic_radial | lsb-sequential | 11960 | ascii | 6 | 6 | 0 | 100.0% (95% CI 61.0%–100.0%) |
| seq_ascii_full | synthetic_stripes | lsb-sequential | 11960 | ascii | 6 | 0 | 0 | 0.0% (95% CI 0.0%–39.0%) |
| seq_zh_full | builtin_cat_qr | lsb-sequential | 11960 | zh | 36 | 0 | 0 | 0.0% (95% CI 0.0%–9.6%) |
| seq_zh_full | synthetic_checker | lsb-sequential | 11960 | zh | 6 | 0 | 0 | 0.0% (95% CI 0.0%–39.0%) |
| seq_zh_full | synthetic_flat | lsb-sequential | 11960 | zh | 6 | 0 | 0 | 0.0% (95% CI 0.0%–39.0%) |
| seq_zh_full | synthetic_gradient | lsb-sequential | 11960 | zh | 6 | 0 | 0 | 0.0% (95% CI 0.0%–39.0%) |
| seq_zh_full | synthetic_noise | lsb-sequential | 11960 | zh | 6 | 6 | 0 | 100.0% (95% CI 61.0%–100.0%) |
| seq_zh_full | synthetic_plasma | lsb-sequential | 11960 | zh | 6 | 0 | 0 | 0.0% (95% CI 0.0%–39.0%) |
| seq_zh_full | synthetic_radial | lsb-sequential | 11960 | zh | 6 | 6 | 0 | 100.0% (95% CI 61.0%–100.0%) |
| seq_zh_full | synthetic_stripes | lsb-sequential | 11960 | zh | 6 | 0 | 0 | 0.0% (95% CI 0.0%–39.0%) |

## 分条件混淆矩阵与准确率

| 条件 | 载体 | 字节 | TP | FN | FP | TN | 未知（正常/含密） | 准确率¹ | 误报率¹ | 漏报率¹ | 判定覆盖率 |
|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|
| keyed_ascii_full | builtin_cat_qr | 11960 | 36 | 0 | 0 | 12 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| keyed_ascii_full | synthetic_checker | 11960 | 6 | 2 | 0 | 1 | 1/0 | 77.8% | 0.0% | 25.0% | 90.0% |
| keyed_ascii_full | synthetic_flat | 11960 | 8 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| keyed_ascii_full | synthetic_gradient | 11960 | 8 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| keyed_ascii_full | synthetic_noise | 11960 | 8 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| keyed_ascii_full | synthetic_plasma | 11960 | 8 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| keyed_ascii_full | synthetic_radial | 11960 | 8 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| keyed_ascii_full | synthetic_stripes | 11960 | 8 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| keyed_zh_full | builtin_cat_qr | 11960 | 36 | 0 | 0 | 12 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| keyed_zh_full | synthetic_checker | 11960 | 6 | 0 | 0 | 1 | 1/0 | 100.0% | 0.0% | 0.0% | 87.5% |
| keyed_zh_full | synthetic_flat | 11960 | 6 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| keyed_zh_full | synthetic_gradient | 11960 | 6 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| keyed_zh_full | synthetic_noise | 11960 | 6 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| keyed_zh_full | synthetic_plasma | 11960 | 6 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| keyed_zh_full | synthetic_radial | 11960 | 6 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| keyed_zh_full | synthetic_stripes | 11960 | 6 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| seq_ascii | builtin_cat_qr | 64 | 0 | 12 | 0 | 12 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | builtin_cat_qr | 1024 | 0 | 12 | 0 | 12 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | builtin_cat_qr | 4096 | 0 | 12 | 0 | 12 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | builtin_cat_qr | 8192 | 0 | 12 | 0 | 12 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | builtin_cat_qr | 10240 | 0 | 12 | 0 | 12 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_checker | 64 | 1 | 1 | 0 | 1 | 1/0 | 66.7% | 0.0% | 50.0% | 75.0% |
| seq_ascii | synthetic_checker | 1024 | 1 | 1 | 0 | 1 | 1/0 | 66.7% | 0.0% | 50.0% | 75.0% |
| seq_ascii | synthetic_checker | 4096 | 1 | 1 | 0 | 1 | 1/0 | 66.7% | 0.0% | 50.0% | 75.0% |
| seq_ascii | synthetic_checker | 8192 | 1 | 1 | 0 | 1 | 1/0 | 66.7% | 0.0% | 50.0% | 75.0% |
| seq_ascii | synthetic_checker | 10240 | 1 | 1 | 0 | 1 | 1/0 | 66.7% | 0.0% | 50.0% | 75.0% |
| seq_ascii | synthetic_flat | 64 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_flat | 1024 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_flat | 4096 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_flat | 8192 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_flat | 10240 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_gradient | 64 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_gradient | 1024 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_gradient | 4096 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_gradient | 8192 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_gradient | 10240 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_noise | 64 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_noise | 1024 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_noise | 4096 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_noise | 8192 | 2 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| seq_ascii | synthetic_noise | 10240 | 2 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| seq_ascii | synthetic_plasma | 64 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_plasma | 1024 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_plasma | 4096 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_plasma | 8192 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_plasma | 10240 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_radial | 64 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_radial | 1024 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_radial | 4096 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_radial | 8192 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_radial | 10240 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_stripes | 64 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_stripes | 1024 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_stripes | 4096 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_stripes | 8192 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii | synthetic_stripes | 10240 | 0 | 2 | 0 | 2 | 0/0 | 50.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii_full | builtin_cat_qr | 11960 | 36 | 0 | 0 | 12 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| seq_ascii_full | synthetic_checker | 11960 | 6 | 0 | 0 | 1 | 1/0 | 100.0% | 0.0% | 0.0% | 87.5% |
| seq_ascii_full | synthetic_flat | 11960 | 6 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| seq_ascii_full | synthetic_gradient | 11960 | 0 | 6 | 0 | 2 | 0/0 | 25.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii_full | synthetic_noise | 11960 | 6 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| seq_ascii_full | synthetic_plasma | 11960 | 0 | 6 | 0 | 2 | 0/0 | 25.0% | 0.0% | 100.0% | 100.0% |
| seq_ascii_full | synthetic_radial | 11960 | 6 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| seq_ascii_full | synthetic_stripes | 11960 | 0 | 6 | 0 | 2 | 0/0 | 25.0% | 0.0% | 100.0% | 100.0% |
| seq_zh_full | builtin_cat_qr | 11960 | 0 | 36 | 0 | 12 | 0/0 | 25.0% | 0.0% | 100.0% | 100.0% |
| seq_zh_full | synthetic_checker | 11960 | 0 | 6 | 0 | 1 | 1/0 | 14.3% | 0.0% | 100.0% | 87.5% |
| seq_zh_full | synthetic_flat | 11960 | 0 | 6 | 0 | 2 | 0/0 | 25.0% | 0.0% | 100.0% | 100.0% |
| seq_zh_full | synthetic_gradient | 11960 | 0 | 6 | 0 | 2 | 0/0 | 25.0% | 0.0% | 100.0% | 100.0% |
| seq_zh_full | synthetic_noise | 11960 | 6 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| seq_zh_full | synthetic_plasma | 11960 | 0 | 6 | 0 | 2 | 0/0 | 25.0% | 0.0% | 100.0% | 100.0% |
| seq_zh_full | synthetic_radial | 11960 | 6 | 0 | 0 | 2 | 0/0 | 100.0% | 0.0% | 0.0% | 100.0% |
| seq_zh_full | synthetic_stripes | 11960 | 0 | 6 | 0 | 2 | 0/0 | 25.0% | 0.0% | 100.0% | 100.0% |

¹ 仅在已判定样本上计算；未知不算正确或负类。各行复用同类正常样本，不可跨行相加；低判定覆盖率下的高准确率不能代表整体能力。

## 区域 vs 整图（全容量顺序 ASCII）

| 载体 | 分析范围 | 样本数 | 检出 | 无法判定 | TPR |
|---|---|---:|---:|---:|---|
| builtin_cat_qr | region | 12 | 12 | 0 | 100.0% (95% CI 75.7%–100.0%) |
| builtin_cat_qr | whole_image | 12 | 0 | 0 | 0.0% (95% CI 0.0%–24.3%) |
| synthetic_checker | region | 2 | 2 | 0 | 100.0% (95% CI 34.2%–100.0%) |
| synthetic_checker | whole_image | 2 | 1 | 0 | 50.0% (95% CI 9.5%–90.5%) |
| synthetic_flat | region | 2 | 2 | 0 | 100.0% (95% CI 34.2%–100.0%) |
| synthetic_flat | whole_image | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| synthetic_gradient | region | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| synthetic_gradient | whole_image | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| synthetic_noise | region | 2 | 2 | 0 | 100.0% (95% CI 34.2%–100.0%) |
| synthetic_noise | whole_image | 2 | 1 | 0 | 50.0% (95% CI 9.5%–90.5%) |
| synthetic_plasma | region | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| synthetic_plasma | whole_image | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| synthetic_radial | region | 2 | 2 | 0 | 100.0% (95% CI 34.2%–100.0%) |
| synthetic_radial | whole_image | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| synthetic_stripes | region | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |
| synthetic_stripes | whole_image | 2 | 0 | 0 | 0.0% (95% CI 0.0%–65.8%) |

## 不可区分对照

- 样本数 10，判为可疑 10。
- LSB 已随机的对照；统计上与全量 LSB 替换不可区分，不计入覆盖样本误报率。

## RS 辅助特征（d_m 随载荷下降）

| 载荷字节 | 样本数 | d_m 均值 | 最小 | 最大 |
|---:|---:|---:|---:|---:|
| 0 | 6 | 0.975 | 0.976 | 0.976 |
| 4096 | 6 | 0.639 | 0.639 | 0.639 |
| 8192 | 6 | 0.296 | 0.296 | 0.296 |
| 10240 | 6 | 0.127 | 0.127 | 0.127 |
| 11960 | 6 | -0.016 | -0.016 | -0.016 |

