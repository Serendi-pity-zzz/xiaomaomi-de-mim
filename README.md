# 小猫咪的秘密

组长集成 MVP。原始分工见 `小猫咪的秘密_小组分工.md`。

## 运行

Python 3.10+。在项目目录执行：

```powershell
python -m pip install --target .deps -r requirements.txt
cd web
npm install
npm run build
cd ..
python app.py
```

浏览器打开 http://127.0.0.1:8000 。生成并下载 PNG，然后上传原图，以相同密钥提取。用手机单独验证公开二维码。停止服务按 Ctrl+C。

前端使用 React 19 + 严格 TypeScript + Vite，入口 `web/src/main.tsx`，样式 `web/src/styles.css`。开发时先运行 `python app.py`，另开终端在 `web` 目录运行 `npm run dev`，访问 http://127.0.0.1:5173 。Vite 将 `/api` 请求代理到 Python 后端。发布或单服务演示前执行 `npm run build`，后端提供 `web/dist` 中的构建产物。

检测、完整性、鲁棒性和对比页面已经接入可用基线与浏览器处理，尚未实现的算法明确标注。无后端演示：在 web 运行 `npm run dev:demo`，访问 http://127.0.0.1:5174 。运行 `npm test` 执行前端测试；`npm run build:demo` 单独构建演示版本。详细接口边界见 `docs/前端API与模式.md`。

```powershell
python -m unittest discover -s tests -v
```

## 当前范围

已实现前端、HTTP 服务、二维码与猫咪并置基线、顺序/密钥置乱 LSB、消息 HMAC 校验。猫咪是代码绘制示例，无外部图片版权依赖。并置方案不等同于 A 的艺术融合成果。

密钥不是加密，空密钥校验只能发现偶发损坏；有密钥时 HMAC 保护消息，不能校验整个图像或定位篡改。随机位置算法依赖 Python random，跨语言实现需统一位置生成规范。C 的卡方检测、D 的区域完整性、E/F 实验、G 自适应算法尚待成员交付。界面不伪造这些结果。

目录：`core/` 模块及集成入口，`web/` 前端，`tests/` 回归验证，`docs/` 统一约定，`experiments/` 成员实验脚本位置。部署仅绑定本机，适用于课程演示。

## 演示顺序

1. 输入公开链接与中文秘密，生成 PNG。
2. 手机扫码确认公开信息；记录手机、扫码工具、时间和成功情况。
3. 下载并重新上传 PNG，输入相同密钥恢复秘密。
4. 输入错误密钥，展示无法判断状态；解释不能直接称为“篡改”。
5. 运行回归测试展示消息位翻转后的校验失败。
6. C–G 接入后用真实 CSV 展示检测与鲁棒性结论。

答辩框架和成员提交要求见 docs。当前未宣称所有成员功能已经验收。

## 团队模块

Web 默认使用内置 CAT1 载体，消息编解码接入 B，检测接入 C 的卡方及 RS 辅助特征。A 的艺术融合和 G 的自适应载体目前通过独立脚本运行。

D 的图像认证支持独立密钥、外置可信元数据和分块定位。运行 `python d_integrity_cli.py --help` 查看用法，见 `docs/d_mimi/接口交接.md`。Web 完整性页仍提供消息校验与参考图 RGB 对照。

E/F 实验脚本与实测记录位于 `experiments/`。综合回归可使用 `python -B tests/g_run_tests.py`，实验依赖见 `experiments/g_requirements-research.txt`，D 的扫码联调测试另外需要 `zxing-cpp==3.1.1`。G 的归档鲁棒性副本与清单哈希存在差异，需由交付者核对原始快照。
