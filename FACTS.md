# Fact sheet / Факт-лист

Canonical numbers used across this repository. Every item is traceable to the audited tree
`24638bc69bd083981b178dd1e7f921eebbf7fc46` or to a harness described in
[`docs/en/methodology.md`](docs/en/methodology.md) / [`docs/ru/methodology.md`](docs/ru/methodology.md).

---

## Позиционирование / Positioning

**RU:** Скрытый экран в production-сборке Telegram-iOS, который кормит вендоренный GLTF-парсер контентом из изменяемого канала.

**EN:** A hidden production screen in Telegram-iOS that feeds a vendored GLTF parser from a mutable channel.

Hardening / supply-chain review. No code execution, no data access, no passcode bypass.

---

## Затронутые версии / Affected versions

| Item | Value |
|---|---|
| Application | Telegram-iOS, App Store: `release-13.1` (2026-10-20), `13.1.1` (10-22), `13.1.2` (10-28), `13.2` (11-03) |
| Not affected | `release-13.0.0` (2026-10-07) and earlier; Telegram Android; Telegram Desktop; TDLib |
| Source commit | `44681a28ee4ad9792f6447a681e615a997af5323` "Experiment", 2026-10-12 16:56:23 +0400, 117 files, +46 268/−2 |
| Follow-up | `a8cc2ed228…` "Fix build", +38 lines, `DebugCompanionScreen/BUILD` only |
| `cgltf` | `85cd62382dfea638278962690cf515023f33ed00` = v1.15-11, byte-identical to upstream |
| OpenSubdiv | `9dab8a47` = Release 3.7.0, 72/72 files byte-identical |
| Fix status | Not fixed as of 2026-11-16; zero substantive changes across `13.1` … `13.2` / `master` |

---

## Что входит в публичную версию / What is covered

1. **Error-path crash / Краш в обработке ошибок.** `Sources/CompanionRenderer.mm:13` converts `ex.what()` with `[NSString stringWithUTF8String:]` inside an `NSDictionary` literal. One invalid UTF-8 byte in `giftNode.id`, `giftSlot`, `sockets[].node` or `GIFT_animation_binding.node` yields `nil`, the literal raises `NSInvalidArgumentException` inside the C++ `catch`, and the process dies. Deterministic; file 716–952 bytes; no CVE involved.
2. **Resource amplification / Амплификация.** Inputs that pass every shipped gate:
   - indices: **2.35 MiB → 607.9 MiB** CPU (+≈1.23 GB GPU), 1.6–2.0 s;
   - 64 distinct PNGs: **3.63 MiB → 4.0 GiB**, 16 s;
   - `images[]` over one buffer view: **32 MiB → 2115 MiB**, memcpy 1.89 s;
   - skins: **1.0 MiB → 175.9 s** on the main thread at a 67.0 MiB peak.
3. **Trust model / Модель доверия.** The catalog is resolved by the string `"tttt3dexample"` — no `peerId`/`accessHash` pin, no `case .channel`, no content hash; only the `.glb` suffix and a 32 MiB cap; resolve cache 48 h.
4. **Process / Процесс.** 46 268 added lines in one commit, no pull request, no tests, no fuzz target; the commit did not build on its own; the feature then shipped unchanged.

---

## Что публично НЕ утверждать / Non-claims

- No RCE, no code execution, no access to messages, keys, camera or microphone, no passcode bypass.
- No "one tap to a remote `.glb`": chip 1 is the bundled model; network content is a second tap on a chip whose label is a digit.
- Exploitation requires control of the channel or the username; otherwise the only outcome is self-DoS.
- CVE-2026-112018 / 112019 / 32845 / 75148 belong to HaiND, Asilbek Muhammadiyev and Ana Kapulica; they are upstream `cgltf` issues, not this repository's findings.
- The skeleton over-read (`inverseBindMatrices`) is proven by ASan on unmodified code, but produced 0 crashes in 400 release-spec runs; its observed effect is a broken frame, not a process kill.

---

## Ремедиация / Remediation

1. Nil-safe `errorFor` + UTF-8 validation of identifiers (`CompanionRenderer.mm:13`, `GiftModel.cpp:74`) — see [`docs/patch.diff`](docs/patch.diff).
2. `require(inverse_bind_matrices == nullptr || count >= joints_count)` before the skeleton loop (`GiftModel.cpp:286`).
3. Limits on `sparse->count`, `stride`, `byteOffset`, `skins_count`, `Σ images[]`; a budget for `nFaces·4^level` before `RefineAdaptive`.
4. Pin `peerId` + `accessHash`, require a channel, allowlist `(documentId, sha256)`.
5. `#if DEBUG` / remote flag, or an explicit product decision for the hidden screen.

---

## Раскрытие / Disclosure

Reported to `security@telegram.org` on 2026-11-16. Public write-up published the same day; no public reports were found in the GitHub issue trackers of `TelegramMessenger/Telegram-iOS`, `telegramdesktop/tdesktop`, `DrKLO/Telegram`, `tdlib/td` or on `bugs.telegram.org`. No binary payloads are published; the reproduction spec is available to the vendor on request.

---

## Источники / Sources

- [`README.md`](README.md), [`README.ru.md`](README.ru.md) — findings and scope
- [`docs/en/findings.md`](docs/en/findings.md), [`docs/ru/findings.md`](docs/ru/findings.md) — detail and code excerpts
- [`docs/en/methodology.md`](docs/en/methodology.md), [`docs/ru/methodology.md`](docs/ru/methodology.md) — five stands and limits
- [`docs/en/vendor-report.md`](docs/en/vendor-report.md) — the report sent to Telegram
