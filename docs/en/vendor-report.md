# `tg://companion` in Telegram-iOS 13.1–13.2 — error-path crash, resource amplification, username-addressed asset catalog

**To:** security@telegram.org · **From:** nimo / https://github.com/Kkuwkl · **Date:** 2026-11-16

## 1. Summary

- `tg://companion` opens a hidden 3D component screen that parses `.glb` files fetched from a public channel at runtime. It ships in App Store builds 13.1, 13.1.1, 13.1.2 and 13.2, with no debug gate.
- **Finding 1 — error-path crash.** A 716–952 byte `.glb` that the app rejects for a non-UTF-8 identifier terminates the process while that rejection is being reported. `Sources/CompanionRenderer.mm:13` converts `std::exception::what()` with `+[NSString stringWithUTF8String:]`; a nil in a dictionary literal raises `NSInvalidArgumentException` inside the C++ `catch`. Deterministic; no memory or timing dependency.
- **Finding 2 — resource amplification.** Four inputs that pass every existing limit, and are accepted by an unmodified build: 607.9 MiB peak from 2.35 MiB, 4.0 GiB from 3.63 MiB, 2.0 GiB from 32.0 MiB, and 175.9 s on the main thread from 1.0 MiB.
- **Finding 3 — catalog trust.** The asset source is a mutable username, with no check that the peer is a channel, no document pin, and a 48-hour resolve cache (`Components/DebugCompanionScreen/Sources/CompanionCatalog.swift:59-91`).
- All three require control of the catalog channel or the username, plus the user opening the link and selecting a network preset. No RCE, no data access. `patch.diff` contains the two minimal fixes from §7.
- Public write-up: https://github.com/Kkuwkl/tg-companion-audit (no binary).

## 2. Affected versions

| Version | Released | Contains `tg://companion` |
|---|---|---|
| 13.0.0 | 2026-10-07 | no |
| 13.1 | 2026-10-20 | yes |
| 13.1.1 | 2026-10-22 | yes |
| 13.1.2 | 2026-10-28 | yes |
| 13.2 | 2026-11-03 | yes |

One commit, `44681a28` ("Experiment", 2026-10-12, 117 files); 114 companion and renderer paths are byte-identical across 13.1 … 13.2 and master `24638bc69b`. No `#if DEBUG`, runtime flag or `testonly`: the renderer is in the release link graph.

**Scope note.** Not a CVE report: CVE-2026-112019, CVE-2026-75148 and CVE-2026-32845 belong to the `cgltf` authors and are already public. What follows is how Telegram's code exposes that parser, bounds its resources and reports its errors.

## 3. Finding 1 — the error path crashes the app (716–952 B)

`Sources/CompanionRenderer.mm:13` is the only `std::string` → `NSString` conversion in the module:

```objc
NSError *errorFor(const std::string &message) { return [NSError errorWithDomain:@"Companion" code:1 userInfo:@{NSLocalizedDescriptionKey:[NSString stringWithUTF8String:message.c_str()]}]; }
```

`what()` is not guaranteed to be valid UTF-8, and here it is assembled from asset-controlled strings: node ids, socket names, animation target ids, material slots. Seven throw sites (`Core/CharacterInstance.cpp:15,25,37,74,165,172,189`) concatenate those identifiers into the message. The JSON reader bounds identifiers to 256 bytes and rejects backslashes (`Core/GiftModel.cpp:71-74`) but not invalid UTF-8, so one `0xFF` byte in a node id survives parsing, `cgltf_validate` and the component-kind check.

The failure then happens in the reporting path:

1. `AssetLibrary::load` builds the node map for a model component (`Core/CharacterInstance.cpp:73`); a duplicate id throws `std::runtime_error("Duplicate node identifier: A\xff")` (`:15`).
2. `catch (const std::exception &ex)` at `CompanionRenderer.mm:175` calls `errorFor(ex.what())` (four call sites: `:89`, `:157`, `:175`, `:213`).
3. `+[NSString stringWithUTF8String:]` returns `nil` for invalid UTF-8. A `nil` value in an `NSDictionary` literal raises `NSInvalidArgumentException`.

`catch (const std::exception &)` does not help here, because the Objective-C exception is raised *inside* the handler, after the C++ exception has already been caught: C++ handlers do not catch `NSException`, Swift `do/catch` only receives `NSError` from throwing Objective-C methods, the companion sources contain no `@try`, and no `NSSetUncaughtExceptionHandler` is installed for this path (0 occurrences). The process terminates — no toast, no error UI, no log. The file was rejected correctly; the crash is in saying so.

Evidence: the C++ half is reproduced with unmodified `GiftModel.cpp` and `CharacterInstance.cpp` and the shipped call order, up to and including `errorFor`. The last step is the documented Foundation contract, checked with two lines of Objective-C on macOS; not run on an iOS device.

## 4. Finding 2 — resource amplification inside the existing limits

The limits are per object and the products are unbounded: 32 MB file (`Core/GiftModel.cpp:152`), 1,000,000 elements per accessor (`:18`), 2,048 nodes (`:157`), 64 images / 128 materials (`:170`), 1,200,000 indices per primitive (`:322`), 128 primitives (`:388`), 200,000 vertices (`:317`), 256 joints per skin (`:288`) — but no `skins_count` limit and no budget for the sum of indices, pixels or `images[]`.

| # | Input (accepted by the shipped gates) | Measured effect |
|---|---|---|
| 1 | 2,460,632 B (2.35 MiB); 128 primitives sharing one `{"indices":0}` buffer view | peak 607.9 MiB; 585.9 MiB of index storage (153.6 M indices); ≈1.23 GB GPU; 1.62–2.02 s |
| 2 | 3,806,732 B (3.63 MiB); 64 distinct PNG images | 4,294,967,296 B decoded (4.0 GiB); peak 4,162.9 MiB; 15.99 s |
| 3 | 33,554,432 B (32.0 MiB — exactly the file gate); 64 `images[]` entries over one buffer view | 2,147,202,304 B in `images[]` (2.0 GiB); peak 2,115.3 MiB; 1.89 s of `memcpy` |
| 4 | 1,053,600 B (1.0 MiB); 2,048 skins | 175.871 s on the main thread (85.9 ms per skin); peak RSS only 67.0 MiB; 131 GB allocation churn |

Measured with a line-accurate model of `GiftModel::load` and the texture path on x86_64; each input was also accepted by an unmodified parser build. Not measured on iOS: the arithmetic is platform-independent, jetsam thresholds are not. Row 4 needs only time; the load is synchronous on the main thread (`DebugCompanionScreen.swift:308-403`).

## 5. Finding 3 — the catalog is addressed by a mutable username

`CompanionCatalog.swift:59` resolves the literal name `tttt3dexample`; `:62-67` accepts whatever peer the resolver returns and passes only `peer.id` onward. Nothing checks that the peer is a channel, that the account is a member, or that the peer is the one the build was tested against. `:85-91` dedupes by file name and lets the most recent message win.

The resolver caches name → peer for 48 hours (`ageLimit = 2 * 60 * 60 * 24 = 172,800`, `ResolvePeerByName.swift:16,31`), and the username is not part of the peer address (`peerId` + `accessHash`). Consequences: a renamed and re-registered username silently changes the code source for cold clients, while warm clients keep the old peer for up to 48 h; with the peer type unchecked, an open-posting group or a user account holding `.glb` in direct messages is a catalog too; and re-uploading a file under an existing name replaces a component with no visible UI change — no `documentId`, no hash, no signature, only the `.glb` suffix and the 32 MB gate.

This is the actual trust boundary of the feature: untrusted bytes reach a native parser in a store build, selected by a string that can change hands.

## 6. Why this matters, and why it does not matter more

Everything above needs one of two preconditions: control of the catalog channel, or possession of the username (plus up to 48 h for warm clients). Without either, a user cannot reach any of these paths: the deep link takes no parameters (no URL, path or channel name), local files are not read, and the first screen always shows a bundled model.

We did not find remote code execution. The one out-of-bounds write we could construct in the vendored parser is gated by `cgltf_validate` (`Core/GiftModel.cpp:163`) and is unreachable in the shipped call order; it would become reachable only if that call were removed or reordered. We did not find data access or exfiltration: the new code has no network client of its own, no logging, no disk writes, and no account, message or key material reaches the renderer.

What remains is a deterministic process kill from a sub-kilobyte file, memory and main-thread pressure up to multi-gigabyte scale from single-digit-megabyte inputs, and misleading labels on a screen that does not identify itself as debug. That is hardening with a real availability component, not a compromise.

## 7. Suggested remediation

1. **Make the error path nil-safe** — `initWithBytes:length:encoding:` with a Latin-1 fallback and a byte-count fallback instead of `stringWithUTF8String:` in a literal (`patch.diff`, hunk 1). Also validate UTF-8 in `ProfileJSON::string` (`Core/GiftModel.cpp:74`) so identifiers are text by construction.
2. **Check inverse bind matrices before reading them** — `require(inverse_bind_matrices == nullptr || count >= joints_count)` before the skeleton loop at `Core/GiftModel.cpp:286` (`patch.diff`, hunk 2). The missing check allows a 16,320-byte heap over-read on a malformed skin (ASan, unmodified code; 0 crashes in 400 release-spec runs, so this is a correctness fix).
3. **Budget before allocating** — total indices, total texture pixels, `Σ images[]` buffer views, `skins_count`, one global allocation ceiling; reject the file as a whole (`Core/GiftModel.cpp:18,170-177,286,317-388`).
4. **Pin the asset source** — `peerId` + `accessHash`, peer must be a channel, allowlist `(documentId, sha256)` per catalog name (`CompanionCatalog.swift:59-91`).
5. **Treat the parser as a maintained dependency** — `cgltf.h` is pinned at `85cd623` (2026-02-02) and has not moved; the CVEs above are inherited from it. Add ASan and a fuzz target on `GiftModel::load` to CI.

Separately, `tg://companion` is a debug surface reachable unconditionally from any link (`OpenUrl.swift:395-404`); whether it should ship is a product decision we are not making for you.

## 8. Reproduction

Policy: we describe the input in text and do not attach it. **The binary is available to the vendor on request.**

The trigger is a valid GLB of 716–952 bytes: two nodes whose `extras.giftNode.id` is the same string containing one invalid UTF-8 byte (`"A\xff"`), one mesh with POSITION and NORMAL accessors, root `extras.giftAsset = {"version":1,"kind":"model"}`. It passes the size gate, GLB header/version/length checks, `nodes_count ≤ 2048`, buffer and extension checks, `cgltf_load_buffers`, `cgltf_validate` and the component-kind check; it fails only at `CharacterInstance.cpp:15`, when the duplicate id is formatted into a `std::string`. The four measurement inputs from §4 are also available on request.

## 9. Disclosure status

- A public write-up is already available at https://github.com/Kkuwkl/tg-companion-audit (published 2026-11-16). We are sending this report the same day so that you have the technical detail, the patch and the reproduction spec directly.
- We are not planning to publish the reproduction binary or the measurement inputs; they are available to you on request.
- We will keep the repository updated with your response and with the fix status for at least 90 days; the 90-day window is for follow-up, not an embargo.
- Before publishing we searched for existing public reports: GitHub issues in `TelegramMessenger/Telegram-iOS`, `telegramdesktop/tdesktop`, `DrKLO/Telegram` and `tdlib/td`, plus bugs.telegram.org. We found none describing these issues.
- This is not a CVE report and not a CVE assignment request. No bounty is requested; the CVE identifiers in §2 belong to the `cgltf` authors and are already public.

## 10. Contact

nimo — https://github.com/Kkuwkl. Preferred contact: GitHub issues in https://github.com/Kkuwkl/tg-companion-audit. We can provide the reproduction binary, the measurement inputs and the harness sources on request, and we are happy to test a candidate build.
