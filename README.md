# Vivo Lightroom Archive Converter

A narrowly scoped macOS converter for a specific Vivo X200 Ultra HEVC recording profile that Lightroom Classic cannot import directly.

> This is not a general-purpose video converter. Inputs are rejected unless their container, tracks, sample descriptions, HDR metadata and temporal-layer structure match the validated reference profile.

> **验证范围：目前只在 Vivo X200 Ultra 的这一种录制结构上验证通过。其他 Vivo 机型、其他拍摄模式或结构不同的 X200 Ultra 文件都会被拒绝，不会尝试猜测性转换。**

中文说明为主；关键安装命令和错误信息均可直接复制使用。

## 背景：为什么需要转换

已验证的源文件是 Vivo X200 Ultra 生成的 4K60、HEVC Main 10、HLG、Dolby Vision Profile 8.4 视频。文件没有损坏，QuickTime 和 FFmpeg 均能正常播放或完整解码；但 Lightroom Classic 的视频导入器并不是“能播放就能导入”，它会先用 Adobe MediaCore 解析 MP4 和 HEVC 头部。

这类原片的 VPS/SPS 声明三个 HEVC temporal sub-layers。实际边界测试表明：Lightroom 可以接受规范化后的 MP4、`hvc1`、HEVC Main 10、4K60、BT.2020 HLG、AAC，以及保留下来的 Dolby Vision/EIS/拍摄元数据；直接触发失败的是原始三时间子层 HEVC 结构。失败发生在打开文件阶段，尚未进入正常画面解码。

因此本工具把视频重新编码为 Lightroom 已验证可接受的**单时间层 HEVC Main 10 HLG**，而不是降为 H.264 或 SDR。这里所说的“Lightroom 接受要求”是针对本机和这组样本得到的兼容性边界，不代表 Adobe 对所有版本、平台和编码器的官方完整规格。

本工具只重新编码视频基础层为单时间层 HEVC，同时尽可能原样保留：

- 3840×2160、60 fps、10-bit、BT.2020 HLG；
- 原始显示时间戳 PTS；
- AAC 包内容与时间；
- Vivo EIS metadata 包内容与时间；
- Dolby Vision RPU 与 `dvvC` 配置；
- 旋转矩阵、GPS、拍摄时间、Android/Vivo 私有元数据；
- 原始文件 SHA-256 和转换方式 provenance。

必然变化的部分包括视频压缩数据、GOP/DTS、HEVC 参数集、三时间层到单时间层、码率和 MP4 内部数据排布。`com.android.video.temporal_layers_count=3` 不会作为输出的活跃属性保留，而是记录在 provenance 中，避免错误描述单层输出。

## v1.8 输出模式

| 模式 | 编码器 | 输出文件名 | 定位 |
|---|---|---|---|
| 默认 | x265 `CRF 8`, medium | `*_LR_CRF8_archive.mp4` | 长期档案，画质优先 |
| 实验 | Apple VideoToolbox `Q65` | `*_LR_VT_Q65_archive.mp4` | 速度和体积优先 |

在参考片段上的客观比较：x265 CRF 8 为 PSNR 55.83 dB / SSIM 0.998472；VideoToolbox Q65 为 PSNR 47.93 dB / SSIM 0.993229。VideoToolbox 使用苹果媒体引擎，但解码、像素转换、封装和验证仍会占用 CPU。

## 每个文件的安全流程

1. 输入先做严格指纹检查；不匹配则拒绝。
2. 在原片旁创建隐藏的临时输出。
3. 完成视频编码、Dolby Vision 注入、AAC/EIS 恢复和 MP4 封装。
4. 对临时输出逐项复检。
5. 只有全部通过才原子重命名为正式输出。

输出复检覆盖：视频参数和方向、帧数与 PTS、AAC/EIS 逐包哈希、Dolby Vision 配置和 RPU、单时间层语法、完整解码、MP4/UUID/拍摄元数据以及 provenance。失败时不会覆盖原片或已有输出，也不会留下正式文件。

## 系统要求与首次安装

- Apple Silicon Mac；
- macOS 14 或更新版本；
- [Homebrew](https://brew.sh/)；
- 大约 1 GB 可用空间用于依赖和转换临时文件，实际转换还需要足够的输出空间。

Release 不捆绑 FFmpeg、PyAV 或 dovi_tool。解压后双击 `install_dependencies.command`。它会通过官方包渠道执行：

```bash
brew install ffmpeg python@3.12 dovi_tool
```

并在以下专用虚拟环境安装固定版本 PyAV 18.1.0：

```text
~/Library/Application Support/VivoLightroomArchiveConverter/venv
```

脚本不会安装 Homebrew 本身。如果没有 Homebrew，请先按照 [brew.sh](https://brew.sh/) 的官方说明安装。App 启动时会检查全部依赖；缺少任何一项时禁止转换并给出明确提示。

### 为什么不把 FFmpeg 直接塞进 App

- FFmpeg 的许可取决于具体构建选项，可能是 LGPL 或 GPL；
- Homebrew 的 FFmpeg 可独立接收安全更新和 codec 修复；
- 避免 Release 重复携带 PyAV wheel 中的一整套 FFmpeg 动态库；
- 用户可以清楚审计实际调用的工具和版本。

详细版本、许可证和上游链接见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 使用

1. 将 App 移到“应用程序”文件夹并打开。
2. 拖入一个或多个原始 MP4，或点击“选择视频…”。
3. 等待每个文件完成输入检查。
4. 保持默认 x265，或主动勾选实验性的 VideoToolbox 模式。
5. 点击“转换全部合格项”。
6. 表格显示“完成并通过复检”后，再导入 Lightroom。

输出放在原片旁边。工具永不覆盖原片或同名输出。

本 Release 使用 ad-hoc 签名，未使用 Apple Developer ID 公证。首次打开可能需要在 Finder 中右键 App，选择“打开”，再确认一次。只有从本仓库 Release 下载且校验 SHA-256 后才应放行。

## 从源码构建

先安装 Xcode Command Line Tools，然后运行：

```bash
./build_app.sh
```

构建结果为 `build/Vivo Lightroom Archive Converter.app`。构建过程只编译 Objective-C/AppKit 前端并复制 Python 引擎源码，不下载或嵌入运行依赖。

## 项目结构

```text
AppKit/main.m                  macOS GUI、拖放与批量队列
Engine/converter_engine.py    输入审计和转换编排
Engine/mux_exact.py           视频 PTS 与原始 AAC 精确复用
Engine/inject_eis.py          EIS metadata 轨道复制
Engine/finalize_mp4.py        MP4、方向与拍摄元数据恢复
Engine/validate_output.py     独立输出复检
Engine/append_provenance.py   来源 SHA-256 与转换记录
Resources/                    Info.plist 和图标
```

## 限制

- 目前只在 README 所述的 Vivo X200 Ultra 录制结构上验证通过；
- 输入即使可以正常播放，只要结构指纹不同也会拒绝；
- 视频必须重新编码，因此不可能与原片逐像素完全相同；
- 保留的 Dolby Vision RPU 来自原片，但会作用于重新编码后的基础层；
- VideoToolbox Q65 是实验选项，长期档案推荐 x265 CRF 8；
- Release 目前仅构建和测试 Apple Silicon。

## 隐私

所有媒体处理均在本机完成。工具不会上传视频、GPS、元数据或哈希。网络仅在用户运行依赖安装脚本时由 Homebrew/PyPI 下载公开软件包。

## 许可证与声明

项目代码采用 [MIT License](LICENSE)。第三方依赖遵循各自许可证。

本项目与 Vivo、Adobe、Lightroom、Dolby、Apple、FFmpeg、PyAV 或 dovi_tool 的作者没有隶属或背书关系。Dolby Vision、Lightroom 等名称仅用于描述兼容性。
