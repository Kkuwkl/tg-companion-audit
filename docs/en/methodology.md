# Methodology and evidence

**Published: 2026-11-16** · Author: [nimo](https://github.com/Kkuwkl)

This review had no iPhone and no Xcode. Everything below is therefore one of two kinds of evidence: **static reading of the shipped tree**, or **a standalone harness built from the unmodified application sources** and run on x86-64. Nothing was executed on iOS, and no statement here depends on a device observation.

Paths of the form `security/…` are internal evidence identifiers; the bundle itself (harnesses, corpora, logs) is available to the vendor on request and is not published.

---

## The five stands

| Stand | What it is | Input | Instrument | Output used in the report |
|---|---|---|---|---|
| **B3** | The real `cgltf.h` compiled and driven in the application's exact call order | 2 412 deterministic mutations of the four bundled `.glb`, 36 targeted cases, 7 DoS probes, 4 valid files | clang 21.1.8 with ASan (WSL), gcc 16.2.0 with ASan+UBSan, plus a native Windows binary (Zig 0.17.1) without ASan | **12 254 executions**, 10 s timeout, **0 hangs**; 4 crashes on 720–66 244 B files, 3 of them also `0xC0000005` without ASan |
| **C01b** | Unmodified `GiftModel.cpp` + ASan at `-O2`, 400 runs of the release path | skeleton files with `joints_count` up to 512 and `inverse_bind_matrices.count` as low as 1 | ASan on Linux, `VmHWM` sampling | `heap-buffer-overflow READ of size 64` at `GiftModel.cpp:292`; **0 crashes in 400 runs**; 16 320 B over-read |
| **C02a** | Harness on unmodified `GiftModel.cpp` / `CharacterInstance.cpp` | 5 GLBs, 716–808 B, plus ASCII controls | clang 21.1.8 (WSL), two OpenSubdiv entry points stubbed and unreachable for these files | three distinct `what()` strings carrying byte `0xFF`; controls return valid UTF-8 |
| **C02b** | Independent harness, deliberately trying to falsify C02a | corrected 860–952 B samples, including the animation-binding form as an object | same toolchain, separate build and separate generator | reproduced all three paths; corrected one earlier sample; hex-level proof that the file byte reaches the exception |
| **C03** | Line-by-line emulator of `GiftModel::load` that **retains** every container, plus a `textureFor` emulator | 5 files: 2.35 MiB, 3.63 MiB, 32 MiB, 1.0 MiB, plus 65 KB and 8-image controls | C++ emulator following the source line by line; zlib decode standing in for ImageIO; `VmHWM` | 607.9 MiB, 4.0 GiB, 2115 MiB, 175.9 s; every file also re-run through the untouched B3 binary with `status:"ok"` |

The five stands are not five opinions. Each one answers a question the previous one could not: B3 measures the parser alone, C01b measures the release path for the skeleton, C02a/C02b isolate the error path, C03 measures what the application **holds after** the parser returns.

---

## What was measured with what

| Question | Stand | Method | Number |
|---|---|---|---|
| Do the upstream parser bugs reproduce in this call order? | B3 | real `cgltf.h`, mutated corpus, ASan | 4 crashes in 12 254 runs, 720–66 244 B |
| How much does disabling `cgltf_validate` cost? | B3 | same 2 412 mutations with the gate removed | 60 crashes instead of 4 |
| Is the skeleton over-read real, and does it crash? | C01b | ASan on unmodified `GiftModel.cpp`, then 400 release runs | `READ of size 64`, 0 crashes |
| Can a file put invalid UTF-8 into the error message? | C02a, C02b | two harnesses on unmodified sources, hex dump of `what()` | `… 41 FF`, `valid_utf8: FALSE` |
| Is the whole path reachable through normal gates? | C02a, C02b | `cgltf_parse` → `load_buffers` → `validate` → `require` | 716–952 B files pass every gate |
| How much memory does one file cost the process? | C03 | container-retaining emulator + `VmHWM` | 607.9 MiB / 4.0 GiB / 2115 MiB |
| How much main-thread time? | C03 | per-stage timing in the emulator | 175.9 s for 2048 skins |
| Is the amplification linear in the attacker's knob? | C03 | 1/16/128 primitives, 1/4/8/64 textures, 1/16/64/256/2048 skins | 16.6 → 89.7 → 607.9 MiB; 130.8 → 4162.9 MiB |
| Are the results artifacts of the emulator? | C03 | re-run all four files through the untouched B3 binary | `status:"ok"` on all four |

---

## B3 in detail

The vendored header is `submodules/CompanionRenderer/ThirdParty/cgltf/cgltf.h`, 205 754 bytes, byte-identical to upstream `85cd6238` (v1.15-11). It was compiled unmodified and driven through the same sequence as `GiftModel::load`: `cgltf_parse` → container checks → `cgltf_load_buffers` → `cgltf_validate` → the application's own limits.

The corpus was generated deterministically from the four bundled models: 2 412 mutations (truncation, byte flips, header fields, JSON restructuring), 36 hand-written targeted cases, 7 DoS probes, 4 valid files. Every execution had a 10 s timeout and **none hung** — the observed failures are crashes, not timeouts.

The standard path (validate on) produced 4 crashes on files of 720–66 244 bytes; 3 of them were reproduced without a sanitizer as Windows `0xC0000005`. The same corpus with `cgltf_validate` removed produced 60 crashes. That ratio is the measure of what one line at `GiftModel.cpp:163` is currently buying.

MSVC was not available: the installed Visual Studio 2022 Community had no C++ workload — the MSVC toolchain directory, `vcvars64.bat` and `cl.exe` were absent. This is a tooling limitation, not a claim about Windows behaviour — the native binary was built with Zig instead.

---

## C01b in detail

The driver includes the **unmodified** `Core/GiftModel.cpp` and `Core/Math.hpp`; the only substitution is the two OpenSubdiv entry points, which are unreachable for files without a `GIFT_subdivision` extension. Build: ASan plus `-O2`, i.e. the release path with instrumentation.

Two results matter:

1. **The defect is real.** `joints_count = 256`, `inverse_bind_matrices.count = 1`: `std::copy_n(binds.data() + j*16, 16, …)` walks 16 320 bytes past a 64-byte allocation. ASan reports `heap-buffer-overflow READ of size 64 … 0 bytes after 64-byte region`, allocation at `:289`, read at `:292`.
2. **The effect is visual, not a crash.** 400 release-mode runs, including files with 512 skins, produced **0 crashes**. With finite garbage the camera collapses (`radius = 0.001`, `distance = 0.0035`, `far = 0.1`); with infinite sentinel bounds the frame is empty. An earlier hypothesis that the radius becomes `NaN` was falsified: `Bounds::add` in `Math.hpp:68` discards NaN. The crash probability estimated by an earlier pass (10⁻³…10⁻²) is an upper bound, not an observation — we report 0/400.

We keep both numbers in the report because they answer different questions: the defect is proven, the DoS is not.

---

## C02a and C02b in detail

C02a builds the shortest trigger and works upward; C02b is the adversarial re-check, built separately with a separate generator.

**What both establish.** The C++ half of the chain is executed on unmodified application code: a structurally valid GLB reaches the target `require`, `std::runtime_error` stores the raw bytes, and `what()` returns a string that fails a strict RFC 3629 check. Messages observed: `Duplicate node identifier: A\xff` (`CharacterInstance.cpp:15`), `Socket node is missing: A\xff` (`:74`), `Animation node is missing: A\xff` (`:25`). ASCII controls produce valid strings and normal errors — the difference is exactly one byte.

**Where they disagree, and what we publish.** C02a's animation sample wrote `GIFT_animation_binding` as a bare string; that path aborts earlier with the valid message "Invalid render profile JSON", so the sample did not prove what it claimed. C02b reproduced the correct form — an object, `{"version":1,"node":"A\xff"}` — and published that. The text conclusion of C02a was right; its evidence file was not.

**What neither establishes.** The Foundation half: `+[NSString stringWithUTF8String:]` returning `nil`, and the dictionary literal raising `NSInvalidArgumentException`. There is no macOS or iOS Foundation on this host. Both are documented contracts (failable initializer; `init(objects:forKeys:count:)` raises on `nil`), and the check is two lines of ObjC on a Mac. We state this as documented behaviour, not as an executed result, everywhere it matters.

---

## C03 in detail

The B3 harness frees each temporary object immediately, so it structurally cannot see memory that the application keeps. C03 is a second harness that follows `GiftModel::load` line by line and **retains** every container the application retains; a separate emulator stands in for `textureFor` (Metal and ImageIO do not exist on Linux), modelling the content-keyed cache, the RGBA8 allocation and the eviction that does not free.

Four independent mechanisms were measured, and all four files were then re-run through the untouched B3 binary in `app` mode: `status:"ok"`, `parse/load/validate = 0`. In other words, none of them is a file the application would reject early.

Two results are corrections rather than confirmations, and both are published as such:

- **Textures:** 64 `images[]` pointing at one `bufferView` decode **once** (65 004 B → 126.6 MiB), because the cache key is the payload. The 4 GiB figure requires 64 **distinct** payloads (3.63 MiB of file). The original formulation was wrong; the corrected one is cheaper for an attacker.
- **Skins:** peak RSS is 67.0 MiB, not "64 MB + 16 MB for `isfinite`" — `isfinite` allocates nothing. The cost is 131 GB of sequential allocate/free churn and 175.9 s of main-thread time. This is the case where a memory budget would never fire.

---

## Code integrity

All harnesses compiled the checked-in sources, not rewritten copies. Short SHA-256 prefixes recorded at build time:

| File | Prefix |
|---|---|
| `Core/GiftModel.cpp` | `A2953C7F1B608FD1` |
| `Core/CharacterInstance.cpp` | `D39B59485BF422C4` |
| `Sources/CompanionRenderer.mm` | `ED2E92978830ADF7` |
| `ThirdParty/cgltf/cgltf.h` | `9D570D219201F9D0` |

`git diff --stat 44681a28 -- submodules/CompanionRenderer submodules/TelegramUI/Components/DebugCompanionScreen` reports only `DebugCompanionScreen/BUILD` (+38, the "Fix build" commit). Every source file used by the harnesses is byte-identical to both the source commit and the audited master tree.

---

## Reproducing this without the bundle

The published text is sufficient to rebuild the inputs, and deliberately not sufficient to run them:

1. Build a GLB 2.0 container with one triangle, `extras.giftAsset.kind = "model"`, and two nodes whose `extras.giftNode.id` is the same byte pair `41 FF`.
2. Compile `Core/GiftModel.cpp` and `Core/CharacterInstance.cpp` unmodified; stub the two OpenSubdiv entry points; call `AssetLibrary::load` and print `what()` with a strict UTF-8 check.
3. For the amplification numbers, follow `GiftModel::load` and retain every container; measure `VmHWM` at the end of each stage.
4. For the parser crashes, compile the vendored `cgltf.h` under ASan and drive it in the order used by `GiftModel.cpp:156-163`.

A reproduction spec, the harness sources and the exact corpus are available to the vendor on request.

---

## Limits

| Limit | Effect on confidence |
|---|---|
| No iOS device, no Xcode | Device-specific behaviour (jetsam thresholds, Metal accounting, A-series timings) is not measured; arithmetic transfers, thresholds do not |
| The App Store IPA was not inspected | "The code is in the shipped binary" follows from the Bazel graph and linking rules, not from `nm`/`otool` |
| `-DNDEBUG` inferred from `-c opt` | Standard Bazel behaviour; no explicit flag for this target in the tree |
| Foundation link not executed | Documented API contracts, verified by code reading only |
| Fuzzing was structural, not coverage-guided | 2 412 mutations can miss branches; the count is a floor, not a ceiling |
| No full-tree `git grep` (partial clone) | "No other mentions" rests on code search plus targeted checks |
| Channel ownership not established | Who can post to `@tttt3dexample` is not decidable from code; the finding is about the trust anchor, not about a person |

Confidence, by claim: **high** — the code is in the release, the three parser CVEs reproduce, the error-path crash mechanism, the four amplification numbers, the username-only catalog. **Medium** — the Foundation half of Finding 1, the pre-gate subdivision cost (reachability proven, volume not measured). **Low / not claimed** — any device-specific crash rate, any user-impact estimate.

---

## Non-claims

No RCE, no data access, no passcode bypass, no one-tap remote asset, and no exploitation without control of the channel or the username. The skeleton over-read is reported as a proven ASan defect with a visual effect and 0/400 crashes, not as a DoS. The upstream CVEs belong to their reporters; this work documents deployment, not discovery of the parser bugs.

Source: `security/13-cgltf-empirical.md` (B3), `security/verify/C01b.md`, `C02a.md`, `C02b.md`, `C03.md`; `CHAINS.md` §2–5.
