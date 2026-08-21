# Vivo Lightroom Archive Converter v1.8

首个公开版本。目前只在 Vivo X200 Ultra 的这一种 4K60 HEVC Main 10、HLG、Dolby Vision Profile 8.4 三时间子层录制结构上验证通过；其他设备或拍摄模式会被严格拒绝。

原片本身没有损坏且可正常播放，但 Lightroom Classic 的 Adobe MediaCore 无法在打开阶段解析其三时间子层 HEVC 结构。转换后的单时间层 `hvc1` HEVC Main 10、4K60、BT.2020 HLG、AAC 组合已验证能够导入，同时继续保留 Dolby Vision、EIS 和拍摄元数据。

## 主要功能

- 严格输入指纹：结构不匹配即拒绝转换；
- 默认 x265 CRF 8 档案模式；
- 实验性 Apple VideoToolbox Q65 模式；
- 保留 AAC、EIS、Dolby Vision RPU/`dvvC`、PTS、方向、GPS 和拍摄元数据；
- 多文件拖放和批量队列；
- 每个输出在正式命名前完成逐项复检；
- 不覆盖原片或已有输出。

## 安装

1. 下载并解压 `Vivo-Lightroom-Archive-Converter-v1.8-macOS-arm64.zip`；
2. 首次使用先双击 `install_dependencies.command`；
3. 将 App 移入“应用程序”文件夹；
4. 如果 macOS 拦截未公证 App，请在 Finder 中右键 App 并选择“打开”。

Release 不捆绑 FFmpeg、PyAV 或 dovi_tool。安装脚本通过 Homebrew/PyPI 安装 FFmpeg、Python 3.12、dovi_tool 2.3.3 和 PyAV 18.1.0。完整原因与许可证说明见 README 和 THIRD_PARTY_NOTICES。

## 校验

Release asset SHA-256：

```text
c0bb8b408c22c58d9d56dcb8b9317b7ef27498453d09fb0da7c242bc0edfcdee
```

## 已知限制

- 只支持 Apple Silicon 和 macOS 14+；
- 只接受与已验证参考结构严格匹配的输入；
- VideoToolbox Q65 为实验选项，长期档案推荐默认 x265 CRF 8；
- App 使用 ad-hoc 签名，尚未使用 Apple Developer ID 公证。
