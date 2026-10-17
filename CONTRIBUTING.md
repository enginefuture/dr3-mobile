# Contributing

Support legitimate purchases. Read [the game files policy](docs/GAME_FILES.md) before opening an issue or PR. Never attach NSP, keys, game programs/assets/shaders, game-containing packages or saves. Include OS, hardware, toolchain and a small redacted error summary only.

Use the pinned upstream revision and retain its licenses. Record backend changes in `docs/UPSTREAM_CHANGES.md` and regenerate `patches/nxnative.patch` from the pinned checkout. Preserve exact-build guards. Separate compilation, synthetic tests, actual rendering and user-confirmed gameplay; do not mark complete compatibility from startup alone.

Stage only reviewed source, then run `python3 tools/audit_public.py --all-history`. CI audits the index and reachable history. Run the relevant synthetic regressions; native Metal tests need an Apple silicon Mac. Bonjour tests are opt-in because they advertise a temporary local service. Tests must not alter game saves, network interfaces or devices.
