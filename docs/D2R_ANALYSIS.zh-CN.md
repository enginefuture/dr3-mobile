# D2R 源码分析与 D3 复用边界

分析日期：2026-10-17。参考 `../ns2mac/docs/NSP_NATIVE_PORTING_GUIDE.md`，D2R 源码提交 `21cf97b91823111ead237858ea79929afacf71a5`。现有目录实际名为 d2r-mobile。

## 执行链

1. `dm/tools/patch_nso.py` 解压 NSO，按指令修改 x18、TLS、SVC 和计时寄存器访问，输出映像、布局、门和修改点表；CUTS/OBS 按 Build ID 登记。
2. `dm/host/loader.c::load_modules` 先读全部布局，再映射、解析动态表、注册门，最后统一跨模块重定位和检查强制接管。
3. `dm/host/main.c::guest_main` 按 `_init_libc0 → nnosInitialize → _init_libc1 → nninitInitializeSdkModule → nninitStartup → _init_libc2 → DT_INIT/init_array → nnMain` 启动。
4. `entry.S → hle.c::gate_dispatch → hle_svc.c / hle_thread.c` 适配内核行为；SDK 的普通实现继续原生执行。
5. HLE/HLE_FORCE 在符号解析时适配文件、账户、输入、音频等服务。D2R 的未知导入桩会记名并返回零，这不能作为新游戏的成功实现。
6. `gfx/nvn/hle_nvn.c` 接管 nvnBootstrapLoader，记录命令；`nvn_mtl.m` 在 Metal 上回放；GPU 完成才推进同步状态。
7. 原始 Maxwell shader 离线经 Ryujinx、SPIRV-Cross、Metal 编译器生成库与反射；运行时按控制段键查找，并检查翻译链版本。

## 可以复用

- NSO 改写模型、宿主门、线程局部状态、装载与跨模块符号解析。
- Horizon HLE 的服务适配模式和 NVN 记录/回放分层。
- LLVM 结构检查、Unicorn 等价和变异负对照；它们不能证明真实独占监视器或并发语义。
- macOS 前端、原始帧抓取、崩溃寄存器与线程日志。

## 必须重新调查

- D3 的模块顺序、完整 Build ID/SHA、SDK/NVN 版本、对象 ABI、内存布局、SVC 和服务使用面。
- D3 的资源包、shader 容器、driver constant 布局、影片、语言包和存档。
- D2R 的 shader_map/facts、初始化预热清单、内嵌 shader 和游戏函数地址都不能当成 D3 数据。

## 不能直接继承

D2R 的 main.c 存档节流与随机种子、hle_oe.c 渲染比例、hle_time.c 固定返回地址、hle_fs.c 预置仓库与触屏默认值，以及 dm_cursor/world/vault/rift 等功能依赖 D2R 地址或文件格式。Makefile 还要求从 D2R RomFS 生成物品/经验表，直接改项目名无法移植 D3。

本项目因此使用手册固定的 nxnative `9579030e5b1f0443c12b7376559560915b6d4c4b` 多标题分支作为宿主基础，保留其 D2R 来源和许可证。所有 D3 常量进入独立 profile；程序与资源保持在被忽略的 work 中。先测原始 macOS 图形配置，再考虑 iOS 或画面优化。
