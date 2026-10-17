# 移植完成度与剩余验收

2026-10-17 最新整合。这里的“通过”只对应列出的证据范围，不代表所有场景或整款游戏已完成。

| 项目 | 当前结论 | 剩余条件 / 入口 |
| --- | --- | --- |
| 模块与资源 | 锁定 main/sdk 身份、重写和独立校验通过；51/51 CPK 解码与存储 CRC 通过，1569 SHD 字节一致 | 资源通过不等于全部游戏行为通过；[ROM_AUDIT.md](ROM_AUDIT.md) |
| 常量转发性能 | 保持开启，原同进程对照证实大幅减少 pass/GPU 时间；整合城镇仍为 56 pass，附件守卫只增加一个边界 | 原蓝灯同位置动态复测、其他复杂场景；[LANTERN_STABILITY.md](LANTERN_STABILITY.md) |
| 程序/命令寿命与同步 | BindProgram 快照、状态恢复、真实 CopyCommands、队列/命令 GPU 等待已实现；两组 64-case GPU 测试通过 | 跨场景及长时间运行；[NVN_COMMAND_LIFETIME.md](NVN_COMMAND_LIFETIME.md) |
| 顶点格式 | 3 个实际失败 PSO 修复，128 个独立预期 GPU channel 通过，9 个布局预编译 | 未遇到的布局及历史 varying/纹理警告仍需实际场景验证；[SHADER_AUDIT.md](SHADER_AUDIT.md) |
| 输入 | Mac 真手柄输入曾到达 guest；Apple snapshot/HID、失焦清零、触摸与物理后端分离通过 | iOS 触摸与实体手柄真机、长按/热插拔；[IOS_TESTING.md](IOS_TESTING.md) |
| 振动 / 六轴 / NFC | 真实能力驱动的近似振动后端已编译并做 ABI/软件测试；六轴转换与 SDK 结构已查证，未宣称有传感器 | 真振动；Joy-Con 传感器、坐标/校准/路由；NFC 尚无原生后端。当前 FullKey/Handheld 不申请该 Joy-Con 摇动路径；[CONTROLLER_EFFECTS.md](CONTROLLER_EFFECTS.md)、[SIXAXIS_ADAPTER.md](SIXAXIS_ADAPTER.md) |
| 保存重载 | 隔离副本装备 → 正常退出提交 → 第二进程重载通过，正式存档未变 | 更多保存/恢复、角色、任务及场景；[SAVE_ROUNDTRIP.md](SAVE_ROUNDTRIP.md) |
| 中文与音频 | 中文菜单/背包已可见、中文资源校验通过；音频队列存在 | 实际声音/中文语音听测、过场及音画同步 |
| Mesh 联机 | 原游戏实际 LDN/socket/NIFM 导入与调用已扫描；现有共享 runtime 能力和缺口已核对 | xmesh 游戏 SDK/数据报与流、控制面房间授权、Admin 游戏权限、DR3 精确 ABI、双机实战均未完成；[XMESH_LAN_CONTRACT.md](XMESH_LAN_CONTRACT.md) |
| iOS 构建与启动 | ARM64 应用及 1993 个 shader 库、公司团队签名、两项内存权限通过；2026-10-18 已安装至 iPhone Air，52 个资源完整传输并核对长度/类型，存档副本回读 SHA 一致；原生开场视频和触摸控件可见，当前动画约 60 FPS | 城镇/战斗、实际触摸、音频听测、生命周期和长时验证待完成；实时 TSV 导出有 CoreDevice 传输限制，暂用原生日志摘要；[IOS_TESTING.md](IOS_TESTING.md) |
| 完整游戏稳定性 | 已测城镇、背包、暂停、装备和正常退出路径无崩溃/红告警 | 五幕、战斗/首领/传送/死亡复活、过场、长时内存与多人会话；不能由静态扫描替代 |

Mesh 使用用户另建的组织，不接入战网。xmesh 与 pingclaw-admin 的具体分工已形成可交接契约；当前没有修改其生产部署、组织、账号或密钥。用户确认团队并连接设备后，本轮推进单机真机启动；缺失的联机及完整游戏验收仍保持未完成。
