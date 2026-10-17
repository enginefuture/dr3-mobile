# 六轴适配的已证实边界与集成方案

2026-10-17。本轮只增加独立数学 helper/test；没有改变正在冻结的 HID 或 Apple 设备后端，没有向游戏发布虚构姿态。

## 可以立即推进的部分

`native/sixaxis_math.h` 提供显式坐标基参数的向量转换、rad/s → turn/s、累计 turn 积分、四元数到右手主动旋转矩阵，以及 `P R Pᵀ` 换基。输入拒绝 NaN/Inf、零四元数、非正交基和反射；没有“默认 Apple 轴就是 Nintendo 轴”的隐含假设。

Apple 本机公开 `GCMotion.h` 明确加速度单位为 g，角速度为 rad/s、右手规则，total acceleration = gravity + userAcceleration。应使用真实 `.acceleration`，不能只传 `.userAcceleration`。`hasRotationRate` / `hasAttitude` 必须分别检查；API 在缺能力时给出的零速度/单位四元数不代表真实测量。[Apple GCMotion](https://developer.apple.com/documentation/gamecontroller/gcmotion)

本机 Suyu 源的实际输入链将 SDL rad/s 除以 `2π`，之后 `UpdateRotation` 对该值按秒积分，并把 `GetRotations()` 直接写入六轴 rotation；因此该实现的 gyro 是 turn/s、angle 是传感器轴角速度的累计 turn。**angle 不能替换成 Apple Euler pitch/yaw/roll。** 这是实现交叉证据，不冒充 Nintendo 原厂 SDK 的文字规范。私有证据记录具体文件哈希和行号。

## SDK 8.2 的 ABI

| 偏移 | 内容 | 长度 |
| --- | --- | --- |
| `0x00` | delta time，ns | 8 |
| `0x08` | sampling number | 8 |
| `0x10` | acceleration，三个 float | 12 |
| `0x1c` | angular velocity，三个 float | 12 |
| `0x28` | angle，三个 float | 12 |
| `0x34` | direction，3×3 float | 36 |
| `0x58` | attributes：bit 0 connected、bit 1 interpolated | 4 |
| `0x5c` | reserved | 4 |

总长 `0x60`。本地原始 SDK `detail::GetSixAxisSensorStates` 以 `0x60` 步长复制，main 使用相同步长；字段分布由 [libnx 原始定义](https://github.com/switchbrew/libnx/blob/master/nx/include/switch/services/hid.h) 和本地 Suyu `hid_types.h` 交叉。SDK 没有在公开 GetStates wrapper 中执行单位换算。delta time 的 ns 由 Suyu 写入路径交叉支持；D3 消费处按 `1,000,000` 除为内部毫秒。

原始 SDK `detail::GetSixAxisSensorHandle` 在 `0x241220` 证实句柄为 32-bit little-endian：byte 0 是类型，byte 1 是 npad id，byte 2 是 device index，byte 3 保留为零。FullKey/Handheld 的类型为 3/4，device **为 2**；JoyDual 类型 5、左右 device 0/1；JoyLeft 类型 6、device 0；JoyRight 类型 7、device 1。ID 接受 0..7、0x10、0x20。不能照搬震动句柄中的左右编号。独立 helper 有对应编码/严格校验，但不会因此向游戏分配传感器。

## D3 实际消费范围

从原始 main 的动态重定位/PLT 找到 GetHandles/Start/Stop 各一个直接调用，GetStates 五个直接调用，均位于同一个输入更新函数 `0xf7310`。五条读取路径都只用时间、采样序号、加速度和角速度，计算：

```
accelerationDeviation² = ax² + ay² + (az + 1)²
angularSpeed² = gx² + gy² + gz²
```

连续超过阈值后置内部输入标志，符合摇动检测。该函数未读取 angle/direction；这是一项有边界的静态结论，不是对所有间接指针使用的全程序证明。原始采样缓冲仍存于对象中，未宣称其他代码绝不可能访问。

另一个关键限制：`0xf73c4` 在 GetHandles 前测试 `style & 0x1c`，只对 JoyDual/Left/Right 风格分配六轴句柄。正常 FullKey/Handheld 风格不走该分配。因此当前标准手柄/掌机运行没有六轴调用，不能用虚拟姿态补齐覆盖数字，也不应只为触发调用改变正常控制器风格。

## 可以绕过的坐标不确定性

对 D3 的两个标量，gyro 范数在正交换基下不变。若从真实静止测量建立单位重力参考 `g0`，则 `|a-g0|²` 在任何把 `g0` 映射到 `(0,0,-1)` 的正交换基后保持不变。故摇动检测不依赖 yaw、Euler 角或 direction 排列，可以独立完成并验证。helper 的 `dm_motion_d3_metrics` 实现此数学关系，**它不是完整 SixAxisSensorState 编码器**。

该方案仍需真实静止区间来建立参考：不能把任意第一帧视为静止，也不能每帧重新对齐而消除真实倾斜。重力范数接近 1 只是一项必要条件；还需一段时间内的低 gyro、低加速度方差。启动时正在移动应等候有效区间并报告无样本，不能发布伪造姿态。传感器偏置和断连重连后的参考必须重新管理。

完整方向转换不能从字段名猜测。作为警示，[SDL 3.2.0 Apple 实现](https://github.com/libsdl-org/SDL/blob/release-3.2.0/src/joystick/apple/SDL_mfijoystick.m) 对 GCMotion gyro 使用 `(x,z,-y)`，而对 acceleration 使用三轴取负；再结合 Suyu 的 SDL 转换，两个量不能直接推出同一套 Apple→Nintendo 矩阵。这不证明任一实现错误，但足以阻止盲目复用轴符号。

## 后端集成顺序

1. 用**当前输入实际选中的同一个 physical controller**绑定 GCMotion，不单独选第一个有 motion 的设备。检查能力；Start/Stop 引用计数管理 `sensorsActive`，仅在 `sensorsRequireManualActivation` 时控制；失焦/断连停止发布、清空历史和积分参考。不要让回调抢占现有 handler。
2. motion 回调按实际到达时间记录真实样本；单调序号、单调时钟纳秒 delta，最多保留 17 项，GetStates newest-first，只返回实际采集项。重复轮询不能制造新 sampling number；异常时差应丢弃并重置连续积分，不跨后台长间隔外推。
3. 对完整 ABI，明确设备/握持风格的轴基、Apple quaternion 的主动/被动方向、相对参考以及 Nintendo direction 的行/列语义，再用 helper 换基；有独立 gyro 积分作为 angle，不把姿态 Euler 填入 angle。未验证这些部分时保留能力限制，不用 connected+identity 冒充完整六轴。
4. D3 窄路径可先验证真实摇动的两个不变量；若将其接成游戏输入，必须记录这是针对该消费者的适配，不能泛化为完整 HID 六轴支持。iOS 的 CMMotionManager 是另一台设备传感器，只有明确的 handheld 路由才能使用，不能冒充外接手柄运动。

仍需硬件校准/验收：真实控制器型号和握持方式的轴符号、姿态参考、静止偏置、回调频率、Start/Stop/断连重连/后台恢复，以及一次真实摇动触发。无需因此停止 ABI、数学、缓存/生命周期和无设备降级实现，但不能把无设备 fixture 称为完成了这些验收。

## 验证

```
clang -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
  tests/test_sixaxis_math.c -lm -o work/audit/sixaxis/test_sixaxis_math
work/audit/sixaxis/test_sixaxis_math
```

已通过：ABI 偏移、π rad/s→0.5 turn/s、90° X/Z 旋转、归一化四元数、旋转右手叉积、换基协变、累计多圈不回绕、D3 标量不变式，以及非法数据/反射/时间跳变负对照。未启动宿主或设备传感器。

同一纯 C 测试已接入 `make test`，同时检查上述 SDK 句柄和非法类型/side/id/reserved 拒绝；不需要 Metal 或真实控制器。

私有原始证据在 `work/audit/sixaxis/`：导入/调用点 JSON、完整输入函数汇编、SDK GetStates/GetHandles 汇编、下载的 libnx/SDL 定义和来源清单。源文件不包含 ROM 数据。
