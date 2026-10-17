# DR3 Mobile 本地 Wi-Fi 联机实现与验收

2026-10-18。当前已实现原生 LAN 房间发现、认证加入、成员更新，以及游戏实际导入的 LDN/IPv4 socket/NIFM 适配。**独立原生传输测试通过；实际 Mac 建房、iPhone 加入已通过，用户确认同一队伍内能看到双方角色。长时间同步、换场景和反向建房仍待验收。** 测试程序成功不能替代游戏成功，当前也没有 Battle.net、Nintendo 在线服务或 Mesh 联机。

## 1. 适配依据

原始 main Build ID `2607a74f5df7754cc0357b5df7e496931355d8ca000000000000000000000000`。原始模块及导入/直接 BL→PLT 证据保存在私有 `work/audit/xmesh-main-imports.json`，本次原始 main/sdk 指令、镜像 SHA256 和 ABI 推导保存在 `work/audit/lan-native-abi.json`。分析使用原始 AArch64 指令；native Ghidra 后端当时不可用，没有安装工具链或把 SDK 字符串当作调用证明。

| 原始实际调用证据 | 适配语义 |
| --- | --- |
| main `0x85908`、`0xc134b0`，SDK `0x2bd110` | CreateNetwork 三个引用参数；游戏安全模式 **2**、passphrase 长度 **16**、最多 **4** 个节点；保留实际传入值，不硬编码模式 1 |
| main `0xc13b50`、`0xc13ad4`、`0xc13c30` | NetworkInfo 大小 0x480；GetNetworkInfo 第二重载参数为输出、8 项更新数组、数量 8，更新项每项 8 字节；bit 0 加入、bit 1 离开 |
| main `0xc13640`，SDK `0x2bda70` | LDN IPv4 是 host order，游戏随后 InetHtonl；NIFM 的 in_addr 仍是 network order |
| main `0xc081b0`、`0xc08070`、`0xc084d0` | sockaddr 长度 16、family 2；Fcntl guest O_NONBLOCK=0x800；addrinfo 的 ai_addr 在 +32、next 在 +40 |
| SDK `0x2bce90` | ScanFilter 大小 0x60，支持掩码 0x37；匹配 communication ID、session、网络类型、SSID、scene 及指定逻辑 channel |

`lan_native.h` 对 NetworkInfo、NodeInfo、ScanFilter、NetworkConfig 的大小和关键偏移有编译期断言。NetworkInfo 节点在 +0x68，每项 0x40；advertise 长度在 +0x26a、数据在 +0x26c，最多 384 字节。公开 [libnx LDN 头文件](https://raw.githubusercontent.com/switchbrew/libnx/master/nx/include/switch/services/ldn.h) 只作为结构和状态枚举交叉核验，实际项目调用仍以上述原始代码为准。

仅 D3 profile `DM_GAME_PROGRAM_ID=0x01001B300B9BE000` 编译启用新强制 hooks，运行时再次校验 main 的短 Build ID。其他 profile 仍保留原离线实现。原 SDK 地址/字节序纯转换函数保留。HLE 桥使用 host big-stack，避免 CommonCrypto/Foundation/包处理占用游戏可能只有 8KB 的栈。

## 2. 结构与行为

- `third_party/nxnative/dm/host/hle_lan_native.c`：共享 C 房间状态机、原生 UDP 控制、成员租约与原 LDN 数据结构转换。
- `third_party/nxnative/dm/host/hle_lan_socket.c`：独立 guest fd 表、原生 IPv4 UDP/TCP、guest errno/flags/timeval/addrinfo/select/poll 转换。
- `third_party/nxnative/dm/host/hle_lan_hooks.c`：精确 SDK 导入名与参数桥，取代本 profile 原 LDN/socket/NIFM 离线 hooks。
- `native/lan_discovery_apple.m`：NSNetService/NSNetServiceBrowser 的 `_dr3lan._udp.local.` Bonjour 发布及解析，共用于 Mac/iOS；单独 run loop，不操作游戏 UI。

发现使用公开 Bonjour，避免以任意 multicast socket 为前提。iOS 配置需要 `NSBonjourServices=["_dr3lan._udp"]` 和 `NSLocalNetworkUsageDescription`；实际授权失败会记日志、使发现不可用，并撤销已创建的房间。`dr3_lan_supported()` 表示编译进 Bonjour bridge，不能代表用户授权、Wi-Fi 链路可用或游戏已经联机。异步 Bonjour 开始请求也不能作为发布成功证据，应观察 `Bonjour room published` 及真实 scan 结果。

控制 UDP socket 绑定实际 en0/其他可用 en* 的 IPv4，随机端口。Bonjour TXT 带版本、游戏 ID 和实际绑定 IPv4；解析回调再验证本地子网，并发送控制查询；返回 NetworkInfo 还必须校验其 host IPv4 与数据包来源相同。该 TXT 是必要的：本机测试曾发现 DNS-SD 会优先返回与所选接口不同的 link-local 地址，造成“发现了服务但找不到房间”。DNS-SD 地址仍作为附加候选。Bonjour 数据不是可信身份凭据。

控制帧为版本化 `DR3L`：40 字节头（magic/version/type/长度/request/session/instance identity）+ 有界正文 + 32 字节认证位。NetworkInfo 所有多字节字段显式 big endian 编码，不发送原生指针。QUERY/ANNOUNCE 仅提供发现；JOIN/JOINED/ROSTER/HEARTBEAT/LEAVE/DESTROY 使用游戏传入 SecurityConfig 的 passphrase 做 HMAC-SHA256，验证 session、来源控制端点、请求和版本。passphrase 不写日志或证据，实例 ID 和房间 session 随机生成。此机制保持游戏本地房间约定，**不是组织/账号权限系统**；共享游戏口令的本地参与者不具备 Mesh 的独立设备授权。

Host 在有空位、accept policy 允许、名称合法、版本一致、认证通过后分配节点；重复同一端点 JOIN 幂等。4 秒未收到 heartbeat 会移除成员；客户端 4 秒失去 host 返回 station/断连原因。Host destroy、主动退出均释放房间资源并撤销对端数据传输，但保留由客体持有的 BSD fd，供游戏正常 Close/重建；后台与库 finalize 才关闭全部 guest socket。后台停止 Bonjour 并关闭 guest socket，恢复不自动重进旧房间；接口 IPv4 改变会重新初始化控制 socket。成员移除会撤销其已连接数据 socket。

游戏数据是原生 UDP/TCP 直接传输，LDN 节点返回实际 Wi-Fi IPv4；控制流和数据流分离。当前无虚拟 IP/TUN/转发，也不把原生 fd 冒充 guest fd。数据 socket 只允许本地自身和当前房间 roster 对端，外部公网地址返回 EACCES；不提供公网 DNS、NAT 穿透或战网连接。NIFM 的网络可用表示本地链路可用，不承诺互联网服务已实现。

### errno ABI 的原始证据与回归

实际游戏 main `0xc07a80` 在非阻塞 connect 失败时只接受 guest `EINPROGRESS=115`。main `0x1147800` 错误名表的 133 项原始 RELA addend 解出 guest `EWOULDBLOCK=11`、`ENETDOWN=100`、`ECONNREFUSED=111` 等，私有证据为 `work/audit/lan-guest-errno-table.json`。Apple 分别使用 35、50、61、36，不能直接透传。所有原生失败路径现统一按该原表转换，SO_ERROR 返回的内嵌 errno 同样转换；guest SetLastErrno 保留 guest 值，不做二次转换。

独立测试首次误用了宿主 EAGAIN 常量，只能证明本机 socket 行为，漏掉了 guest 编号差异。回归现在断言**固定 guest 数字**：非阻塞 UDP 为 11，非阻塞 TCP 为 115，连接已关闭本地端口后的 SO_ERROR 为 111，禁用网络为 100。已重跑完整 4 项 ASan/UBSan 和 Bonjour 测试通过，12.902 秒。

## 3. 前端与构建接口

稳定 C 接口：

```c
int dr3_lan_supported(void);       // Compiled discovery bridge exists.
int dm_lan_initialize(void);      // SDK LDN/socket Initialize calls this lazily.
void dm_lan_finalize(void);
void dm_lan_suspend(int on);      // Background=1; foreground=0.
```

在 preload 前设置 `DM_DR3_LAN=1/0`，对应启动菜单“本地 Wi-Fi 联机”。默认开启以编译能力为前提。前端无须提前 initialize；不能在每次切回前台自行重建游戏房间。Mac 的 upstream `hle_*.c` wildcard 会包含三个新增 C 文件；Mac/iOS 必须同时纳入 `lan_discovery_apple.m` 并链接 Foundation，新文件需进入 upstream diff patch / iOS source fingerprint。

测试专用变量 `DM_LAN_BIND_IP`、`DM_LAN_PEER=ip:port` 用于独立程序；正式启动应清除。它们不是游戏联机设置或手动输入 Wi-Fi IP 的产品流程。测试不修改网卡别名、系统防火墙、原 ROM、原存档或账户 UID。

## 4. 已完成验证

```sh
DM_LAN_BONJOUR_TEST=1 .venv/bin/python -m unittest discover -s tests -p test_lan_native.py -v
```

2026-10-18：5 项通过，ASan/UBSan，13.789 秒，日志 `work/logs/lan-native-tests.log`：

1. 两独立进程走真实 socket，含场景过滤、错误 passphrase、版本不匹配、满员、重复 JOIN、畸形长度/非法名称、NodeLatestUpdate 数组边界、TCP hello/world/EOF/half-close、UDP ping/pong/peek、select/poll、guest nonblock/errno、禁止公网、主动离开和人数回落。
2. **没有手工 peer 的真实 Bonjour 发现**后完成相同 UDP/TCP 流程，并检查发布回执。
3. `DM_DR3_LAN=0`、开启、后台 socket 清理、恢复、finalize/reinitialize、64 位 timeval timeout roundtrip 和非法 usec 拒绝。
4. 已有成员收到 host destroy，进入 station 并得到断开原因。
5. 直接编译并调用真实 CSRNG forced hook，验证注册导出名与 big-stack 入口，以及 0/1/17/128/4096 字节请求的输出边界；隔离测试不会连接任何游戏服务。

两个进程测试使用现有不同 loopback IPv4；Bonjour 测试 host 绑定本机 en0、client 绑定 loopback。测试没有制造第二个物理设备。若机器没有第二个现有 loopback IPv4，相应测试明确 skip，不会偷偷增加网卡地址。Bonjour 需显式 opt-in，常规测试不会发布服务。

### 首次游戏联机入口崩溃：原 SDK CSRNG 服务

2026-10-18 实际在两端选择本地联机，Mac/iPhone 均在 `LDN Initialize result=0` 后崩溃。原回溯 `sdk+0x18148c/+0x181588 → main+0xbdfd40` 对应 SDK `nn::crypto::GenerateCryptographicallyRandomBytes(void*,size_t)` 首次初始化 csrng，继续调用 `InitializeHipcServiceResolution`/sm: 后触发未实现 SVC 0x1f。原 main 这条路径请求 128 字节；证据和两端日志 SHA256 保存在 `work/audit/lan-csrng-startup-abi.json`。

针对该精确 D3 导出增加 host big-stack 强制接管，使用 Apple `arc4random_buf` 按请求填满输出，不调用 Nintendo IPC，也不使用可选的确定性 replay 随机流。没有把 SM/SVC 一概改成成功。真实 hook 的 ASan/UBSan 边界测试和其余原生 LAN 测试通过。重建后的 Mac 和 iPhone 均实际跨过该入口，日志出现 `CreateNetwork result=0`、Bonjour 发布成功；两端均曾得到 `Scan count=1`。这证明入口崩溃已跨过，尚不代表加入游戏成功。

### 本地模式中的互联网离线提示与空列表

实测游戏切换本地联机后出现“未检测到网络连接”。原 main `0x7ec94..0x7ed1c` 在模式 1 分支主动清零互联网状态缓存，再设置独立 LocalCommunication 标志；因此不能把该短提示或左下角“已断开《暗黑破坏神》网络连接”直接判为 Wi-Fi/LDN 初始化失败。原指令和分析边界见私有 `work/audit/lan-nearby-readiness-analysis.json`。提示最终显示回调尚未完整追踪，不改成虚假的战网在线状态。

本轮 Mac `<Mac LAN IPv4>`、iPhone `<iPhone LAN IPv4>` 已相互解析 Bonjour；日志有实际 `CreateNetwork=0`、`Scan count=1`，但 UI 仍显示“附近没有玩家”，尚无 `Connect` 成功证据。Mac 控制 QUERY 返回 1/4 节点、384 字节 advertise；记录只保存长度和状态，不记录广告前 24 字节传输密钥。先追踪游戏消费 Scan 数据的筛选与刷新路径，不能把同名 Player、复制英雄或固定账户 UID 直接认定为原因。

手机切后台会撤销房间，之后的 Scan=0 与暂停状态应分开记录。前台恢复不会自动重进旧房间；验收时应重新建立本地会话并刷新列表，同时检查两端仍在前台。随后两端统一修复版并重新建房/刷新，用户已确认实际加入并看到双方角色；此前空列表并非固定 UID 过滤的证据。持续同步仍待验收。

### 房间切换不能提前销毁游戏持有的 BSD fd

实际 Mac 选择手机 Player 后，LDN `Connect result=0`，游戏仍立即提示“加入游戏时发生错误”。原 main `0xc13298` 经 vtable `+0x48` 调用 `bdSocket::Close`，随后才 Create/Fcntl/SO_BROADCAST/Bind；适配层此前在 DestroyNetwork 时调用 socket finalize，提前关掉游戏缓存 fd，导致 Close 返回 `EBADF=9`。诊断版实测销毁后 Close=-1/errno9；原指令与 vtable 证据见私有 `work/audit/lan-post-connect-fast-failure.json`。

修复将 LDN 房间生命周期与 BSD fd 所有权分开：断房、成员离开/超时、host destroy 只撤销已连接对端传输，保留 fd 至客体 Close；后台挂起和库 Finalize 仍完整关闭。没有把重复 Close 伪装成功。新回归先在旧后端失败，再在修复后完成真实双进程 AP→station→Connect→Close→Create/Fcntl/Broadcast/Bind→UDP/TCP 流量；后台与 Finalize 旧 fd 必须失效的断言保留。6 项 ASan/UBSan（含真实 Bonjour）于 14.683 秒全部通过，记录 `work/logs/lan-bonjour-isolated-fixed-tests.log`。随后已安装 iOS 同版修复并重试：Mac 建房、iPhone 的 LDN Connect=0，用户确认同一队伍内能看到双方角色。

独立 Bonjour 测试使用单独随机 scene，实际时间期限 8 秒；不能用固定 Scan 次数当等待期限，因为真实游戏房间回应会提前唤醒 Scan。测试发布成功和传输成功分开判断。

### 双端同版实机加入结果（2026-10-18）

Mac runtime `6730bb61d1842996684754342ec7297e9ae4b2e9749153ef62d6a3e6ed9d11d2`；iOS `bea0a70683f47ead5ac3aae7b2ec4b9a29d3e6d6400030e4524eafb3057b14c2`。手机升级前备份并核对 4 个存档文件，升级后 SHA256 完全一致。仅更新 Mac 后，Close/Create/Bind 已成功但加入仍超时；将 iPhone 也更新并重新建房后，用户明确确认“已加入同一队伍，能看到双方角色”。此次实际方向为 **Mac host → iPhone client**，iPhone 日志 `Connect result=0`，并非仅独立测试结果。

私有回执 `work/run/mac-lan-test-20261018/attempt-6-both-fixed-success/summary.json` 保存两端应用 SHA、日志 SHA、用户确认及验收边界。没有修改账户 UID、英雄身份或用户原存档。此结果通过建房、发现、加入和双角色显示，尚未证明 15 分钟同步、战斗/掉落/换场景、四人及反向 host 场景完整通过。退出或切后台后仍需重新建立本地会话。

## 5. 实机验收与剩余边界

已通过 Mac 建房、iPhone 加入和双角色显示。以下其余范围仍须各自取得实际游戏日志/行为，不能由一次加入推定完成：

- Mac 与 iPhone 在允许局域网互访的同一 Wi-Fi，分别启动已包含相同网络代码的构建；首次允许 iOS 本地网络权限。记录实际两端 IPv4、Bonjour 发布/解析、LDN Initialize/Create/Scan/Connect 结果。
- 使用两个独立测试存档/角色进入本地联机。当前已有复制英雄和相同合成账户 UID 的历史，可能触发游戏内部身份冲突；先观察实际协议和拒绝原因，再为**独立副本**安排不同身份，不能直接改用户原存档或宣称已有双人玩家身份。
- 一端建房，另一端通过游戏 Scan 发现并加入；两端 roster/人数正确，移动、战斗、掉落、换场景和至少 15 分钟游玩保持同步。交换 host 角色。
- 拒绝权限、AP 客户隔离、拔 Wi-Fi、切后台/前台、host 退出、client 退出、切 Wi-Fi 后重建、错误版本、满四人时正确失败且单机仍可继续。
- 观察游戏期真实所用 socket options/异步调用和 guest errno。当前强制入口覆盖已确认导入，但不是完整 Horizon BSD 栈或全部 SDK API；IPv6、私有 Scan/whitelist、认证互联网解析明确不支持。未知实际调用需根据 locked SDK/游戏证据扩展，不能无条件返回成功。

原 LDN 一个节点由 IPv4 标识，因此同一物理接口相同 IPv4 的两个游戏实例不会被当作两个不同玩家；独立测试用不同现有 loopback 地址，正式 Mac ↔ iPhone 则应各有不同 Wi-Fi IPv4。当前无 iPhone/macOS 防火墙自动改动；真实链路验证仍会暴露 OS 权限/AP 隔离等环境问题。

Mesh 后续接入应复用 room roster/guest ABI/生命周期边界，但需替换发现与数据寻址/认证，不能将本次 HMAC 和真实 IP 直接宣称为组织 ACL。组织房间需求仍见 [XMESH_LAN_CONTRACT.md](XMESH_LAN_CONTRACT.md)。
