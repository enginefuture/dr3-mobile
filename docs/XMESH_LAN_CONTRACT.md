# Future Mesh LAN integration / Mesh 接入契约

Status: design only, 2026-10-18. Local Wi-Fi transport exists and Mac host → iPhone client joining was user-confirmed; this does **not** implement a public-Internet virtual LAN or Battle.net. The detailed local integration notes remain private.

The intended Mesh integration should reuse the game's LDN/socket ABI and lifecycle boundaries while replacing discovery, peer authorization and data addressing. The present local HMAC room protocol is not an organization/device access-control system.

## Requirements for a shared native SDK

- macOS and iOS static library/XCFramework with a versioned C ABI, fixed-width structures, explicit ownership and bounded event/packet queues. No Tauri/WebView dependency in game runtime.
- Native device enrollment and organization membership; room leases, compatible game/version filtering, capacity, join/leave, authorization revocation and generation/session barriers. Authenticate room operations independently of user-supplied labels.
- Authenticated peer datagrams for UDP plus ordered streams for TCP, NAT traversal and a relay fallback. Report connection mode and errors; do not block the render/game thread on authentication or DNS.
- Stable virtual IPv4/port mappings scoped to each room. Allow only current authorized room peers; bound broadcast fanout. Preserve guest BSD fd ownership across room changes, while background/finalize revoke transport correctly.
- Negotiated MTU, maximum message sizes, queue limits, cancellation, backpressure and explicit errors. Oversized datagrams fail visibly or use bounded versioned reassembly with peer/room/session isolation, timeouts and strict limits.
- Native Keychain-backed credentials and device-local identity on iOS; OS-authenticated IPC for any macOS companion. No tokens or private keys in command lines, logs, public diagnostics or web UI.

## Game-side boundary

The locked game has static imports for 17 LDN, 29 C++ socket, 19 C nnsocket and 10 NIFM operations. Counts are not proof of complete runtime coverage. Implement exact ABI layouts and guest errno conversion, including nonblocking progress and SO_ERROR. LDN initialization, state, scan, room creation/join, network info and address queries must reflect real room state, never unconditional success.

Current native LAN uses Bonjour and directly routed Wi-Fi IPv4 UDP/TCP. It rejects public destinations and lacks NAT traversal. A TCP proxy alone cannot replace the game's UDP traffic. The Mesh provider must supply both discovery/authorization and data paths.

## Acceptance before release

Two real devices in one authorized organization must discover, join, synchronize movement/combat/drop/scene changes and retain independent saves. Repeat across separate Internet connections using both direct and relay paths. Test unauthorized/expired/revoked membership, stale room generations, wrong versions, full rooms, packet loss/reordering, oversized traffic, host exit, Wi-Fi changes and app background/foreground.

Compare frame times and queue/memory growth with single-player on the same device/scene. Independent echo tests, compile success or one successful join are insufficient. Do not label Mesh as available before implementation and this evidence exist.
