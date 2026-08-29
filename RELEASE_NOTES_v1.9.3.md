# Vivo Lightroom Archive Converter v1.9.3

本版本修复一种发生在画面编码完成后的 MP4 收尾错误。

部分较大的 PyAV 中间文件不会包含可选的顶层 `free` box。旧版在移除编码器标记后，仍假定这个 box 必然存在，因此以 `StopIteration` 失败。v1.9.3会把被移除标记占用的相同字节原位补成标准 `free` box，使 `mdat` 位置和所有媒体 sample offset 均保持不变。

此修复不跳过任何元信息，也不放宽输出复检。AAC、EIS、显示矩阵、UUID、`udta`/GPS、movie metadata、视频帧数和显示 PTS 仍按原有严格标准核验。
