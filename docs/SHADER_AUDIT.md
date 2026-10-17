# D3 原始着色器与运行接口审计

审计日期：2026-10-17。范围是已经提取的 SHD、链 `87c50a868147` 的生成结果、当前 `app.log` 和累计 PSO 成功记录。没有操作游戏窗口、切换优化或替换运行库。审计开始时用户仍在游玩，优先保持帧数。

## 结论

**阶段离线编译覆盖充分，但运行接口仍有明确缺口，不能据此宣称移植完整或画面稳定。** 当前日志存在两类真正的 Metal 管线失败：缺少 VS 输出，以及 normalized 顶点格式与整数输入接口不相容。另有纹理目标类型不匹配警告。灯笼随常量转发开关发生的闪烁由另一条资源依赖调查处理；这些接口问题不能自动解释该开关相关现象。

最关键的覆盖问题是：现有 `shader_pairs.tsv` 来自同一个 SHD 内阶段的保守组合。真实运行会出现表外配对，当前两组失败都在表外。因此，静态表内全部通过与真实运行仍漏绘制可以同时发生。

## 证据与数量

可重复执行：

```sh
.venv/bin/python tools/audit_shader_interfaces.py
.venv/bin/python -m unittest discover -s tests -p test_shader_interfaces.py
```

完整私有结果在 `work/audit/shader-interfaces.json`，包含输入文件 SHA-256、全部阶段 MSL/JSON 摘要、失败原文和解析边界。以下为本次快照，不代表后续日志没有增加。

| 项目 | 本次观测 | 能说明的范围 |
| --- | --- | --- |
| CPK SHD 提取 | 1569 个记录、1569 个 SHD 文件 | 已识别 SHD 容器，不包括未知容器格式 |
| 唯一阶段 | 1323：544 VS、779 PS | 本次提取范围未发现 CS/HS/DS/GS，不能推断整个游戏永远不用 |
| 对应 metallib | 1323/1323 存在 | 文件覆盖；运行链接和视觉正确性另验 |
| SHD 同容器保守配对 | 1457 | 不是运行时绘制事实 |
| 上述配对的 emitted MSL varying 声明比较 | 0 缺输出，0 类型/插值差异，0 解析未知 | 只比较接口声明，不检查原始算法或所有渲染状态 |
| 累计 PSO 成功记录 | 243 个状态键、193 对独立 VS/PS、259 个阶段加载标识 | 跨进程累计历史，不是当前会话的全场景覆盖 |
| 成功配对在同容器表外 | 6 对 | 证明同容器表不能穷尽真实运行配对 |
| 当前日志失败 | 2 对、各出现 2 次 | 不是每帧失败次数；失败缓存和预热会影响日志次数 |
| 现有缺省输出补齐 | 70 个 VS 的 `vs_pad` 非空 | 目前按静态配对表补，漏表外关系 |
| 带整数属性接口的 VS | 533/544 | 是需按实际顶点格式核验的候选面，不能当作 533 个错误 |

SHD 提取和包收据：`work/shaders/cpk-receipt.json`、`work/shaders/package-receipt.json`。包收据还记录 30 个早期运行捕获阶段与静态原始字节逐一相符、没有缺失。30 个样本不能替代所有后续章节的运行覆盖。

### 实际失败 A：VS 缺输出

- VS：`56e679b7d07788a8_b`，其 MSL 的 `main0_out` 只有 position 和 point_size。
- PS：`76a9b1fafc7c5d8c_b`，其 `main0_in` 要求 `user(locn1)`、`user(locn3)`。
- Metal 原文：`Fragment input(s) user(locn1),user(locn3) mismatching vertex shader output type(s) or not written by vertex shader`。
- 独立静态比较明确得到缺少位置 `[1, 3]`；这对不在 1457 配对表中。

不能直接把 VS 的 `pc_paired` 源文件名当作运行效果身份。打包器按阶段去重，一个阶段可以在多个 SHD 复用，JSON 仅保留一个代表性来源。也应排除程序生命周期或按阶段绑定状态错误；仅补 varying 会让链接通过，却可能掩盖错误配对。

### 实际失败 B：normalized 格式与 uint 输入

- VS：`18f2aadcec113d49_b`，属性 2 声明为 `uint4 m_26`。
- PS：`22e0cb8cba3b1d5a_b`。
- Metal 原文：`Vertex attribute m_26(2) of type uint4 cannot be read using MTLAttributeFormatUChar4Normalized`。
- 两阶段的 varying 声明相容，但顶点输入状态不相容；该运行配对也不在静态表中。

另外，当前日志有 `顶点属性格式 0x27 与着色器输入类型 float 对不上，位模式保不住（照原格式）`。这是独立警告；日志没有携带 shader 身份，不能擅自归到上述失败上。

### 实际纹理警告

当前日志：`贴图类型不符：着色器声明 7，贴图 2（贴图号 259），照原样绑`。本机 Apple `MTLTexture.h` 中 7 是 `MTLTextureType3D`，2 是 `MTLTextureType2D`。当前日志未记录 shader 键和槽位，不能确认究竟哪一个阶段错误，或是游戏有意使用的未采样占位绑定。

静态纹理声明按绑定计数：2312 个 `texture2d<float>`、57 个 cube、24 个 3D、1 个 2DMS。24 个 3D 绑定分布于 8 个 PS，代表性容器均为 ToneMap/SoftFocus ToneMap 系列；这使 LUT/色调映射成为后续定位入口，不能据此确认运行警告来源。

## 缺省反射与驱动常量边界

1323 个阶段全带 `无配对 PC 反射，查询按缺省`。一个额外缺省提示是 `7d07ee7a91c6f85d_b` 的纹理句柄 8 缺少 PC 类型信息，查询按 2D；但其最终 MSL 实际声明 `texture2d_ms<float>`，代表性来源为 `PostFX Copy Depth MS2.shd`。因此提示不能直接等同于最终错用了普通 2D。

生成 JSON 的 `drv_reads` 全为空、`drv_unfillable` 全为空；直接在生成 MSL 中搜索 `vp_c0/vp_c2/fp_c0/fp_c2` 也未发现声明或使用。560 个阶段存在离线 c1 数据，13 个 support 绑定，1756 个 cbuf 绑定。它们只说明当前输出中的识别结果，不能证明原始驱动查询都答对，也不能证明默认 texture/attribute 类型在全部运行状态下正确。

## 修复顺序与保持帧数的约束

1. **最高优先：局部修复常量转发资源依赖。** 用户已经通过 OFF 不闪、ON 又闪提供强因果证据。保留整体转发收益，只在实际需要读取已写附件、别名或排序边界时 flush。用相同灯笼位置验收画面，并确认通道数没有整体退回约 436。此审计不修改该生产路径。
2. **补运行配对证据，再完善链接。** 在原有成功 ledger 之外持久保存失败 pair、完整 PSO 状态和程序 serial/绑定来源。确认合法配对后，为真实需要的 VS/PS 接口补齐原平台缺省值，或者提供按 PS 输入需求选择的 VS 变体。不能把 544×779 全组合全部当真实使用，也不能无证据把所有缺输出填零后宣称正确。
3. **为实际顶点输入格式选择接口变体。** 现有 `int_inputs()` 是基于使用方式的启发式，不足以决定 NVN 顶点 fetch 的实际格式。normalized/half 输入应通过 Metal float 接口完成 fetch，再在函数内部按位恢复原来寄存器解释；整数 fetch 保留整数接口。不能把 NVN normalized 格式粗暴改成 raw uint 格式，因为这会改变原平台的转换语义。
4. **补纹理身份观测。** 类型警告带 shader、arg/reg、handle、tex serial、view target、实际采样与否；确认后修复翻译查询或资源 view。对 3D/2D 不匹配自动造替代纹理或丢绑定会掩盖真实问题。
5. **跨章节验收。** 每个场景记录新增 shader/pair、管线失败、纹理/顶点格式警告、前台帧时间、手柄和保存退出；在 60 FPS 稳定预算之外，另做画面完整性验收。静态扫描不能保证完整和稳定。

### normalized 入口包装方案的可行性与限制

可行的局部形态是把特定 normalized 属性的入口从 `uint4` 改为 `float4`，然后在函数入口建立 `uint4 dm_raw = as_type<uint4>(in.attr)`，将原函数体的该属性引用改为 `dm_raw`。这样 Metal 完成 normalized fetch，而函数体仍获得该 fetch 结果的 32 位寄存器位模式。**不能使用 `uint4(in.attr)` 数值转换，也不能只改字段类型而不适配函数体。**

已在私有 `work/audit/shader-normalized-entry-probe.metal` 对实际 VS `18f2…` 的属性 2 做隔离原型，改写 4 处引用，并通过 `xcrun -sdk macosx metal -c`。原始 `.metal`、`.metallib`、链指纹和运行应用均未更改。证据摘要在同名 JSON。这个小探针只证明改写可以编译，不证明实际 NVN 指令语义、Metal 管线链接、GPU 输出或全场景正确。

生产实现仍需处理：多个属性分别选择的组合、向量宽度和 signedness、Metal 缺省分量、half/normalized 精度、属性跨函数引用、缓存键与预热使用相同变体、原始寄存器语义对照。应从实际失败的格式组合开始，按需求生成变体；不能产生指数级全属性组合后全量编译影响用户游玩。验收须包括 normalized 与 integer 两组使用同一原始 shader 的数值和图像对照，以及运行场景 OFF/ON/修复版比较。

## 本次验证

新增审计器的 5 个独立解析测试通过，覆盖缺输出与类型差异的区分、真实失败的 position-only VS 接口形态、插值限定、未知数组声明不误判为干净、未知 PSO ABI 拒绝解析。PSO 身份解析所依赖的当前结构大小另外用 C 编译检查：`sizeof(pso_skey)=432`、`offsetof(k)=88`、`offsetof(attr)=136`。没有全量重编 1323 阶段、没有执行 GPU 负载测试，也没有替换游戏 shader 链。

## 后续实现：按真实 fetch 类型选择入口（同日）

上述“尚未实际实现”的顶点接口方案已经落地为独立层；没有修改基础翻译链、原始 stage JSON 或 shader profile 表。生产代码在 `nvn_vertex_fetch.h` 和 `nvn_mtl.m` 的 `vertex_fetch_function()`/`pso_desc()`。它按实际 NVN 格式选择 float/uint/int 入口，并按位恢复原函数体需要的寄存器类型。normalized/half 格式保持原样，signed integer 保留符号扩展，不将 signed byte 粗暴改成 unsigned byte。

`tools/vertex_fetch_variants.py` 导出全部 544 个 VS 的独立 `.vsrc` 来源与 `.vsrc.json` 收据；已预构建两个已知失败布局和历史成功 PSO 中另需的七种布局，共九个 macOS 库。每个 Metal location 用两位编码，0 保留原接口，1/2/3 分别请求 float/uint/int。变体包含基础 chain、来源 SHA-256、转换修订号、适配来源 SHA-256、库 SHA-256 和目标 SDK。生产层验证这些身份；未预构建的新布局只在首次遇到时编译，再按 shader/签名缓存。预构建和运行生成函数使用相同的转换规则，不能混用 macOS 和 iPhoneOS 的 metallib。

可重复执行：

```sh
.venv/bin/python tools/vertex_fetch_variants.py work/build/cache/metal_shader_cache/b-87c50a868147 --known-variants --ledger work/run/pso_user.tsv
.venv/bin/python -m unittest discover -s tests -p test_vertex_fetch.py
clang -O1 -Wall -fobjc-arc tests/test_vertex_fetch.m -framework Metal -framework Foundation -o work/test-vertex-fetch
work/test-vertex-fetch work/build/cache/metal_shader_cache/b-87c50a868147
```

验证结果：

- 三组实际失败描述符 `18f2…/956e…`、`18f2…/22e0…`、`88ba…/7033…` 均能用入口变体链接；同一描述符换回原始 VS 均被 Metal 拒绝，构成负对照。运行生成和预构建库两条路径均通过。
- 八种真实 GPU fetch：UNORM8（含 64/255、128/255 中间值）、SNORM16（含中间值）、half、unsigned byte、signed byte、float32、uint32、原本已匹配的 unsigned byte。32 个 GPU 像素、128 个整数输出通道全部等于独立预期的寄存器位，包括 NaN payload、负零、无穷和最小 subnormal 的 float32 fetch。
- 三个 Python 测试对生产 Objective-C helper 和离线 Python 转换逐字比较，涵盖两个原始失败 VS、多属性不同类型以及拒绝未知/重复请求。

这证明接口变体能修复上述 Metal 格式失败并保留测试覆盖的 fetch 位语义，仍不等于完整游戏的视觉验收、实际 iPhone GPU 测试或所有顶点格式精度一致性证明。首次遇到未预构建布局可能产生编译尖峰，应继续从真实 PSO ledger 补预构建布局。

### 其余接口问题的证据边界

修复程序快照后的 `lantern-guard-ab-20261017-210528`（runtime `b073…`）城镇测试未再次报告旧的 VS/PS 缺输出或 3D/2D 类型警告。旧裸 guest 程序对象和分阶段绑定身份被复用可能影响过配对，因此当前没有用盲补零 varying 或伪造纹理转换来遮住旧错误。

为后续复现添加两类精确记录：真正 PSO 失败时，`pso_user.tsv` 写入 `F + 完整 pso_skey + 原因`，与成功 R 记录分开；不支持的纹理目标组合按 shader、stage、reg、tid、texture serial、目标类型和尺寸去重记录。这些诊断保留真实错误；仍需跨章节触发，才能判断剩余问题是否已经被程序寿命修复消除。不能据一次城镇测试宣称全场景接口完整。
