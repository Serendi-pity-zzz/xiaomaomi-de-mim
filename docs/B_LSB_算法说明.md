# B：CAT1 基础 LSB 算法说明与接口交接

更新：2026-11-09。范围仅限 B 的隐写模块、测试与示例；组长负责把模块接入 core/service.py，A 负责可扫码的猫咪二维码载体，G 负责改进算法。

## 1. 输入、输出和调用

依赖 Python 3.10+、Pillow（仓库 requirements.txt 固定 13.0.0）。模块文件为 core/steganography.py；测试为 tests/test_steganography.py 与 tests/test_steganography_compat.py；示例为 examples/b_lsb_demo.py、examples/b_qr_carrier_check.py、examples/b_a_carrier_check.py；仓库内实测记录为 examples/b_qr_carrier_results.json、examples/b_a_carrier_results.json。模块本身不依赖二维码生成库，输入是调用方提供的 Pillow Image。返回的 image 是独立 RGB 图像，原始 image 不被修改。

- capacity_bytes(image, region=None) -> int：验证 CAT1 尺寸与区域，返回净载荷容量 11960 UTF-8 字节。
- embed(image, secret: str, key: str = "", region=None) -> dict：返回 image、capacity_bytes、metadata。metadata 仅含 format、algorithm、region、payload_bytes，不保存密钥或秘密。
- extract(image, key: str = "", region=None) -> dict：返回 status、secret、detail。成功时 status 为 passed；其余情况 secret 为 None。
- positions(image, key="", region=None) -> list：公开 CAT1 位位置顺序，供调试和边界测试；一般调用方不必依赖。

region 使用 (x, y, width, height)；省略时由图像宽度恢复固定 CAT1 区域。有参时必须等于 (image.width - 180, 32, 160, 200)，否则抛 ValueError。这样提取端不依赖未保存的外部元数据。A 若改动猫咪位置或需要避开保护 mask，必须设计新版载体协议，不能以 CAT1 名义使用新区域。当前模块不消费 protected_mask；A/服务层须保证固定区域可写。

调用示例：

~~~python
from PIL import Image
from core.steganography import embed, extract

with Image.open("carrier.png") as source:
    result = embed(source, "你好🐱", key="演示密钥")
result["image"].save("stego.png", format="PNG")
with Image.open("stego.png") as saved:
    recovered = extract(saved, key="演示密钥")
assert recovered["status"] == "passed"
assert recovered["secret"] == "你好🐱"
~~~

上例的密钥仅是演示占位文本。真实密钥不写入图片文件、日志、CSV 或公开仓库。返回字典中的 Pillow image 不是 JSON 值；服务层应先编码为 PNG 再转 Base64。此模块尚未接入现有 HTTP 服务，不能把模块测试当作网页验收。

## 2. CAT1 位流和容量

固定区域：x 从 image.width - 180 到 image.width - 20（右端不含），y 从 32 到 232（下端不含）；图像至少 200×240 像素。依次遍历 y、x、RGB 通道，取每个通道最低位。区域总位数 160 × 200 × 3 = 96000 位，即 12000 字节。

封包为 ASCII CAT1（4 字节） + 大端 uint32 消息字节数（4 字节） + HMAC-SHA256(key 的 UTF-8 字节, 消息字节)（32 字节） + UTF-8 消息。头部 40 字节，因此净容量 12000 - 40 = 11960 字节。容量按编码后的字节检查，空文本允许；恰好 11960 字节允许，11961 字节抛 ValueError。每个字节按最高位到最低位写入。每次只改一个 RGB 通道的最低位。

空 key 按上述顺序写入；非空 key 先以 SHA256(UTF8(key)) 摘要转成大端整数，作为 Python random.Random 的种子，再 shuffle 完整 96000 个位置。该规则沿用 core/baseline.py，不能直接替换为其他语言的随机库或不同的派生方法。metadata 的 algorithm 仅区分 lsb-sequential 与 lsb-keyed；不改变封包。位置置乱不是加密。

提取先读 40 字节头；无 CAT1 标记返回 unknown；长度超过容量返回 failed；之后读消息、比对 HMAC、按 UTF-8 解码。HMAC 不匹配或编码无效返回 failed；一致则返回 passed。HMAC 只覆盖消息，不覆盖二维码、猫咪外观或整个 PNG。空 key 的 HMAC 没有密钥认证意义，只能识别偶发损坏。错误密钥通常没有 CAT1 标记，返回 unknown，不能将其断言为恶意篡改。

## 3. 异常与限制

| 情况 | 模块行为 |
|---|---|
| 图像尺寸不足、显式 region 与 CAT1 不符、消息超过 11960 字节 | ValueError |
| image 不是 Pillow Image，secret/key 不是字符串 | TypeError |
| secret/key 含无法编码的 Unicode 代理码点 | ValueError |
| 没有标记或密钥无法复现位置 | unknown，secret=None |
| 长度字段损坏、消息位改变、HMAC 不符 | failed，secret=None |
| 已识别为 Pillow 图像但像素数据截断、无法加载 | unknown，secret=None |
| PNG 连图像头都无法解析 | Image.open 在调用模块前抛异常，服务层需捕获 |

仅使用 PNG 或其他无损像素路径。JPEG、缩放、旋转、裁剪或色彩量化会改变位置或最低位，不能保证秘密恢复。未经独立扫码验证，不能声称示例 PNG 可供普通扫码。二维码公开内容验证由 A/组长另行记录。

## 4. 可复现样例与测试

在项目根目录安装 requirements.txt 后运行：

~~~powershell
python -m pip install --target .deps -r requirements.txt
python -m unittest discover -s tests -v
python examples/b_lsb_demo.py
~~~

`examples/b_lsb_demo.py` 构造 240×240 合成 RGB 载体，写入空 key 的 10 字节 UTF-8 文本，生成 `examples/b_lsb_cat1.png`，再重开 PNG 并校验提取。它是 B 的无损位流样例，**不是二维码**；输入固定，可用 `--output` 指定其他路径重新生成。本轮重生成的 PNG 与交付样例 SHA-256 完全一致，无私人图片或密钥。

可选扫码验证（需额外安装 `pyzbar`）：

~~~powershell
python -m pip install --target .deps pyzbar
python examples/b_qr_carrier_check.py
~~~

该脚本用现有 MVP 二维码载体（`core.baseline.generate`）分别跑两条链路：pyzbar 真实解码公开文本并与原文比对；B 模块在 PNG 写盘重开后恢复秘密。同时逐字节确认二维码区域和猫咪条带两侧各 20px 保留区未被改动。结果写入 `outputs/b_qr_carrier_results.json`（被 Git 忽略），只记录 `key_mode`，不写密钥值。缺 pyzbar 时扫码状态为 `unverified`，脚本返回非零，绝不记为通过。**该载体是二维码与条带并置的 MVP 图，不是 A 待交付的艺术融合图；程序解码也不等于手机扫码。**

A 的艺术融合载体联调（2026-11-09 新增）：

~~~powershell
python examples/b_a_carrier_check.py --image <A 生成的 PNG>
~~~

`examples/b_a_carrier_check.py` 只读 A 的产物图，不修改 A 的模块、不依赖 numpy。用 `--image` 指定 A 的 PR #1 中 `outputs/qr_test/case_1_H_level_with_cat.png`，即可验证 B 在真实融合图上嵌入后公开文本仍可解码、秘密可恢复、CAT1 区域之外像素零改动。缺 pyzbar 时扫码标 `unverified` 并返回非零。结果写入 `examples/b_a_carrier_results.json`（进仓库，只记 `key_mode`，不写密钥）。A 的素材本身未被本仓库收录，JSON 中记录了输入 SHA-256 便于追溯；A 的 PR 合入 `main` 后，可把 `core.qr_generator.generate()` 的输出另存为 PNG 传给同一脚本复测。两个脚本默认把运行时结果写到 `outputs/`（被 Git 忽略），仓库内的 `examples/*_results.json` 是用 `--output` 生成的快照，供组员 clone 后直接查看，无需重跑。

测试覆盖空消息、中文与 emoji、最大容量、UTF-8 字节边界、原图不变、PNG 重存、错误密钥、无标记图、消息位破坏、长度与标记破坏、截断 PNG、无效类型、固定区域、像素读取异常。两个 SHA-256 像素向量来自原 `core/baseline.py`。`tests/test_steganography_compat.py` 另外固化了与原基线的双向兼容：6 组组合输出像素逐字节一致，PNG 重存后旧/新模块互相提取一致，容量异常行为一致。

本轮实测（2026-11-09，Python 3.13.14 / Pillow 13.0.0 / qrcode 8.2 / pyzbar 0.1.9）：全套 `15/15` 通过；示例脚本 `status=passed`；MVP 二维码载体双链路两种密钥模式均 `passed`，二维码区域逐字节不变。

A 真图联调实测（同一环境，记录见 `examples/b_a_carrier_results.json`）：输入 610×410 RGB 艺术融合图，公开文本 `https://example.com/hello`，CAT1 区域 `(430,32,160,200)`；空密钥与带密钥两种模式下，嵌入前后 pyzbar 均解码出同一公开文本，`extract` 均 `passed` 且 UTF-8 原文一致，CAT1 区域之外被改动的像素数均为 **0**。**注意该区域 32000 个像素原本全是纯白 `(255,255,255)`**（A 的 `protected_mask` 使猫图不覆盖此区），写入 LSB 后统计特征明显，C 的检测模块容易命中；这是 CAT1 固定区域的固有代价，不是嵌入错误，联调时应主动说明。该结论仍基于 pyzbar 程序解码，不是手机扫码，也不替代 A 的正式验收。

上轮环境为 Python 3.12.14，像素向量一致，说明该版本区间内 `random.Random` 置乱可复现；跨语言仍不保证。完整命令、输出与复审结论见 `B_LSB_交接.md`。

## 5. 给组长与 A/G 的接口说明

- 原始图来自 A 的 generate(...) 返回 image，或现有基线生成器；B 不产生二维码，也不改变 core/service.py。
- A 的图像必须为 RGB 或可转 RGB，尺寸至少 200×240，固定区域内无禁止改动像素。把 A 返回的 region 传给 embed 可立即校验是否保持 CAT1。
- B 的 metadata 是说明性数据，不是提取必需状态。提取端由图像宽度和 key 恢复位置；PNG 中自带 CAT1 标记和消息长度。
- G 的新置乱或自适应策略须有独立格式/算法标识，不得复用 CAT1 并悄悄改变位置规则。
- 组长接入时将 embed(...) 的 image 编码为 PNG Base64，并把 ValueError 映射为已处理的 400；保持现有 /api/generate 与 /api/extract 协议。接入后重新验证扫码和秘密恢复两条链路。

供 `core/service.py` 改写的适配示例（**B 不修改服务层**，以下只是交接参考）：

~~~python
# 现状：from .baseline import generate, embed, extract
from .baseline import generate                       # 原始载体仍由 A / 组长提供
from .steganography import embed as lsb_embed, extract as lsb_extract

def hide(image, secret, key=""):
    try:
        return lsb_embed(image, secret, key)["image"]  # 返回 dict，需取 ["image"]
    except ValueError as exc:                          # 容量 / 尺寸 / region 不合法
        raise BadRequest(str(exc)) from exc            # BadRequest = 服务层已有的 400 异常类型

def reveal(image, key=""):
    result = lsb_extract(image, key)                   # 不抛异常，返回三态
    return {"status": result["status"],
            "secret": result["secret"],
            "detail": result["detail"]}
~~~

三个易错点：`embed` 返回 dict 而不是 Image；`extract` 的 `passed / failed / unknown` 三态要原样透传给 `/api/extract`，不能把 `unknown` 当成功；PNG→Base64 与 `Image.open` 仍在 `app.py`，B 模块只接收和返回 Pillow Image。接入后请重跑 `python -m unittest discover -s tests -v`、两个 `examples/*_check.py`，并补一条真实 HTTP 链路验收。

- 已用现有 MVP 二维码载体（`examples/b_qr_carrier_check.py`）与 A 的艺术融合真图（`examples/b_a_carrier_check.py`）分别完成「程序扫码 + 秘密恢复」双链路实测，均为 2/2 通过。**手机扫码记录仍待补**；A 的 PR 合入 `main` 后应以 `core.qr_generator.generate()` 的现场输出再复测一次。B 不修改 `core/service.py`。
