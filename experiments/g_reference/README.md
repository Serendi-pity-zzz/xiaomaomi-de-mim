# G 实验所用的成员模块快照

这里的 A/B/C/F 代码由对应组员编写，G 只作实验引用，不主张其作者身份。
`manifest.json` 记录原分支、完整提交号、仓库路径和 SHA256，文件字节保持原样。

保留快照是为了让尚未合并 A/B/C 的 main 分支也能独立复现实验，并冻结比较版本。
这些文件不会覆盖公共 `core` 或 F 的原模块，也不会替换公共服务。
集成时应由组长调用正式成员模块；不要把这份快照作为第二套生产实现。

G 的实现位于 `core/adaptive_steganography.py`、`core/g_png.py`；实验适配器为
`experiments/g_team_adapter.py`。A 的掩码语义和猫图填充调整只发生在 G 实验适配器内。
