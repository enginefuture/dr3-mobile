# 实体手柄震动与六轴边界

2026-10-17。此实现不改变已经测试的按键、位置映射或摇杆合并。macOS 与 iOS 共用 `native/controller_effects.m`，通过 GameController 的真实 `GCDeviceHaptics` 和 CoreHaptics 输出。

## 原始 D3 使用与 ABI

目标模块仍为已经核验的 D3 2.7.7 SDK 8.2。`main` 直接导入四个震动接口：`GetVibrationDeviceHandles`、`InitializeVibrationDevice`、`GetVibrationDeviceInfo`、`SendVibrationValue`；另直接导入四个六轴接口：`GetSixAxisSensorHandles`、`StartSixAxisSensor`、`StopSixAxisSensor`、`GetSixAxisSensorStates`。导入存在证明代码依赖，不证明当前场景已执行。

原 SDK 反汇编核对：

- `GetVibrationDeviceHandles`：`sdk+0x2532c0`，转入 detail 实现。
- detail `GetVibrationDeviceHandles`：`sdk+0x248ef0`。FullKey 的低字节为 **3**，Handheld 为 **4**，player 位于 8..15，第二设备位于 16..23；设备句柄每项 4 字节。这是此 SDK 的真实编码，不能套用别的库的内部 style index 0/1。
- `GetVibrationDeviceInfo` detail：`sdk+0x248a30`，成功时复制 8 字节结果。
- `SendVibrationValue`：`sdk+0x253470`，detail 为 `sdk+0x248ad0`。
- 振动值为 `{amp_low, freq_low, amp_high, freq_high}` 四个 float，大小 16 字节；幅度归一化，频率以 Hz 表示。与 [libnx 的公开 HID ABI](https://github.com/switchbrew/libnx/blob/master/nx/include/switch/services/hid.h) 交叉核对。

私有证据在 `work/audit/controller-effects-abi.json`，包含精确 SDK 摘要、导入列表与上述函数指令。

## 已实现的震动路径

只有真实连接的 extended controller 提供非空 `haptics`，并能创建实际 locality 的 engine，才发布能力。优先独立左/右 handle；如果只有 Default locality，则只提供一个合并设备，位置为未知，不伪造两个独立马达。无能力时返回 0 个句柄。

`hle_hid.c` 在原 SDK 的句柄 ABI 上路由初始化、单条/批量输出、设备信息和已接受命令查询。设备信息的类型 1 表示适配层接受 LRA 风格的幅度/频率命令，不声称物理设备一定使用 LRA 电机。缺少 optional backend 时，旧测试和精简构建仍能链接，能力为 0。

CoreHaptics 没有通用的“精确设置 HD Rumble 两个频率”接口。因此采用明确的近似：强度取两个频带的最大幅度，sharpness 由幅度加权的频率对数映射得到。Apple 文档把 [sharpness](https://developer.apple.com/documentation/corehaptics/chhapticeventparameterid/hapticsharpness) 定义为内容相关的频率/过滤/信号处理控制；它不等于硬件频率计。输出保留左右位置、强弱和粗略频率感，不等于原平台的精确 HD 波形。

正常发送只读取原子能力并入队，不同步等待 CoreHaptics。相同命令保持连续 player，不重复启动 engine。NaN/Inf、越界幅度和频率先钳制；归零停止 player。断连、失焦和后台停止输出，generation 拒绝旧连接/旧前台周期中排队的命令。engine reset/stop 会清理 player；失败的 channel 不再作为可用输出发布。

`GetActualVibrationValue` 返回适配层最后成功接受的原命令，停止或不可用时全零；它不是硬件加速度、实际 Hz 或振幅的测量。用户的系统设置和控制器硬件仍可能限制输出，实际手感必须用设备验收。

## 六轴仍未完成，已取消伪句柄

旧路径在没有任何六轴数据源时仍返回两个 handle。现在真实返回 0 handle、0 states，单条状态保持 attributes=0。不会编造静止姿态或伪报连接。

Apple `GCMotion` 能提供 acceleration、gravity、rotationRate、attitude，而且部分设备需显式打开 `sensorsActive`。[Apple 的旋转速率单位是弧度/秒](https://developer.apple.com/documentation/gamecontroller/gcrotationrate)。公开 Switch ABI 有 delta time、sampling、acceleration、angular velocity、angle、direction matrix、attributes，共 0x60 字节。但这还不足以证明不同实体手柄坐标轴、Nintendo angle 累积单位与参考姿态的精确转换。

本轮没有足够的真实设备数据完成坐标校准，所以没有打开传感器或宣称六轴已支持。完整实现仍需原 SDK/实机对照单位、轴向、采样时钟与姿态矩阵，并在真实控制器上验收。iPhone 自身运动传感器不能冒充连接手柄的六轴；如果以后支持机身传感器，应使用明确的独立能力。

## 验证与接入

已通过：

- macOS 与 iPhoneOS SDK 对共享 backend 的语法检查。
- `tests/test_controller_effects.c`：生产 HID 边界与显式软件 sink，覆盖无能力不发布、SDK 8.2 的 FullKey/Handheld 编码、双/单/合并 actuator、批量数据、无效句柄、数值钳制和六轴不可用。
- `tests/test_controller_effects_probe.m`：只查询实际硬件能力和构造 pattern。等待一秒让已连接设备完成框架枚举后，本机观测为 `physical=0 / haptics_capable=0 / motion_capable=0 / capabilities=0`。Apple snapshot 也不提供 haptics；因此没有用 snapshot 伪造震动支持。

**未验证：真实硬件振动、左右分离手感、设备断连/重连时的真实波形、iPhone 运行以及六轴。** 被动探针没有启动 engine 或输出振动。

构建应把 `native/controller_effects.m/.h` 同步到 host，并将 `.m` 加入 macOS/iOS 目标，链接 CoreHaptics（原本的 GameController/Foundation 继续保留）。单纯编译 HID 的 weak optional 引用并不等于把 backend 接入了成品。现有按键 adapter 和 iOS 虚拟按键前端没有因此更改。

```sh
clang -O1 -Wall -Wno-unused-function -Ithird_party/nxnative/dm/host/gen/01001B300B9BE000 tests/test_controller_effects.c -o work/test-controller-effects
work/test-controller-effects
clang -O1 -Wall -fobjc-arc tests/test_controller_effects_probe.m native/controller_effects.m -framework GameController -framework CoreHaptics -framework Foundation -o work/test-controller-effects-probe
work/test-controller-effects-probe
xcrun -sdk iphoneos clang -fsyntax-only -target arm64-apple-ios26.0 -fobjc-arc -Wall native/controller_effects.m
```
