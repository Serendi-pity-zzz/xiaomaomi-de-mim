# G 实验所用的成员模块快照

这里的 A/B/C/F 代码由对应组员编写，G 只作实验引用，不主张其作者身份。
`g_manifest.json` 记录原分支、完整提交号、仓库路径和 SHA256，原始正文保持原样，Python 文件前新增中文用途和关联文件注释。

保留快照是为了让尚未合并 A/B/C 的 main 分支也能独立复现实验，并冻结比较版本。
这些文件不会覆盖公共 `core` 或 F 的原模块，也不会替换公共服务。
集成时应由组长调用正式成员模块；不要把这份快照作为第二套生产实现。

G 的实现位于 `core/g_adaptive_steganography.py`、`core/g_png.py`；实验适配器为
`experiments/g_team_adapter.py`。A 的掩码语义和猫图填充调整只发生在 G 实验适配器内。

文件统一使用 g_ 前缀。manifest 中 path 是原提交路径，local_path 是当前副本路径；sha256 验证原始正文，annotation_bytes 记录新增注释的字节数，annotated_sha256 验证带注释的完整文件。C 的校准文件通过 calibration_path 显式指定，避免依赖旧文件名。
