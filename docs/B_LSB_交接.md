# B：CAT1 LSB 实现交接（v2 · 复审与移植后）

日期：2026-11-09。v1 由上一位专家在 C 盘工作副本产出，未写回 E 盘仓库；v2 为接手后完成复审、移植、补测与实测的记录。**本文所有数字均为本机真实运行结果，未把未验证项计为通过。**

- 原仓库：`E:/test/xiaomaomi-de-mim`，`main` 保持干净未改动；本轮所有改动在 `feature/B-lsb` 分支。
- 上轮工作副本：`C:/Users/LENOVO/Documents/Codex/2026-11-09/xiaomaomi-b-lsb/work/xiaomaomi-de-mim`（只读留档，未删除）。
- 上轮完整交接稿（含全部源码附录）：`C:/Users/LENOVO/Documents/Codex/2026-11-09/xiaomaomi-b-lsb/outputs/B_LSB_交接.md`。

## 1. 上轮产出的复审结论

先逐文件核对了工作副本与 E 盘原仓库：`core/baseline.py`、`core/service.py`、`core/__init__.py`、`app.py`、`README.md`、`requirements.txt`、`tests/test_roundtrip.py`、`tests/verify_mvp_http.py`、两份统一接口文档、`.gitignore` 共 11 个非 B 文件**逐字节一致**，上轮没有越界修改其他成员或组长的模块，符合分工规范。

| 复审项 | 结论 |
|---|---|
| CAT1 区域、位序、封包、HMAC、SHA-256 种子置乱 | 与 `core/baseline.py` 完全一致；`positions()` 的 96000 位顺序、每字节高位优先、`random.Random` 种子派生均正确 |
| `embed` / `extract` 签名与返回字典 | 符合 `统一接口与协作.md` 的目标签名；`metadata` 不含密钥或秘密，提取端不依赖未保存的隐藏状态 |
| 容量与异常规范 | 11960 UTF-8 字节边界、非约定区域拒绝、TypeError/ValueError 区分、passed/failed/unknown 三态均正确 |
| 文档与实测是否相符 | 上轮记录的 9/9 单测、示例 PNG SHA-256、6/6 像素一致，在新环境均可复现；无伪造数值 |
| 上轮未完成项 | 全套回归被缺失的 `qrcode==8.2` 阻断（环境问题，非代码缺陷）；兼容性验证只手工跑过一次；未建分支、未移植、未做真实二维码载体验证 |

发现并已修正的四个具体问题：

1. **全套回归未通过**：上轮 `python -m unittest discover -s tests -v` 因 `ModuleNotFoundError: No module named 'qrcode'` 报 1 个错误。本轮用官方 PyPI 源把 `requirements.txt` 固定依赖装进项目 `.deps`（清华镜像不可用），阻断解除。
2. **6 组兼容性检查没有固化成测试**：只在交互式会话里手工比对过输出像素。新增 `tests/test_steganography_compat.py`，把「两边 embed 输出逐字节相同」+「PNG 重存后双向交叉提取」+「容量异常一致」变成可重复回归。
3. **截断 PNG 用例脆弱**：`Image.open(...[:60])` 能否打开取决于 Pillow 版本的惰性加载行为，换版本可能让测试直接 error。已改为容忍 `Image.open` 阶段抛 `OSError`，并新增 `test_unreadable_pixels_are_unknown` 用 mock 确定性地覆盖 `extract` 的 `OSError` 分支。
4. **示例是合成载体，没有公开扫码链路**：新增 `examples/b_qr_carrier_check.py`，用现有 MVP 二维码载体分别实测扫码与秘密恢复，并逐字节确认二维码区域未被改动。

另复核了跨版本风险：上轮环境为 Python 3.12.14，本轮为 3.13.14，两个来自旧 `baseline.py` 的 SHA-256 像素向量仍全部匹配，说明 3.12→3.13 的 `random.Random.shuffle` 位置复现稳定；但**跨语言、跨随机库仍不保证**，文档中保留该限制。

## 2. 当前交付文件（均在 `feature/B-lsb`）

| 文件 | 来源 | 用途 |
|---|---|---|
| `core/steganography.py` | 上轮移植，未改 | CAT1 兼容的容量、位置、嵌入、提取 |
| `tests/test_steganography.py` | 上轮移植 + 本轮补 1 例、修 1 例 | 10 项 B 单测（含两组基线像素向量） |
| `tests/test_steganography_compat.py` | 本轮新增 | 与原 `baseline.py` 的双向兼容回归（3 项） |
| `examples/b_lsb_demo.py` | 上轮移植，未改 | 可重复生成合成 CAT1 PNG 并校验 |
| `examples/b_lsb_cat1.png` | 上轮移植，未改 | 240×240 合成载体样例（非二维码） |
| `examples/b_qr_carrier_check.py` | 本轮新增 | MVP 二维码载体双链路实测 |
| `examples/b_a_carrier_check.py` | 本轮新增 | A 艺术融合真图的双链路联调（只读 A 素材，不依赖 numpy） |
| `examples/b_qr_carrier_results.json` | 本轮新增 | MVP 双链路实测快照（进仓库，只记 key_mode） |
| `examples/b_a_carrier_results.json` | 本轮新增 | A 真图联调实测快照（进仓库，含输入 SHA-256） |
| `docs/B_LSB_算法说明.md` | 上轮移植 + 本轮更新 | 接口、协议、异常、**服务层适配示例**与局限 |
| `docs/B_LSB_PPT内容.md` | 上轮移植 + 本轮更新 | 答辩第 5 页文案（按统一框架） |
| `docs/B_LSB_交接.md` | 本文件 | 复审、移植、实测与剩余待办 |

`B_LSB_PPT内容.md` 仍是交给组长排版的文案，不是 PPTX；B 未生成 PPTX，以免与组长统一模板冲突。

## 3. 依赖与复现命令

项目根目录执行（Windows，Python 3.13.14）：

```powershell
python -m pip install --target .deps -r requirements.txt
python -m pip install --target .deps pyzbar   # 可选：启用真实扫码解码
python -m unittest discover -s tests -v
python examples/b_lsb_demo.py
python examples/b_qr_carrier_check.py
python examples/b_a_carrier_check.py --image <A 生成的 PNG>   # 需 A 的融合图，见第 4 节
python -m py_compile core/steganography.py tests/test_steganography.py tests/test_steganography_compat.py examples/b_lsb_demo.py examples/b_qr_carrier_check.py examples/b_a_carrier_check.py
```

仓库内 `examples/*_results.json` 是实测快照：`b_qr_carrier_check.py` 与 `b_a_carrier_check.py` 都支持 `--output`，默认写到被忽略的 `outputs/`，指定 `--output examples/...` 即可刷新快照。

本轮环境：Python 3.13.14、Pillow 13.0.0、qrcode 8.2、pyzbar 0.1.9（后两者装在项目 `.deps`，被 Git 忽略）。未安装 pyzbar 时扫码状态为 `unverified`，脚本返回非零，不会伪装成通过。

## 4. 本轮真实测试结果

| 命令 | 结果 |
|---|---|
| `python -m unittest discover -s tests -v` | **15/15 通过**（两次运行约 2.09 s / 2.05 s）：原有 `test_roundtrip.py` 2 项、B 单测 10 项、兼容回归 3 项 |
| `python -m unittest discover -s tests -p test_steganography.py -v` | B 单测 10/10 通过 |
| `python examples/b_lsb_demo.py --output outputs/b_lsb_cat1_regen.png` | `status=passed`、`payload_bytes=10`、`capacity_bytes=11960`；重新生成的 PNG 与交付样例 SHA-256 完全一致：`aca0e8a4784f0dd1b77c922652bc0989df3b645206be25f58819bd3d4c77390c` |
| `python examples/b_qr_carrier_check.py` | 总体 `passed`，退出码 0 |
| `python examples/b_a_carrier_check.py` | A 艺术融合真图联调 **2/2 通过**（`overall=passed`）：嵌入前后扫码均为 `https://example.com/hello`、秘密 UTF-8 原文一致、CAT1 区域外改动 0 像素 |
| `python -m py_compile ...`（五个文件） | 通过 |
| 内存请求流直接调用 `app.Handler` 的 8 项请求处理核查 | 8/8 通过（generate/extract/detect/400/404）；**不等于 HTTP 全链路** |
| 真实 HTTP 连接 `127.0.0.1:8000` | 端口可绑定，但 TCP 连接 `TimeoutError: timed out`，沙箱网络限制仍在，未通过 |

请求处理核查是本机临时脚本（`outputs/b_http_inprocess_check.py`）与结果（`outputs/b_http_inprocess_results.json`），均被 Git 忽略、**不属于 B 的仓库交付**；它实例化组长的真实 Handler，用内存流替代 socket，验证本分支没有破坏现有服务层的请求处理，但不验证 TCP、Vite 代理或浏览器。

双链路实测细节（原始记录 `outputs/b_qr_carrier_results.json`）：载体为 `core.baseline.generate()` 输出的 496×296 PNG，公开文本 `https://example.com/cat1`，秘密 28 字节，CAT1 区域 `(316, 32, 160, 200)`。空密钥与有密钥两种模式下：

- 嵌入前 pyzbar 解码公开文本 `passed`；嵌入后重开 PNG 再次解码仍 `passed`，文本与原文一致；
- 二维码区域 `(0,0,296,296)` 与猫咪条带左右各 20px 保留区**逐字节未变**；
- PNG 写盘重开后 `extract` 返回 `passed`，秘密 UTF-8 原文完全一致。

注意：这是**组长 MVP 的二维码与猫咪条带并置载体**；扫码为 pyzbar 程序解码，不是手机扫码，不能替代 A 的正式扫码验收。

A 真图联调（本轮新增，原始记录 `examples/b_a_carrier_results.json`）：输入为 A 的 PR #1 中 `outputs/qr_test/case_1_H_level_with_cat.png`，610×410 RGB，SHA-256 `0fb1dc04d1ce3760c832ff93c19b68002634d6897ddc381308bfcf8b218cccca`，公开文本 `https://example.com/hello`，CAT1 区域 `(430,32,160,200)`。空密钥与带密钥两种模式下，嵌入前后 pyzbar 解码文本一致、PNG 重开后 `extract` 均 `passed` 且秘密原文一致、CAT1 区域外像素改动数均为 0。**该区域原本 32000 像素全为纯白**（A 的 `protected_mask` 使猫图不覆盖），写 LSB 后统计特征明显，C 的检测模块容易命中；这是 CAT1 固定区域的固有代价，不是嵌入错误。素材本身未收录进仓库，JSON 以输入 SHA-256 追溯；A 合入后应以 `generate()` 现场输出复测。

## 5. 上轮文档中「下一位专家动作」的完成情况

1. 建立 `feature/B-lsb` 分支并移植六个 B 文件 —— **已完成**（另加两份新文件；`main` 干净）。
2. 装齐固定依赖后重跑 B 单测、全套 Python 回归与示例脚本并记录真实输出 —— **已完成**，见第 4 节。
3. 由 A/组长交付真实可扫码载体并分别实测扫码与恢复 —— **基本完成**：MVP 二维码载体已完成程序解码 + 秘密恢复双链路；本轮另从 A 的 PR #1 取其 610×410 艺术融合真图完成联调（2/2 通过，CAT1 区域外 0 像素改动）。仍待：手机扫码记录；A 的 PR 合入 `main` 后用 `core.qr_generator.generate()` 现场输出再复测一次。
4. 组长在 `core/service.py` 增加适配、保持 HTTP 协议 —— **未做，且不属 B 分支范围**（分工规定 B 不修改服务层）。
5. G 改置乱或自适应规则须独立格式标识 —— **未做**，属 G 与组长联调事项。

## 6. 仍需说明的边界

- 错误密钥通常返回 `unknown`，不能断言恶意篡改；`failed` 只说明 HMAC 覆盖的秘密消息不一致。HMAC 不覆盖二维码、猫咪外观或整幅 PNG。
- 置乱不等于加密；空密钥的 HMAC 没有密钥认证意义。
- `extract` 只捕获 `OSError` 类图像读取失败；PNG 连文件头都无法解析时，`Image.open` 在调用模块前抛异常，需由服务层捕获。超大图的 `DecompressionBombError` 亦由服务层的像素上限约束。
- 仅 PNG 等无损路径可用；JPEG、缩放、旋转、裁剪、量化会破坏位置或最低位。
- 本轮**未完成真实 HTTP 全链路与浏览器验收**：`127.0.0.1:8000` 可绑定但 TCP 连接超时，沙箱网络限制与上轮 MVP 验收记录一致；`web/node_modules` 未安装，前端 `npm test` / `npm run build` 未重跑（B 分支不改动 `web/`）。请求处理 8/8 通过不能写成网页验收通过。
- 密钥值不写入图片、日志、CSV、JSON 结果或仓库；结果文件只记录 `key_mode`。
- `outputs/`、`.deps/`、`__pycache__/` 均被 Git 忽略，不进提交；需要交付的原始结果已用 `--output` 生成快照放在 `examples/`，组内 clone 后可直接查看。
