# NVN 同步与命令列表寿命

2026-10-17，本轮修复针对实际执行过的 `CommandBufferWaitSync` 空实现，以及 `CopyCommands` 与 `CallCommands` 原先等价的问题。保留常量转发优化；不以 CPU 全队列等待掩盖同步错误。

## 原 SDK 证据决定行为

对锁定的 SDK 8.2 NSO 动态重定位和 `nvnBootstrapLoaderInternal` 的名称/实现表进行了只读解析。SDK 使用去掉 `nvn` 前缀的 516 项排序名称表；将原始 RELATIVE 重定位应用于表指针后，可以确定真正的函数入口，避免仅根据字符串猜测。

- `SyncInitialize` 入口 `0x426c00`：写入设备指针，清空状态及负载。初始状态是 0。
- `SyncWait` 入口 `0x427000`：内部跳表状态 0 直接返回 `FAILED (3)`。旧宿主测试曾假设返回 `TIMEOUT_EXPIRED (2)`；该假设已经纠正。
- `QueueWaitSync` 入口 `0x4273a0` 转到 `0x4272b0`：状态 0 返回 false；不能把尚未围栏的同步对象一律当作已完成。
- `CommandBufferWaitSync` 入口 `0x414660`：把 **sync 对象指针** 写入控制命令，不是在录制时读取围栏数值。录制时尚未围栏、提交前再围栏的顺序必须被支持。
- `CallCommands` / `CopyCommands` 入口分别是 `0x414360` / `0x4143b0`；它们给公共解释/拷贝 helper 传递不同的 copy 标志。不能继续把两者都保存为指向源列表的 `OP_CALL`。

完整原始汇编只存于私有 `work/audit/nvn-command-sync/sdk-*.asm` 与 `sdk-sync-functions.json`，不纳入文档。REA 本机深度反编译引擎不可用，本轮使用现有 LLVM 反汇编工具和 NSO 元数据解析；没有下载或安装分析引擎，也没有执行原 SDK 驱动。

## 同步实现

`QueueFenceSync` 在队列提交锁内捕获已经提交的 Metal fence，随后发布同步对象状态。同步对象中的标志和 fence 使用原子字段，保持原宿主对象大小；CPU 查询也使用短锁取得一致状态。

`QueueWaitSync` 对未初始化、已 finalized、未围栏的对象返回 false。对有效围栏使用 Metal4 队列的 `waitForEvent:value:`，建立 GPU 侧对特定已提交值的依赖。空队列 fence 0 立即满足；拒绝依赖未提交的未来 fence。这里不调用 `waitUntilCompleted`、`mtl_finish` 或 CPU 全队列 drain。

`CommandBufferWaitSync` 现在录制真实 `OP_WAIT_SYNC`，保留 sync 对象引用，到回放时才检查当时的对象状态和围栏值。初始化但尚未围栏的对象可以被录制；若执行时仍是该状态，则与原 SDK 的失败等待一致，不建立 GPU 依赖，也不会因此崩溃。原对象必须保留到录制命令被执行，不能在提交前释放或重新用于别的对象。

录制与执行的前 16 次等待会记录对象身份、状态和 fence，便于核对本作启动时“先 SyncInitialize，后 CommandBufferWaitSync、尚无 QueueFenceSync”的实际顺序。已围栏的等待是 render-pass 合并、清除前提和其它前瞻重排的边界；待写常量及未完成的延后工作在边界上完成处理。

所有客体队列仍共享当前单一 Metal4 队列和提交上下文，队列提交会串行保护。同步条件 `GRAPHICS_WORLD_SPACE_COMPLETE` 使用更强的全部已提交 GPU 工作完成条件。这里没有宣称实现了完整的多硬件队列并行，也没有补齐未被本作调用的全部 536 个 NVN 入口。

## Call 与 Copy 的寿命区别

`CallCommands` 继续保存源 handle 引用。源命令内存需要保持有效，直到引用它的提交完成。源列表在合法重录后，后续 CALL 会读取新的内容。

`CopyCommands` 先在只读遍历中展开源列表的 BEGIN/JUMP/END 和嵌套 CALL，收集真正的命令记录，再用生产 `cmd_alloc` 写入目标命令内存。读取全部源内容早于目标分配器的任何回调，因此目标回调即便重新发放并覆盖源命令内存，也不会改变已经拷贝的内容。目标产生自己的 JUMP 链，之后不依赖原命令列表存储。

program bind 记录已经包含此前修复的 inline program snapshot 和 shader keys，拷贝时这些数据随记录归目标所有；不再回到原 `NVNprogram` 或其临时 control 指针计算 key。纹理、buffer、sync 等外部资源引用仍依照 NVN 对象寿命保留，Copy 没有复制整个资源内容。

宿主登记 EndRecording 完成的 handle 和已发放命令内存范围；`DeviceFinalizeCommandHandle` 现在撤销登记。Copy/Call 拒绝未完成或 finalized 的直接 handle。Copy 在修改目标之前检查所有输入，拒绝循环 CALL、越界记录和控制流、非法记录大小；有界预算为 16 层 CALL、100 万条记录、64 MiB 收集内容。源命令在收集期间不得被另一线程无同步重写，外部资源内存仍由调用方管理。

## 验证

```sh
.venv/bin/python tests/run_nvn_commands.py
MTL_DEBUG_LAYER=1 work/test-nvn-commands
```

这是实际生产 NVN 入口 → 生产录制 → Metal4 回放的独立测试，包含 64 项检查，普通运行与 Metal 验证层运行均为 0 失败。没有通过手工 memcpy 的正例冒充 API Copy 行为。

覆盖了：多段命令内存与嵌套 CALL、Copy 后源 handle finalized/源命令内存覆盖、真实 ProgramSetShaders 的旧 key 经 Copy/回放保留、目标内存回调覆盖源区、无效和循环 handle 的原子拒绝，以及录制后才围栏的同步对象。

GPU 测试以独立事件暂时阻塞生产队列，验证 QueueWaitSync 在 GPU 仍被阻塞时迅速返回，消费者不能提前完成，门释放后复制数据逐字节正确。此测试证明没有退化为 CPU drain；不代表所有游戏场景帧时间已经回归。

构建和运行证据保存于 `work/audit/nvn-command-sync/`。后续仍需整合后的游戏启动、跨场景长时间游玩和 iOS 真机验证；本文件不宣称这些步骤已经完成。

旧上游 `t_nvn.c` 的未围栏返回值断言已按上述 SDK 证据更新。其末段也已纠正为通过 `posix_spawn` 重新 exec `--unimpl-probe`，在任何 Metal 初始化之前调用未实现 API，并断言子进程按现有 fail-visible 契约以 SIGABRT 明确失败。没有 fork 正在运行 Metal 的进程，也没有恢复 silent stub。完整上游 fixture 重跑为 **64 项、0 失败**，原有 GPU 等待、读回、内存写保护、挂起恢复检查均保留。

可重复命令为 `.venv/bin/python tests/run_upstream_nvn.py`，日志位于私有 `upstream-build.log` / `upstream-run.log`。其中子进程的预期 FATAL 是负对照，不是游戏或父测试进程崩溃。
