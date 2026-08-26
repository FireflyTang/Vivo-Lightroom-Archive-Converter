# v1.9 — 自适应档案与元信息安全账本

v1.9 不再要求输入与单个 4K60 Main10 HLG/Dolby Vision样片逐字节相同。对 `/Volumes/Backup/无法导入` 中 86 个 Vivo X200 Ultra原片的只读盘点表明，它们共享 Lightroom 不兼容的三时间子层 HEVC结构，但分为三种合法拍摄档案：

- 1080p30、HEVC Main、8-bit、BT.709 SDR；
- 4K60、HEVC Main、8-bit、BT.709 SDR；
- 4K60、HEVC Main 10、10-bit、BT.2020 HLG、Dolby Vision Profile 8.4。

本版会根据原片自适应保持位深、色彩、分辨率、显示 PTS和方向；SDR不添加HDR，Dolby Vision仅在原片存在时恢复原始配置与逐帧 RPU。

## 元信息处理

- 顶层 UUID、`udta`、GPS、Vivo私有字段和可独立搬运的未知 movie metadata按不透明字节保存；
- 缺失 GPS 保持缺失，不虚构空值；
- AAC 与 EIS payload和时间逐包不变；
- 活动三时间层值不能继续描述单层输出，因此移入 provenance；
- 无法证明复制后仍然正确的未知结构继续拒绝。

## 输出核验

每个输出在获得正式文件名之前会独立检查视频规格、矩阵、PTS、AAC/EIS逐包哈希、未知元信息账本、Dolby Vision存在性与RPU、完整码流单时间层、可见元数据、原生色彩域PSNR/SSIM、完整解码、原片SHA-256与文件修改时间。

回归测试还会故意修改输出副本的 UUID、方向、AAC、EIS和temporal-id，确认对应检查能够真正拒绝损坏文件。

## 大文件

NAL、AAC、EIS、MP4 media data、哈希和最终输出已改为流式处理，避免旧版对多GB原片的整文件内存占用。

## 依赖

App仍不捆绑 FFmpeg、PyAV 或 dovi_tool。首次使用请运行 `install_dependencies.command`。依赖、许可和安装位置见 README 与 `THIRD_PARTY_NOTICES.md`。
