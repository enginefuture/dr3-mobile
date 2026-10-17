# Third-party notices / 第三方声明

Compatibility-layer source is MIT licensed. Each component retains its original notices. These licenses do not grant rights to Diablo III, its programs, assets, shaders or trademarks.

| Component | Origin and license | Local record |
|---|---|---|
| Native host, NVN/Metal and offline toolchain | [nxnative](https://github.com/seedds/nxnative), MIT; pinned `9579030e5b1f0443c12b7376559560915b6d4c4b` | Reconstructed locally; [changes](docs/UPSTREAM_CHANGES.md), [patch](patches/nxnative.patch) |
| Compatibility method, validation tools | [d2r-mobile](https://github.com/jhaizhou-ops/d2r-mobile), MIT | [license](third_party/d2r-verify/LICENSE), [origin](third_party/README.md) |
| Generic controller foundation | [blade2-mobile](https://github.com/ha7rock/blade2-mobile), MIT; via Bayonetta 3 Mobile | [Blade II notice](third_party/LICENSE.blade2), [D2R notice](third_party/LICENSE.d2r-mobile) |
| CPK reference parser | [D3CPKUnpack](https://github.com/RedMadKnight/D3CPKUnpack), MIT, pinned `7ac76a99791b55ccef01fd6afdfac5d3dbf70a48` | [license](third_party/d3cpk/LICENSE) |
| Generic touch-control drawing and socket artwork | d2r-mobile `9393b00ea9aca52d9254214da93738f26582562f`, MIT | [license and provenance](platform/ios/Sources/ControlArt/README.md) |
| Publication audit and NSO helper adaptations | [Bayonetta 3 Mobile](https://github.com/enginefuture/bayonetta3-mobile), MIT | [license](LICENSE) |

The ignored nxnative checkout includes Ryujinx's MIT shader translation code, Spv.Generator, libvpx, libdeflate and other dependencies. Bootstrap retains their original licenses in that checkout; they are not re-licensed by this project. Ryujinx translation is an offline build step, not the runtime emulator application.

No extracted game icon is published. The local icon generator reads only the user's private extraction. No original or translated game shader corpus is published.
