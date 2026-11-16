# Security policy

Two different things can go wrong here, and they go to two different places.

| If you found a problem in… | Report it to | Where |
|---|---|---|
| This repository — wrong numbers, misquoted code, a broken link, an over-strong claim, an unsafe script | the maintainer | GitHub private vulnerability reporting, or e-mail below |
| Telegram-iOS itself — the companion screen, the GLTF path, the trust model | the vendor | `security@telegram.org` |

This repository is an independent review. It is not Telegram and cannot fix
Telegram. Please do not send vendor issues to the address below and expect a
patch; it will be forwarded at best.

## 1. Reporting a problem in this repository

Contact: **Kkuwkl@users.noreply.github.com** (noreply address, monitored)
Subject prefix: `[tg-companion-audit]`

Preferred channel: GitHub → *Security* tab → *Report a vulnerability* (private
advisory). It keeps the thread private until a fix exists and gives you a place
to attach a patch. For non-sensitive corrections — a typo, a dead link, a number
that drifted — a normal GitHub issue is fine and preferred, so the fix is
visible.

What is in scope:

- a factual error: a number that does not match `FACTS.md`, a line range that
  does not point at the quoted code, a revision hash that is wrong;
- a citation or attribution error: missing credit, wrong license, wrong author;
- a claim that overstates impact — the report deliberately says "no RCE, no
  code execution, no access to messages or keys", and a sentence that implies
  otherwise is a bug;
- a broken or malicious link, a script in `scripts/` that misbehaves;
- accidental disclosure: a local path, a token, a screenshot with an account
  identifier, a working payload that should not be public.

Response expectations: one maintainer, best effort, no SLA. Acknowledgement
within a few days is the target; corrections to text are usually applied in the
same week. There is no bug bounty.

Please keep the first message free of exploit material — describe the problem
and the file, and ask if a payload is needed before attaching one.

## 2. Reporting a problem in Telegram-iOS

Use the vendor's official channel: **security@telegram.org**

Telegram does not operate a third-party bug-bounty platform for these reports,
so an e-mail to that address is the expected path. Practical advice:

1. First message: short description, affected version(s), and a request for the
   format they prefer. Do not attach a working payload yet.
2. Then send the technical detail — file paths, line ranges, minimal
   description of the input fields involved.
3. Ask explicitly whether they want a reproducer file. If they do, send it over
   the channel they name, not as a public attachment.

## 3. Please do not publish payloads

This applies to issues in this repository and to issues in Telegram-iOS:

- no ready-to-use `.glb` / `.bin` files, no archives of them, no base64 blobs;
- no step-by-step "send this to a channel and watch it crash" instructions
  aimed at third parties;
- no screenshots that identify an account, a phone number, or a private chat;
- no posting of a reproducer while a vendor response is pending or inside the
  90-day window described in the report's disclosure section.

The report ships *descriptions of fields* and, where useful, a generator that
produces a file locally. That is the intended level of detail: enough for a
defender to reproduce, not a packaged attack.

Reasons, briefly: the affected builds are on the App Store, the entry point is a
public URL scheme, and a payload in the open turns a hardening report into a
tool. Descriptions age well; binaries get mirrored and misused.

## 4. Coordinated disclosure and current state

- **Published 2026-11-16**, in this repository, deliberately **before any vendor
  reply**. The write-up contains field-level descriptions and no payload (see
  section 3), which is what makes publishing first defensible.
- **Vendor notified the same day** at `security@telegram.org`, with a link to
  this repository, the affected versions, and an offer of a patch and a
  reproduction spec on request.
- The 90 days that follow are the **window offered for a fix, not an embargo** —
  publication has already happened.
- No public report of these findings existed before this one: GitHub issues in
  `TelegramMessenger/Telegram-iOS`, `telegramdesktop/tdesktop`,
  `DrKLO/Telegram`, `tdlib/td` and `bugs.telegram.org` were checked on the same
  day.
- Status as of 2026-11-16: **not fixed**; `release-13.1`…`13.2` and `master`
  show no substantive change in the affected files.
- Corrections and status updates arrive as new commits. The history is not
  rewritten after publication; a fixed claim is dated, not deleted.

## 5. Scope of this document

This policy covers the artifacts in this repository: Markdown text, Mermaid
diagrams, the SVG banner, and `scripts/`. It does not cover Telegram-iOS, Apple
platform software, or the third-party libraries named in `NOTICE` — report those
to their own maintainers (upstream links are in `NOTICE`).
