# Third-party sources

- nxnative: https://github.com/seedds/nxnative, fixed commit 9579030e5b1f0443c12b7376559560915b6d4c4b, MIT. Recreated by `tools/dr3.py bootstrap`; the checkout is ignored. Includes Ryujinx shader translation, libvpx, libdeflate and other dependencies with their original notices. Local changes are preserved in `patches/nxnative.patch`.
- d2r-verify: `structck.py`, `equiv.py`, `nsoimg.py` from https://github.com/jhaizhou-ops/d2r-mobile at 21cf97b91823111ead237858ea79929afacf71a5, MIT. Includes documented adaptations for nxnative's metadata, CTR policy, dynamic SP template and precise thread-slot write filtering. These tools are copied into nxnative/dm/verify to retain upstream relative paths.
- tools/nso.py: NSO reader adapted from the local enginefuture/bayonetta3-mobile/tools/analyze.py; MIT. Uses only caller-supplied modules.

No game programs, assets, shaders, keys or tickets are included.

- d3cpk/cpklib.py: D3CPKUnpack by RedMadKnight, https://github.com/RedMadKnight/D3CPKUnpack at 7ac76a99791b55ccef01fd6afdfac5d3dbf70a48, MIT (license alongside). Our tools/cpk_shaders.py adds strict boundaries, exact decompression checks, sector-zero handling and the observed numeric cipher initializer.
- native/gamepad_mac.m: adapted from the local bayonetta3-mobile/third_party/blade2-mobile/dm/host/gamepad_generic.m. MIT, copyright 2026 Blade II Mobile contributors; portions copyright 2025–2026 d2r-mobile authors. Notices preserved in LICENSE.blade2 and LICENSE.d2r-mobile. Changes add background gating, foreground polling, eager state sampling, finite-axis checks and disconnect cleanup.
