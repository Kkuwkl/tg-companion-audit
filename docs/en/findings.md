# Findings

**Published: 2026-11-16** · Author: [nimo](https://github.com/Kkuwkl)

Four findings from a review of `tg://companion` in Telegram-iOS `release-13.1` … `13.2`. Audited tree: `24638bc69bd083981b178dd1e7f921eebbf7fc46`; the companion code is byte-identical to the source commit `44681a28ee4ad9792f6447a681e615a997af5323`.

This document contains **no `.glb` files and no generator**. Reproduction is described at the field level; the full spec goes to the vendor on request.

Paths of the form `security/…` are the audit's internal evidence identifiers. The raw bundle (harnesses, corpora, logs) is not part of this repository; it is available to the vendor on request.

| # | Finding | What it takes | Effect | Severity |
|---|---|---|---|---|
| 1 | Crash inside the error handler | channel control + second tap | deterministic process kill, 716–952 B | high (as a DoS) |
| 2 | Resource amplification | channel control + second tap | jetsam / watchdog / freeze | medium |
| 3 | Catalog addressed by username | control of the username | silent change of executable input for all users | high |
| 4 | The process that shipped it | — | no review, no tests, no update path | process |

Severity in the table is conditional: how bad the effect is if its precondition holds. It is not the repository's overall rating — the README badge reads low–medium because nothing here is reachable without control of the channel, and Finding 1 has no CVE and no memory corruption; it is a plain logic error on an error path.

---

## Finding 1: crash inside the error handler

**Summary.** `errorFor` converts an arbitrary `std::string` to `NSString` with a failable API and then inserts the result into an `NSDictionary` literal without checking for `nil`. A file can put invalid UTF-8 into the message. The conversion returns `nil`, the literal raises `NSInvalidArgumentException`, and this happens **inside** the C++ `catch` block that was supposed to report the failure. The process dies with no toast, no undo overlay and no log.

### The code path

`submodules/CompanionRenderer/Sources/CompanionRenderer.mm:13`:

```objc
NSError *errorFor(const std::string &message) {
    return [NSError errorWithDomain:@"Companion" code:1
        userInfo:@{NSLocalizedDescriptionKey:[NSString stringWithUTF8String:message.c_str()]}];
}
```

It is called as `errorFor(ex.what())` from four `catch (const std::exception &)` blocks: `:89`, `:157`, `:175` (`setComponentAtURL`), `:213` (`applyPreset`). The two that matter are `:175` and `:213`, because their `try` bodies parse file content.

Seven throw sites interpolate strings that come from the file:

| Site | Message | Field |
|---|---|---|
| `Core/CharacterInstance.cpp:15` | `Duplicate node identifier: <id>` | `nodes[].extras.giftNode.id` |
| `:25` | `Animation node is missing: <id>` | `GIFT_animation_binding.node` |
| `:37` | `Morph target is missing: <a>/<b>` | `GIFT_animation_binding.morphs[]` |
| `:74` | `Socket node is missing: <id>` | `extras.giftAsset.sockets[].node` |
| `:165` | `Materials do not define slot: <slot>` | `meshes[].extras.giftSlot` (slot comes from the **model**) |
| `:172` | `Materials do not define slot: <slot>` | same |
| `:189` | `Item bone is missing: <id>` | `giftNode.externalJoint` |

`GiftModel.cpp:74` accepts a string if it is non-empty, ≤256 bytes and contains no backslash. That is the entire filter. `jsmn` inside `cgltf` validates only escape sequences (`ThirdParty/cgltf/cgltf.h:6983-7045`); `cgltf_decode_string` copies bytes (`:1381-1450`); `cgltf_validate` never looks at names (`:1597-1806`). So `0xFF` reaches `std::runtime_error` untouched, and `std::string` preserves arbitrary bytes.

<details>
<summary>Why nothing above catches it</summary>

- `@try` / `@catch` in `submodules/CompanionRenderer` and `Components/DebugCompanionScreen`: **0 occurrences**.
- `NSSetUncaughtExceptionHandler` in the repository: **0 occurrences**.
- The `catch (const std::exception &)` at `:175` cannot catch an Objective-C exception thrown in its own body.
- Swift `do/catch` at `DebugCompanionScreen.swift:401-412` receives only `NSError`; the bridge fills it only when the method returns `NO` with `*error` set, which never happens here. The `showError` call at `:411` is unreachable.
- `BUILD` sets `-fexceptions` explicitly, so the C++ path is compiled as reviewed.

</details>

### Reproduction spec

The shortest trigger is **716 bytes**: a GLB 2.0 file, one triangle (`POSITION` + `NORMAL`), `extras.giftAsset.kind = "model"`, and **two nodes whose `giftNode.id` is the same two bytes `41 FF`**. `nodeMap` throws on the duplicate (`CharacterInstance.cpp:15`) while building the asset (`AssetLibrary::load:73`), i.e. before any rendering state exists. The ASCII control with `41` alone loads normally and produces a valid `NSError`.

Sibling forms follow the same pattern: `sockets[].node = "A\xFF"` (`CharacterInstance.cpp:74`), an animation channel binding `{"version":1,"node":"A\xFF"}` (`:25`), and an item bone (`:189`). Tested samples span 716–952 bytes; the item-bone form was identified by code reading, not executed. The animation form needs a model with the same `rig` string; the bundled classic model exposes its rig in cleartext, so this is not an obstacle.

Everything else must be valid: `cgltf_parse`, `cgltf_load_buffers`, `cgltf_validate`, the 32 MiB gate and the `kind`/`version` checks all run **before** the target `require`. That is the point — the file is rejected correctly, and the rejection kills the process.

### Evidence

- Harness on **unmodified** `GiftModel.cpp` and `CharacterInstance.cpp` (structurally identical SHA-256 to the pinned commit), WSL clang 21.1.8, only two OpenSubdiv entry points stubbed and unreachable for these files.
- Observed message bytes: `… 3A 20 41 FF`, `valid_utf8: FALSE`. ASCII controls return `valid_utf8: true` and a normal error.
- Two independent harnesses agree; one corrected an earlier sample where `GIFT_animation_binding` was written as a string instead of an object.

### What is not verified

The Foundation link itself — `+[NSString stringWithUTF8String:]` returning `nil` for invalid UTF-8, and `+[NSDictionary dictionaryWithObjects:forKeys:count:]` raising on a `nil` value — was not executed here (Windows/Linux host, no macOS). Both are documented Apple/clang contracts; the check is two lines of ObjC on a Mac. No iOS device was available, so the in-app path (Swift frame unwinding, absence of a third-party exception handler inside vendored SDKs) is reasoned from the tree, not observed.

### Fix

```objc
NSError *errorFor(const std::string &message) {
    NSString *text = [[NSString alloc] initWithBytes:message.data()
                                              length:message.size()
                                            encoding:NSUTF8StringEncoding];
    if (!text) text = @"Invalid component";
    return [NSError errorWithDomain:@"Companion" code:1
                           userInfo:@{NSLocalizedDescriptionKey: text}];
}
```

Plus a UTF-8 and alphabet check in `ProfileJSON::string` (`GiftModel.cpp:74`), so the file is rejected with a valid message instead of reaching the error path at all. Both `:173` and `:217` use the same unsafe conversion and should be changed with it.

Source: `security/verify/C02a.md`, `security/verify/C02b.md`; code at `CompanionRenderer.mm:13`, `CharacterInstance.cpp:15-189`, `GiftModel.cpp:74`.

---

## Finding 2: resource amplification

**Summary.** Every limit in `GiftModel::load` is per object. Nothing budgets the product, and several expensive operations happen before their own gate. Four independent mechanisms were measured on files that pass every check.

| Mechanism | Input | Peak | Time | Container measured |
|---|---|---|---|---|
| 128 primitives sharing one index accessor | 2.35 MiB (2 460 632 B) | **607.9 MiB** RSS + ≈1.23 GB GPU | 1.62–2.02 s | `Σ p.indices` = 614 400 000 B (585.9 MiB), 153.6 M elements |
| 64 distinct 4096² PNG | 3.63 MiB (3 806 732 B) | **4.0 GiB** (peak 4162.9 MiB) | 15.99 s (emulator) | RGBA8 = 4 294 967 296 B |
| 64 `images[]` over one 32 MiB `bufferView` | 32 MiB (33 554 432 B) | **2115 MiB** (peak) | memcpy 1.89 s | `Σ images[]` = 2 147 202 304 B (2.0 GiB) |
| 2048 skins over one shared IBM accessor | 1.0 MiB (1 053 600 B) | 67.0 MiB (131 GB churn) | **175.9 s on main** | 2048 × 64 000 000 B |

Ratios: ≈1147×, ≈259×, ≈66×, and 176 s per megabyte respectively. The first column is the file; the last is what the process actually holds.

### Mechanism 1 — indices

`GiftModel.cpp:321-326` limits `indexCount` **per primitive** (≤1 200 000) and copies element by element without `reserve()`; `:385` moves each primitive into the model, so all of them live until `load` returns; `:388` checks `primitives.size() <= 128` **after** all 128 are built. `CompanionRenderer.mm:131` then creates a shared-storage Metal buffer of the same size, doubling the footprint. Linear control: 1 primitive → 16.6 MiB, 16 → 89.7 MiB, 128 → 607.9 MiB, same accessor.

One `accessor` of 1.2 M `uint16` indices, referenced by 128 primitives with `{"indices": 0}`, is enough. Nothing in the file is malformed.

### Mechanism 2 — textures

Each decoded image becomes `w*h*4` bytes (`CompanionRenderer.mm:101`) and a texture (`:109-111`); the cache at `:42` is keyed by **content** (`:92`), and eviction at `:116` does not free anything while a draw holds a strong reference (`:142`). 64 distinct 4096×4096 single-colour PNGs cost ~59 KB each compressed and 67.1 MB each decoded.

Two corrections to the naive version of this claim, both verified:

- 64 `images[]` pointing at the **same** `bufferView` decode **once**: 65 004 B → 126.6 MiB peak. The content-keyed cache defeats the duplication.
- 4 GiB therefore needs 64 **different** payloads — which is cheaper for an attacker (3.8 MB of file) and is what the table above measures.

### Mechanism 3 — `images[]` copies

`GiftModel.cpp:177` initialises a `std::vector<uint8_t>` from an iterator pair, i.e. copies the whole `bufferView`, with no deduplication and no budget. `:170` allows up to 64 images. Pointing 64 entries at one 32 MiB view (exactly the file gate at `:152`) yields 64 copies. Control: 8 images → 256.0 MiB, confirming a copy rather than a reference. The bytes need not be a valid PNG — `load` only checks `mime_type` and copies.

### Mechanism 4 — skins

`GiftModel.cpp:286` iterates `raw->skins_count` with no limit; `:289` calls `floats()` **inside** the loop, so the same `inverse_bind_matrices` accessor is decoded 2048 times. Each call allocates `count*16*4` bytes (`:19`, with `count` allowed up to 1e6) and runs an `isfinite` pass (`:21`). Measured: 108 ms for one skin, 175.871 s for 2048 — 85.9 ms per skin, peak RSS only 67.0 MiB. `byteStride = 1` passes `cgltf.h:1610-1612` because `req_size` stays inside the view. This is the case that no memory budget can catch: the weapon is time on the main thread.

### Related: the skeleton over-read (not a crash)

`inverse_bind_matrices->count` is never compared with `joints_count` (`GiftModel.cpp:286-293`). With `joints_count = 256` and `count = 1`, `std::copy_n(binds.data() + j*16, 16, …)` reads up to 16 320 bytes past a 64-byte allocation. ASan on the unmodified file reports `heap-buffer-overflow READ of size 64` at `:292`. Effect in practice: a collapsed or invisible model (`radius = 0.001`) or an empty frame — **0 crashes in 400 release-mode runs**, and the distortion is not controllable from the file because `joints_count ≤ 256`. It is a proven memory-safety defect with a visual effect, not a DoS primitive.

### Parser-level amplification

Independent of the four above, the parser itself grows ~10× on dense JSON: 24.41 MB → 246 MB RSS. The `"accessors": [{}, {}, …]` shape is estimated at ≈160 bytes of heap per input byte, which is where the theoretical multi-gigabyte ceiling comes from. We report the measured value, not the estimate.

### Why the gates do not help

| Gate | Value | Why it does not bound the product |
|---|---|---|
| file size | ≤32 MiB (`:152`) | each of the four inputs is far below it |
| images / materials | ≤64 / ≤128 (`:170`) | limits are multipliers, and pixels are unbudgeted |
| vertices | ≤200 000 (`:317`) | indices, images and skins are separate counters |
| accessor count | ≤1 000 000 (`:18`) | 1e6 is a per-call limit, not a total |
| primitives | ≤128 (`:388`) | checked after all 128 exist |

### What is not verified

All numbers are from x86-64 Linux/Windows harnesses. iOS jetsam thresholds, Metal texture accounting in `phys_footprint`, and A-series timing were not measured; on a phone the process should die earlier, and the 16 s decode emulator is slower than ImageIO. The trends transfer; the exact device numbers do not.

### Fix

```cpp
require(raw->skins_count <= 64, "Too many skins");
require(sparse->count <= (1u << 20) && sparse->stride >= element_size,
        "Unsupported sparse accessor");
require(totalImageBytes <= (64u << 20), "Texture payload budget exceeded");
require(indexTotal <= (1u << 26), "Index budget exceeded");
require(cage.faces * (1u << (2 * level)) <= 30000, "Subdivision budget exceeded");
```

Move the subdivision budget **before** `RefineAdaptive` (`Core/Subdivision.cpp:78`); today the patch and control checks sit at `:80` and `:84`, after the expensive call. Add de-duplication by `bufferView` for `images[]`, and cache one `floats()` result per accessor.

Source: `security/verify/C03.md`; `security/13-cgltf-empirical.md`; code at `GiftModel.cpp:152-177, :286-293, :317-388`, `CompanionRenderer.mm:42-142`, `Subdivision.cpp:74-84`.

---

## Finding 3: the catalog is addressed by username

**Summary.** The screen does not know which channel it trusts. It resolves a hard-coded **name**, takes whatever peer comes back, and downloads the newest `.glb` with a matching filename. Nothing binds the peer, the document or the bytes.

### The flow

```mermaid
flowchart TD
    A["CompanionCatalog.load()"] --> B["resolvePeerByName(name: \"tttt3dexample\")<br/>CompanionCatalog.swift:59"]
    B --> C["peer.id used directly<br/>:62-67, no case .channel"]
    C --> D["messages.search(peer, tags: .file, limit 100)<br/>paginated to the end"]
    D --> E["filter: name hasSuffix .glb<br/>most recent message wins<br/>:85-91"]
    E --> F["MediaBox download, 32 MiB gate<br/>GiftModel.cpp:152"]
    F --> G["cgltf -> OpenSubdiv -> Metal"]
```

| Property | What the code does | Consequence |
|---|---|---|
| Peer identity | name only; `peerId`/`accessHash` are not pinned (`:59-67`) | renaming or re-registering the username changes the input |
| Peer type | no `case .channel` check (`:62-67`) | a public group, or a user whose saved messages hold `.glb` files, becomes the catalog |
| Document identity | no `documentId`, no SHA-256, no signature | "latest message with this name" is the only rule; deleting a post silently reverts to the previous file |
| Resolution cache | `ageLimit = 2*60*60*24 = 172 800` s, 48 hours (`ResolvePeerByName.swift:59-69`) | a warm client keeps reading the old channel for up to two days; a cold client switches immediately |
| Filename filter | suffix `.glb` and a per-kind suffix (`CompanionCatalog.swift:18-28, :90`) | no MIME check, no size check beyond 32 MiB, no allowlist |
| UI disclosure | preset chip shows only a digit (`DebugCompanionScreen.swift:518`); the name is only in `accessibilityLabel` (`:525`) | the user cannot see the source, size, date or author of a network component |

The username is not part of the peer address (`id`, `accessHash`), so the resolver cache and the server are the only things standing between a name and a channel. `@tttt3dexample` is a public channel that ordinary users cannot post to — which is exactly why this is filed as hardening rather than as a remotely exploitable issue: the trust anchor is mutable, but controlling it is a real precondition.

### Two-tap reality

One tap on `tg://companion` opens the screen and loads metadata plus the **bundled** classic model (`DebugCompanionScreen.swift:297-305, :370-372`). Sixteen of seventeen presets are not bundled (`isBundled == false`), and tapping one downloads files by compiled names (`:340-343`). Selecting an explicit component from the option list is a third interaction. There is no URL parameter, path, filename or peer argument in the deep link — the only thing an attacker controls remotely is the channel content.

### What an attacker gets, and what they do not

With channel control: arbitrary `.glb` (≤32 MiB) into a native parser, i.e. Findings 1 and 2, plus external strings in permanent UI labels. Without it: nothing beyond self-DoS with your own file. There is no path to another user's media, no write to the bundle, and no network egress from the companion code.

### Fix

```swift
guard case let .channel(channel) = peer else { return }        // no users, no groups
guard channel.id == Self.pinnedPeerId,
      channel.accessHash == Self.pinnedAccessHash else { return }
guard Self.allowed[option.name] == sha256(file) else { return } // documentId + hash allowlist
```

Also show the source channel, file size and date on the preset chip, and require a confirmation before the first network asset.

Source: `security/08-dataflow-catalog.md`, `security/verify/C05a.md`, `security/verify/C07.md`; code at `CompanionCatalog.swift:59-91`, `ResolvePeerByName.swift:59-69`.

---

## Finding 4: how this reached the App Store

**Summary.** A 46-thousand-line feature arrived in one commit with no pull request and no tests; the commit did not build on its own; the code then sat unchanged for two weeks and shipped in four releases.

| Date / commit | Event |
|---|---|
| 2026-10-12 16:56:23 +0400, `44681a28` | "Experiment": 117 files, +46 268/−2, one author |
| +7 m 49 s, `a8cc2ed228` | "Fix build": +38 lines, only `DebugCompanionScreen/BUILD` — the first commit referenced a package that did not exist (`TelegramUI/BUILD:433`) |
| 2026-10-20, `release-13.1` | First shipping release; then `13.1.1`, `13.1.2` |
| 2026-11-03, `release-13.2` / master `24638bc6` | 114 companion paths byte-identical; 0 substantive changes across 909 commits |
| 2026-11-16 | Still present; not fixed |

Three structural problems made this possible:

1. **No gate and no review.** The screen is a `Debug*` target with `visibility: ["//visibility:public"]` and no `testonly`, linked unconditionally. Nothing in CI compiles or exercises it; there are no unit tests and no fuzz target for `GiftModel::load` anywhere in the project.
2. **A frozen vendor.** `cgltf` is pinned to `85cd6238` (2026-02-02) and byte-identical to upstream; upstream HEAD is the same commit, so the three reproducible OOB reads are not fixed anywhere, and there is no `VENDOR.md`, no update script and no smoke test.
3. **Runtime shader compilation.** The renderer compiles `*.metal.txt` from the bundle with `newLibraryWithSource` on the main thread at every screen open (`CompanionRenderer.mm:55-61`), unlike the seven other Metal modules in the project, which ship a prebuilt `default.metallib`. A build cannot catch a shader error here.

None of this is memory-unsafe by itself. It is the reason a debug screen with no identity pin survived review, and the reason a one-line error-path bug is reachable in a shipping build. App Store guideline 2.3.1 (hidden features) is the likely reviewer objection; it is an organisational risk, not a security mechanism.

### Fix

`#if DEBUG` or a remote flag for the entry point, or an explicit product decision with disclosure in App Store Connect; a required review path for `submodules/*/ThirdParty/**` and new deep links; a libFuzzer target on `GiftModel::load` and a shader-compile smoke test in CI.

Source: `security/01-scope.md`, `security/09-build-supplychain.md`, `security/14-release-diff.md`; code at `OpenUrl.swift:391-404`, `TelegramUI/BUILD:442`, `ThirdParty/cgltf/SOURCE.json:3`.

---

## Non-claims

No RCE, no code execution, no data or key access, no passcode bypass, no one-tap remote asset, no exploitation without channel control. The only in-tree memory-safety defect with an ASan proof and no crash is the skeleton over-read described above. The four `cgltf` CVEs belong to their upstream reporters (HaiND, Asilbek Muhammadiyev, Ana Kapulica); see the README for NVD links.

Source: `THREAT-MODEL.md` §5–6, `CHAINS.md` §2–5.
