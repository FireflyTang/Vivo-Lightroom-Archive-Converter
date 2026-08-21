# Third-party dependencies

The v1.8 application bundle does not redistribute the following tools or libraries. They are installed separately by the user through Homebrew and PyPI.

| Dependency | Tested version | Purpose | Upstream | License |
|---|---:|---|---|---|
| FFmpeg / ffprobe | 9.0.1 | HEVC encode/decode, probing and bitstream filters | <https://ffmpeg.org/> | LGPL-2.1-or-later; GPL-2.0-or-later when GPL components are enabled |
| Python | 3.12 | Python conversion engine | <https://www.python.org/> | Python Software Foundation License |
| PyAV | 18.1.0 | Packet-level MP4 muxing | <https://pyav.org/> | BSD 3-Clause-style license |
| dovi_tool | 2.3.3 | Dolby Vision RPU extraction and injection | <https://github.com/quietvoid/dovi_tool> | MIT |
| Homebrew | current | Dependency installation | <https://brew.sh/> | BSD 2-Clause License |

The exact FFmpeg license applicable on a machine depends on the Homebrew formula and enabled codec libraries. Run `ffmpeg -version` to inspect its configuration and consult <https://ffmpeg.org/legal.html>.

This notice is informational and is not legal advice. Each dependency remains the property of its respective copyright holders.
