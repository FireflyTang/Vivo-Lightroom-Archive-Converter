# Vivo Lightroom Archive Converter v1.9.4

本版本只优化编码后的封装与记录步骤，不改变x265参数、HEVC画面、Dolby Vision RPU、音频、EIS、时间戳、元信息或输出复检标准。

## 性能改进

- 将逐字节Python Annex-B扫描替换为底层原生块查找；
- 写入provenance时不再无意义地完整复制一次成品；
- 实时日志记录每个阶段的准确耗时和成功/失败状态。

在1.1 GB真实HEVC中间码流上的完整PTS/AAC重建测试中，旧版约需343秒，新版需5.34秒；两份输出MP4的SHA-256相同且逐字节完全一致。64 MiB NAL边界测试中，扫描器本身快约124倍，识别出的NAL数量、总字节数和SHA-256完全一致。

## 端到端验证

- 4K60 SDR 8-bit：502帧、392个AAC包、503个EIS包全部通过，PSNR 53.55 dB / SSIM 0.998336；
- 4K60 HLG Dolby Vision 8.4 10-bit：96帧、原始dvvC和逐帧RPU全部一致，PSNR 59.53 dB / SSIM 0.999147；
- 方向、GPS、UUID、udta、movie metadata、可见元数据、时间刻度、PTS和单时间层检查保持不变。
