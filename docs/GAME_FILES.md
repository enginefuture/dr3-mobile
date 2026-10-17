# Game files policy / 游戏文件政策

**Support the original game. Buy a legitimate copy. Bring your own game files.**

**支持正版，请购买正版游戏，自行准备自己的游戏文件。**

This project publishes compatibility-layer source, synthetic tests and tutorials only. We do not provide, host, link to, or accept NSP, XCI, NSZ, NCA, keys, tickets, game executables, extracted resources, original or translated game shaders, or packages containing game content. Prepare your own files from a legally owned copy where permitted. Ownership does not promise that every extraction or use is permitted in every jurisdiction.

本项目仅发布兼容层源码、合成测试和教程。**不提供、不托管、不链接、不接受 NSP/XCI/NSZ、NCA、密钥、票据、游戏程序、提取资源、原始或翻译后的游戏着色器，以及含游戏内容的安装包。** 不提供游戏下载、游戏文件分享或他人的密钥。

## Local inputs / 本地输入

Use your own base game, the update matching the locked 2.7.7.92380 fingerprint, and any language DLC you own. Extraction takes explicit caller-supplied paths. Keep keysets outside the public checkout or under ignored `work/`. The native runtime does not need prod.keys. No emulator account or save is required.

自行准备基础游戏、匹配 2.7.7.92380 指纹的更新及自己拥有的语言包。工具只读取显式提供的路径；原生运行时不需要 prod.keys。不要向维护者发送密钥、游戏文件或个人存档。

## Never upload / 禁止上传

- Distribution files: NSP/NSZ/XCI/XCZ/NCA, tickets and certificates.
- Executable data: NSO/ExeFS, decompressed or rewritten images and generated embedded-image assembly.
- Resources: RomFS, CPK/PAK, textures, icons extracted from the game, fonts, audio and videos.
- Shaders: captures, SHD, control/code blobs, translated SPIR-V/MSL, metallibs and generated per-game cache/reflection tables.
- Personal data: credentials, keys, provisioning/signing material, saves and complete device logs.
- Any App/IPA/archive containing those files.

These rules apply to Git history, LFS, Issues, PRs, Releases, Actions artifacts and caches. 本规则同样适用于历史、LFS、Issue/PR 附件、Release 和 CI 产物。

**A small IPA is not automatically distributable.** The local iOS app embeds rewritten game modules and shaders even when RomFS stays in Documents. The local Mac app also contains generated game content. Neither package is published here. 构建后的 App/IPA 即使没有 NSP 或 RomFS，仍包含游戏程序和着色器，不可作为本项目公开下载。

The generic MIT touch-control socket artwork is the single reviewed binary source asset, pinned by SHA-256 and accompanied by its upstream license/provenance. It is not the extracted game icon. Version fingerprints, ABI names and bounded instruction-match constants are documented in [DERIVED.md](DERIVED.md).

Before publishing, review and stage source only, then run `python3 tools/audit_public.py --all-history`. The audit reads actual Git blobs, checks paths, binary signatures and credential patterns, and rejects unchecked LFS pointers. It cannot establish the legal provenance of every byte; source review is still required.

This independent community project is not an official port and is not affiliated with or endorsed by Blizzard Entertainment or Nintendo. Game content and trademarks belong to their owners. The MIT source license grants no game rights.
