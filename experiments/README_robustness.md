# F 模块说明：二维码鲁棒性与抗干扰测试

对应分工：**F——二维码鲁棒性与抗干扰测试**
交付：`experiments/robustness.py`、攻击测试样例、实测结果（CSV + 报告）、本说明。

## 1. 做了什么

对同一张「扫码可见公开信息 + LSB 藏密文」的猫咪二维码，施加不同类型的干扰，然后**分别**回答三个问题：

1. 手机/解码器还能扫出二维码里的公开信息吗？（文本必须与原文完全一致才算成功）
2. 专用程序还能恢复出秘密信息吗？（UTF-8 字节必须完全一致才算成功）
3. 完整性校验（CAT1 的 HMAC）还通过吗？

三项分开统计，不合并、不互相替代，也不把 `unknown` 当作通过。

## 2. 干扰类型与参数

前六类与前端 `web/src/utils/experiments.ts` 同构，便于和界面演示对照；强度 0—100，0 为未处理对照。

| 干扰 | 参数 | 说明 |
|---|---|---|
| `jpeg` | 质量 = 1 − 0.95·s | s=0.2 → 81，s=1 → 5 |
| `gaussian` | σ = 40s | 每通道高斯噪声 |
| `salt` | p = 30%·s | 椒盐噪声，置纯黑/纯白 |
| `occlude` | 白块边长 = 50%·s × 图宽 | 居中遮挡（前端用例） |
| `crop` | 四边各裁 20%·s | 不补边，尺寸变小 |
| `rotate` | ±45°·s | 画布不变，空处填白 |
| `occlude_region` | 白块宽 = 160·s | **F 追加**：直接盖在 CAT1 条带左侧，用于对照「遮挡位置」的影响 |

`occlude_region` 是补的第七类：只做中心遮挡时，白块根本压不到 `x=[w-180,w-20)、y=[32,232)` 这条载荷带，会得出「遮挡不影响提取」的错误结论。

## 3. 运行

```bash
# 只需 Pillow + numpy；要真实扫码解码再加 opencv-python-headless
python -m pip install --target .deps -r requirements.txt
python -m pip install --target .deps opencv-python-headless

python experiments/robustness.py                     # 默认 2 个样本 × 6 类干扰 × 6 档强度
python experiments/robustness.py --samples 3         # 本次报告用的参数
python experiments/robustness.py --strengths 0,20,40,60,80,100 --attacks jpeg,salt,occlude_region
python experiments/robustness.py --carrier path/to/stego.png --public https://x --secret 喵   # 用 A 产出的图复测
```

未安装 opencv/pyzbar 时，扫码列**留空并在报告中标注「未测」**，不会填 0。

作为库调用（对应 `docs/成员剩余任务与接口交接.md` §5 的 F 接口）：

```python
from experiments.robustness import make_case, run, summarize

records = run(
    [make_case("cat01", "https://example.com", "来自喵星人的问候", key="")],
    {"attacks": ["jpeg", "crop"], "strengths": [0, 40, 80], "seed": 20261107},
)
```

`run(cases, config) -> list[dict]` 每次实验返回一条记录，字段即 §7 的统一 CSV 列，不只返回平均值。

## 4. 输出

```
experiments/results/
  robustness_raw.csv      每次实验一行，126 行（3 样本 × 7 干扰 × 6 强度）
  robustness_summary.csv  按 干扰×强度 汇总的分子/分母与均值
  robustness_report.md    自动生成的报告（环境、逐档表格、结论、局限）
  robustness_env.json     环境与参数快照
experiments/samples/      干扰后的样例图（默认取中间强度）
```

CSV 严格遵守 §7 列序；`scan_success` / `secret_success` 用 1/0 表示已测结果，**未测留空**；
`integrity_status` 保留 `passed / failed / unknown`；密钥只以 `lsb-keyed` / `lsb-sequential` 体现，不写具体值。

## 5. 实测结论（3 个样本、seed=20261107、OpenCV 解码）

| 干扰 | 扫码成功上限 | 秘密恢复 |
|---|---|---|
| 高斯噪声 | 强度 100 仍 3/3 | 强度 20 起 0/3 |
| JPEG 压缩 | 强度 100（质量约 5）仍 3/3 | 强度 20 起 0/3 |
| 旋转 | 强度 20 仍 3/3，40 起 0/3 | 强度 20 起 0/3 |
| 四周裁剪 | 强度 20 仍 3/3，40 起 0/3 | 强度 20 起 0/3 |
| 椒盐噪声 | 强度 20 降到 1/3，40 起 0/3 | 强度 20 起 0/3 |
| 中心遮挡 | 强度 60 仍 3/3，80 起 0/3 | 13/15 仍可恢复（白块没压到条带） |
| 定点遮挡 | 全部 3/3 仍可扫 | **0/15**，一压条带就全灭 |

四条主要结论：

1. **凡是改写像素的干扰，秘密恢复率在强度 20 时就是 0**（合计 0/75）：LSB 存最低位，重编码、插值、叠加噪声都会直接改写这些位。
2. **二维码的耐受力来自纠错码**：JPEG 压到质量约 5、噪声 σ=40 仍能扫出，因为它只要求码字在容错范围内可恢复，而 LSB 要求每一位都精确。
3. **遮挡的位置比面积更关键**：中心遮挡 60% 强度时秘密仍 100% 可恢复；同样面积压在条带上就 0/15。这既解释了为什么前端现有用例不足，也是答辩时可以讲的一个点。
4. **完整性判据目前与「能否恢复」同生共死**：HMAC 必须先读到 40 字节包头才生效，数据被破坏后结果多为 `unknown`（无法判断）而不是 `failed`（判定篡改）——这正是 D 要补的缺口，也说明「提取失败 ≠ 被篡改」。

## 6. 局限（写进 PPT 的「局限」页）

- **解码器不是手机**：用 OpenCV `QRCodeDetector` 并固定「失败则 2 倍放大再试一次」，不做多轮调参；手机扫码通常更宽容，所以表里的扫码成功率是**保守下界**。真实手机扫码要按 README 的演示顺序另行记录，不并入本表。
- Python 噪声用 `numpy.random.default_rng(seed)`，与浏览器 LCG 实现不同，统计口径一致但像素不可逐一对齐。
- 完整性判据只有 CAT1 的 HMAC（只覆盖消息，不覆盖整幅图像）。
- 载体是 `core.service.generate` 的**内置猫咪并置基线**，不是 A 的艺术融合成果；A 交付后用 `--carrier` 重跑，结论才对最终载体成立。
- 每档强度只有 3 个样本，成功率是粗粒度估计（0%、33%、100% 这种颗粒），要更细的曲线就加 `--samples` 或 `--repeats`。

## 7. 和别人的接口关系

- 只读调用 `core.service`（当前等于 `core.baseline`）的 `generate / embed / extract`，**不改动任何其他人的模块**；A/B/G 接入后自动跟着换。
- 不写 `core/service.py`，不碰前端；若要暴露成 HTTP，建议组长在 `core/service.py` 加一层适配，路由见 §6 的 `/api/experiments/robustness`。
- 与 C 的分工：本模块只测「能不能扫出、能不能提取、校验是否通过」，不产出隐写检测分数（CSV 的 `detection_score` 留空）。
- 与 E 的分工：PSNR 只作为干扰强弱的参考量，SSIM 的定义归 E，这里不填。
