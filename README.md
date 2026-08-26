# Vivo Lightroom Archive Converter

一个面向 Vivo X200 Ultra 特定 HEVC 录像结构的 macOS 档案转换工具。原片可正常播放和解码，但其三时间子层 HEVC 码流无法被 Lightroom Classic 的 Adobe MediaCore 打开。本工具将视频规范化为单时间层 HEVC，同时尽可能保持画面规格、时间、音频、EIS、Dolby Vision 与拍摄元信息。

> 这不是通用视频转换器。目前只在 Vivo X200 Ultra 上验证。无法证明安全处理的设备、轨道、编码或元信息结构会被拒绝，不会猜测性转换。

## v1.9 已验证输入

v1.9 对 86 个无法导入 Lightroom 的 Vivo X200 Ultra 原片做了完整只读盘点，支持以下三种档案：

| 档案 | 视频 | 色彩 | Dolby Vision |
|---|---|---|---|
| 1080p30 SDR | HEVC Main、8-bit、4:2:0 | BT.709 limited | 无 |
| 4K60 SDR | HEVC Main、8-bit、4:2:0 | BT.709 limited | 无 |
| 4K60 HLG/DV | HEVC Main 10、10-bit、4:2:0 | BT.2020 HLG limited | Profile 8.4 |

三类原片都必须具有 `hvc1` 视频、AAC-LC 48 kHz 双声道、Vivo `mett` EIS 数据轨，以及声明三个 temporal sub-layers 的 VPS/SPS。支持原片的 0°、90°、180°和270°正交显示矩阵；GPS可以存在或缺失。

## 为什么必须转换视频

这些原片的共同特征是：

```text
vps_max_sub_layers_minus1 = 2
sps_max_sub_layers_minus1 = 2
```

也就是声明三个 HEVC 时间子层。QuickTime 和 FFmpeg 可以正常处理，但已测试的 Lightroom Classic 版本在打开阶段失败。重封装、去除 Dolby Vision、修改时间戳或只保留基础层都不能解决；经过边界实验，Lightroom 可以接受同等画面规格和元信息组合，但 HEVC 必须重新编码成正常的单时间层码流。

## 未知元信息安全规则

“不认识”不等于删除。v1.9 为每个输入建立元信息账本：

- 边界独立的未知顶层 UUID、`udta` 和 movie metadata 项按不透明字节保存；
- AAC 和 EIS 的压缩包、内容与时间逐包保存；
- 与新 MP4/HEVC 结构有关的时长、偏移、参数集和单层声明按语义重建；
- 原片的活动 `com.android.video.temporal_layers_count=3` 值必须移除，避免错误描述单层输出，原值写入 provenance；
- 未知且可能引用原始帧号、sample、GOP、轨道或字节偏移的结构会导致拒绝。

原片没有 GPS 时，输出同样没有 GPS；工具不会虚构空位置。Vivo 私有 UUID 不再要求固定字段集合，而是整个 box 原样复制并在输出端逐字节核验。

## 自适应转换

工具不会把 SDR 升格成 HDR，也不会把 8-bit 升格成10-bit：

- 1080p/4K SDR 保持 HEVC Main、8-bit、BT.709；
- 4K HLG/DV 保持 HEVC Main 10、10-bit、BT.2020 HLG；
- 保持原分辨率、帧数、显示 PTS集合和显示矩阵；
- Dolby Vision 仅在原片存在时逐帧重新注入原始 RPU，并恢复原始 `dvvC`；
- 不做缩放、像素旋转、帧率转换、tone mapping 或 SDR/HDR互转。

| 模式 | 编码器 | 输出文件名 | 定位 |
|---|---|---|---|
| 默认 | x265 `CRF 8`, medium | `*_LR_CRF8_archive.mp4` | 长期档案，画质优先 |
| 实验 | Apple VideoToolbox `Q65` | `*_LR_VT_Q65_archive.mp4` | 速度和体积优先 |

在本次代表样片上，CPU CRF 8 的原生色彩域抽样结果为 PSNR 52.89–59.17 dB、SSIM 0.997634–0.999142；VideoToolbox样片为 PSNR 43.96–52.01 dB、SSIM 0.988443–0.995377。指标随内容变化，仅用于回归和发现错误，不代表所有视频的固定结果。

## 每个输出的独立复检

临时输出必须全部通过以下检查才会原子重命名为正式文件：

1. 视频 codec/profile、分辨率、位深、色彩、range和时间基与原片一致；
2. 显示矩阵、轨道时间刻度、时长、语言和 EIS样本描述一致；
3. 视频帧数与完整显示 PTS 集合一致；
4. AAC 和 EIS 的 packet 属性与 payload SHA-256 逐包一致；
5. 所有源顶层 UUID、`udta`、GPS和未知独立元信息通过字节级账本；
6. SDR 的 Dolby Vision 存在性保持为无；HDR/DV 的配置与逐帧 RPU逐字节一致；
7. 输出 VPS/SPS 声明一层，并扫描完整 HEVC码流确认所有 NAL 的 `temporal_id=0`；
8. 全部可见容器和轨道元数据逐字段一致；
9. 在不旋转、不缩放、不 tone map 的原生色彩域做 PSNR/SSIM抽样；
10. 完整解码/读取所有输出轨道；
11. 独立复算原片 SHA-256、大小、文件修改时间与 provenance；
12. 任一检查失败时不留下正式输出，也不覆盖原片或已有文件。

测试脚本还会在输出副本中分别篡改未知 UUID、方向矩阵、AAC包、EIS包和 temporal-id，确认核验器能针对每种损坏拒绝通过。

## 大文件与批量处理

v1.9 将 NAL、AAC、EIS、MP4 media data、哈希和最终写入改成流式处理；不再把整部视频或全部压缩包一次性装入内存。转换仍需要同时容纳编码中间文件和最终输出的磁盘空间。原目录中已盘点到 6.55 GB单文件，因此开始批量转换前应预留明显高于原片总大小的空间。

## 系统要求与依赖

- Apple Silicon Mac；
- macOS 14 或更新版本；
- [Homebrew](https://brew.sh/)；
- FFmpeg、Python 3.12、PyAV 18.1.0；
- `dovi_tool`（只有 Dolby Vision输入在转换时需要，但安装脚本统一安装）。

Release 不捆绑第三方运行库。解压后双击 `install_dependencies.command`，脚本执行：

```bash
brew install ffmpeg python@3.12 dovi_tool
```

并在下面的专用虚拟环境安装固定版本 PyAV：

```text
~/Library/Application Support/VivoLightroomArchiveConverter/venv
```

App 启动时检查依赖。详细版本、许可证和上游链接见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 使用

1. 将 App 移到“应用程序”文件夹并打开；
2. 拖入一个或多个原始 MP4，或使用“选择视频…”；
3. 查看每个文件的档案分类、方向、HDR/DV、EIS、拍摄字段和元信息安全账本；
4. 等待检查完成；只有合格原片进入转换队列；
5. 使用默认 x265，或主动选择实验性的 VideoToolbox；
6. 点击“转换全部合格项”；
7. 只有显示“完成并通过复检”的输出才应导入 Lightroom。

输出放在原片旁边。工具不会上传视频、GPS、元数据或哈希。

本 Release 使用 ad-hoc 签名，未使用 Apple Developer ID 公证。首次打开可能需要在 Finder 中右键 App，选择“打开”。

## 从源码构建与测试

```bash
./build_app.sh
python3 -m py_compile Engine/*.py Tests/*.py
```

使用已有的已验证原片与输出运行破坏性副本测试：

```bash
python3 Tests/negative_validation.py SOURCE.mp4 VERIFIED_OUTPUT.mp4
```

测试只修改临时副本。构建结果位于 `build/Vivo Lightroom Archive Converter.app`。

## 项目结构

```text
AppKit/main.m                  macOS GUI、拖放与批量队列
Engine/converter_engine.py    输入分类、安全账本和转换编排
Engine/mux_exact.py           流式恢复视频 PTS 与原始 AAC
Engine/inject_eis.py          流式复制 EIS metadata 轨道
Engine/finalize_mp4.py        方向、拍摄信息与未知独立元信息恢复
Engine/validate_output.py     独立输出复检与画质抽样
Engine/append_provenance.py   来源 SHA-256 与必要变化记录
Tests/                        反向篡改回归测试
```

## 限制与声明

- 目前只在 Vivo X200 Ultra 和上述三种档案上验证；
- 视频必须重新编码，不可能与原片逐像素完全相同；
- Dolby Vision RPU来自原片，但作用于重新编码后的基础层；
- VideoToolbox Q65是实验选项，长期档案默认推荐 x265 CRF 8；
- Lightroom兼容性结论来自实际边界测试，不代表 Adobe 的官方完整规格；
- 本项目与 Vivo、Adobe、Dolby、Apple、FFmpeg、PyAV 或 dovi_tool 的作者没有隶属或背书关系。

项目代码采用 [MIT License](LICENSE)。第三方依赖遵循各自许可证。
