# Vivo Lightroom Archive Converter v1.9.2

这是 v1.9.1 的输出复检修复版本。视频编码、MP4封装、画质参数、元信息保存和准入规则没有改变。

## 修复内容

x265 CRF 8可能生成大于FFprobe默认5 MiB探测预算的首个HEVC访问单元。当第一个AAC包位于其后时，输出虽然包含正确的AAC-LC配置和原始AAC包，FFprobe仍可能暂时把profile报告为unknown，导致App误报“输出AAC profile与原片不一致”。

v1.9.2将独立验证器的探测预算提高到256 MiB，并保留以下全部严格检查：

- AAC codec、profile、采样率、声道布局与时间基；
- 每个AAC包的PTS、DTS、duration、size、flags；
- 每个AAC压缩包payload的SHA-256；
- AAC轨道时间刻度、时长、语言和可见元数据。

## 实际复现验证

`video_20260126_125450.mp4` 的CRF 8 medium输出中，第一个AAC包位于5,571,150字节：默认5 MiB探测时profile为unknown，10 MiB及以上探测时稳定识别为LC。修复后的完整验证结果：

- 502个视频帧一致；
- 392个AAC包逐包一致；
- 503个EIS包逐包一致；
- PSNR 53.55 dB / SSIM 0.998336；
- 单时间层、元信息、完整解码和来源哈希全部通过。

依赖和已验证输入范围与v1.9.1相同。
