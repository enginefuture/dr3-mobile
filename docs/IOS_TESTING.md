# iOS 构建与真机验收

更新于 2026-10-18（Asia/Shanghai）。最低工程目标 iOS 26，开发工具链 Xcode/SDK 27；最低版本不等于所有设备兼容。

## 构建与签名

详见[构建教程](BUILD.md)。本地生成 iPhoneOS ARM64 宿主、独立 iPhoneOS Metal 库和 UIKit 外壳；不混用 Mac metallib。生成目录 `platform/ios/Gen/`、构建输出和真机记录均为私有，不公开发布。App 包含重写后的游戏模块与着色器，即使 RomFS 放在 Documents 也不可作为公开 IPA 下载。

```sh
.venv/bin/python tools/build_ios_shaders.py
.venv/bin/python tools/build_ios.py --cpu apple-a17 --sign --team-id YOUR_TEAM_ID --device YOUR_DEVICE_UDID
```

`--cpu apple-a17` 用于 iPhone 15 Pro/A17 Pro；默认 `apple-a18` 用于本次较新设备构建。记录实际 CPU，避免把 A18 专用指令的宿主当作 A17 兼容包。按自己的账号签名；本仓库不提供证书、私钥或描述文件。

签名及 `embedded.mobileprovision` 均需具有 `com.apple.developer.kernel.extended-virtual-addressing` 和 `com.apple.developer.kernel.increased-memory-limit`。实际验证使用支持这些能力的公司开发团队；免费个人团队未能签发本次所需权限。设备必须注册在有效描述文件中，开启开发者模式、配对信任并解锁。8 GiB 虚拟空间与 4 GiB alias 是地址预留，不等于驻留内存；权限检查也不能替代真机分配测试。

## 资源与存档

启动前逐项核对资源路径、类型与长度；缺失或部分传输不会启动 guest。实测私有清单包含 52 个文件、22,754,168,801 字节，分为 Documents/romfs 与 Documents/aoc。已完成的设备回读核对是类型/长度检查，不声称对远端全部资源计算内容哈希。本机原始 CPK 全量解码/CRC 另有私有审计记录。

升级前备份已提交存档，覆盖安装后再次比对；不要通过卸载更新。iPhone Air 更新时 4 个存档文件的回读哈希保持一致；iPhone 15 Pro 为首次安装，未导入其他设备的个人存档。签名团队、UDID、设备名、完整日志及资源清单只保存在被忽略的 `work/` 中。

## 已实际验证

| 设备 | 验证范围 |
|---|---|
| iPhone Air，A19 Pro GPU，iOS 27.2 | 原生开场、进入城镇；用户确认触摸、有声音和修正后的真宽屏；与 Mac 加入同一队伍并显示双方角色 |
| iPhone 15 Pro，A17 Pro，iOS 27.2 | 专用 CPU 编译、有效开发签名、USB 首次安装、完整资源检查、启动及进程存活；尚未验证游戏操作、声音或帧率 |

开场样本曾观测约 59.98 FPS、frame p50/p95 16.67/16.93 ms、GPU 2.46/2.77 ms、footprint 1377 MiB。这是特定设备的开场动画样本，不是城镇、战斗或持续温控基准。声音后来由用户确认可听；未通过运行时调试器修改音频，不能把静音模式认定为唯一根因。

UIKit 触摸与实体输入分别发布；物理后端有死区、热插拔、后台抑制、恢复重读和未消费边沿清除。CoreHaptics 近似映射的真实输出、六轴及更多手柄仍需硬件验证。启动菜单可选 HUD、MetalFX Spatial、正常/宽屏、本地 Wi-Fi；宽屏纹理查询的旧 0.8 级联矩形已修正，用户确认画面恢复，不能据此宣称所有相机和菜单通过。

USB 安装时同时确认 UDID 和 CoreDevice `transportType=wired`，避免误选仍在线的无线设备。旧版 screenshotr 服务在 iPhone 15 Pro 所用系统上不可用；此次仅以日志及进程验证启动，不声称截图验收。

## 后续验收

1. 每台设备分别确认中文、触摸/实体手柄、可听音频、保存重载与前后台生命周期。
2. 原蓝灯位置、切图/传送、战斗、死亡复活、装备/背包、首领/过场及长期内存/温控逐项检查。
3. 帧率按同设备、同场景、前台和相同开关测量；HUD 有开销，不能用开场样本代替持续游戏性能。
4. 局域网继续验证长时间同步、战斗/掉落/换场景、反向 host、四人、断线和后台重建，见 [LAN_MULTIPLAYER.md](LAN_MULTIPLAYER.md)。Mesh 尚未实现，见 [契约](XMESH_LAN_CONTRACT.md)。

公开报告只分享最小脱敏摘要，不上传原始运行目录、个人存档、设备标识或签名内容。
