# 通用触控外观来源

从 [d2r-mobile](https://github.com/jhaizhou-ops/d2r-mobile) 的提交 `9393b00ea9aca52d9254214da93738f26582562f` 复用两项通用素材：

- `dm/ios/Sources/DmTouchControlArt.h` → `Sources/DmTouchControlArt.h`，SHA-256 `50d77ffbef01f5278bcbe79636ea373f7687095efc821a84b0f03eb0f5caaa86`。
- `dm/ios/Sources/ControlArt/dm_mobile_socket.png` → 本目录同名文件，SHA-256 `06492a002198c2a79353eeb60a953f2cebd5fead001c09e2ce6786226d69758b`。

两项文件原样复制。源仓库为 MIT，版权 `Copyright (c) 2026 jhaizhou`；完整原许可证位于 `LICENSE.d2r-mobile.txt`。机器可读回执为 `provenance.json`。

这里只使用薄边圆形嵌槽、渐隐摇杆底盘和哑光摇杆头。没有复制 D2R 职业技能图案、原游戏素材、HUD 绑定桥或触控状态机。D3 按钮仍显示真实 A/B/X/Y/肩键等绑定；没有宣称已解析动态 D3 技能图标。

`DmGamepad.m` 保留既有命中区域、拖动所有权、多点触控、位置映射及外接手柄隐藏/清零。每次尺寸或屏幕 scale 变化生成 10 张小控件图像并替换旧缓存；按下仅切换 layer contents，摇杆移动仅改变 knob position。没有逐帧全屏绘图、额外 timer 或 display link。

打包时将 PNG 作为平铺资源 `dm_mobile_socket.png` 或保留 `ControlArt/` 路径均可；还需保留许可证与回执。PNG 缺失时使用共享头文件中的矢量嵌槽作为降级，并输出一条日志。

验证范围：iPhoneOS SDK syntax-only 编译通过；所有输入几何常量、28 个输入/命中/清零方法及 physical-present 尾部与改前逐字一致。已用同一 CoreGraphics 绘图函数制作离屏材质状态预览。离屏材质预览不代表 UIKit 实机布局、触摸或性能验收；最终需要安装包在真实屏幕检查。
