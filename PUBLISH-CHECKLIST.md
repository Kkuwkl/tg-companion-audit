# Publish checklist

Practical, in order. Target state: **public** repository
`github.com/Kkuwkl/tg-companion-audit`, author line **nimo**, published
2026-11-16.

## 0. Ground rules, stated honestly

- GitHub allows **one account per person**. A pseudonymous account is allowed;
  creating extra accounts to evade a ban, to boost a repository, or to
  impersonate someone is not. `Kkuwkl` is the account used here, and the display
  name `nimo` is a pseudonym, not a claim to be another person or an
  organisation.
- "Anonymous" here means: **no real name, no real e-mail address, no employer,
  no location** in commits, files, or profile. It does not mean evading GitHub's
  terms, and it cannot hide a determined reader — commit metadata, writing
  style, and timing are all correlatable.
- The noreply address is the mechanism: `Kkuwkl@users.noreply.github.com`
  (GitHub's own form) keeps the real mailbox out of the object database
  permanently, which is the part that matters — history is hard to rewrite
  after the fact.
- No claim of affiliation with Telegram anywhere. `NOTICE` carries the explicit
  line, `docs/assets/banner.svg` carries no Telegram mark.

## 1. Content: what must not be in the tree

- [ ] No `evidence/` directory, no raw captures, no `*.glb`, no `*.bin`, no
      archives or base64 of payloads. `SECURITY.md` promises this; the promise
      has to hold on day one.
- [ ] No internal working files: `FACTS.md` is the canonical-numbers sheet for
      the authors, including the "do not claim publicly" list. It stays local.
      It is listed in `.gitignore` — verify with `git status --ignored`.
- [ ] No screenshots with account names, phone numbers, message previews, device
      names, or a logged-in Telegram UI.
- [ ] No local clone paths, no build roots, no machine names, no IDE project
      files (`.idea/`, `.vscode/`, `*.xcworkspace` of a local checkout).
- [ ] Every number in the report matches `FACTS.md` exactly. Rounding "for
      effect" is a factual error, and errors are what a hostile reader will use
      to dismiss the whole document.
- [ ] Claims stay inside the non-claims list: no RCE, no code execution, no
      access to messages, keys, camera, microphone, no passcode bypass, and no
      "one tap to someone else's model".

## 2. Identity in git metadata

Set before the first commit, not after:

```bash
git config user.name "nimo"
git config user.email "Kkuwkl@users.noreply.github.com"
git config user.useConfigOnly true
```

- [ ] `git config user.name` and `git config user.email` show exactly the two
      values above (locally and with `--global` checked once).
- [ ] One commit only: `Initial public report`. A single commit has no
      intermediate tree to leak drafts, and no second author identity.
- [ ] Author and committer are both `nimo <Kkuwkl@users.noreply.github.com>`:

      git log --format='%h %an <%ae> | %cn <%ce>'

- [ ] No real mailbox anywhere in the history:

      git log --format='%ae %ce' | Sort-Object -Unique

- [ ] Commit dates are honest but not chatty: `git log --format='%ai %ci'`.
      A commit stamped in an unusual timezone is a small hint; if it matters,
      normalise with `GIT_AUTHOR_DATE` / `GIT_COMMITTER_DATE`.
- [ ] No GPG/SSH signing key attached for this push. A signing key is a stable
      public identifier and often carries a real name — skip `-S`, unsigned
      commits are fine for a report.
- [ ] `gh auth status` shows the `Kkuwkl` account, not a personal one.

## 3. Path and text hygiene

- [ ] Placeholder author and placeholder mailbox are gone from all Markdown:

      Select-String -Path *.md,docs\*.md -Pattern 'contact@example\.com','Independent\s+security\s+research'

- [ ] No drive-letter absolute paths in any tracked text file:

      Select-String -Path * -Pattern '[A-Za-z]:\\' -Recurse

      (expect hits only in `.git/`, which is not published)
- [ ] No absolute home directories, no `file://` URLs, no UNC shares.
- [ ] No e-mail addresses other than the noreply one; no phone numbers.

## 4. Automated pass

```bash
python scripts/check_repo.py
```

Covers broken relative links, drive-letter paths, `.glb`/`.bin` artifacts,
Markdown tables with inconsistent column counts, clickbait words in headings, and
leftover placeholder identity in `*.md`. Expected output: `0 problems`. Run it
from the repository root, then again with `--verbose` if anything fails.

- [ ] Exit code 0.
- [ ] Mermaid blocks render: open `docs/diagram.md` in a scratch private repo or
      in the GitHub preview before publishing — GitHub's preview of a local file
      does not render Mermaid, the pushed file does.
- [ ] `docs/assets/banner.svg` renders at 1280x320 with no external font, image,
      or logo reference:

      Select-String -Path docs\assets\banner.svg -Pattern 'href=','xlink','<image','url\(http'

## 5. Create and publish

From the repository root, with `gh` authenticated as `Kkuwkl`:

```bash
git init -b main
git add -A
git commit -m "Initial public report"
gh repo create tg-companion-audit --public --source=. --remote=origin --push
gh repo view --web
```

Notes:

- `git init -b main` only if the directory is not a repository yet; otherwise
  `git branch -M main` before the commit.
- `--public` from the start: the report is meant to be readable immediately and
  the content was reviewed before the push. There is no private pre-flight
  window, so everything in section 1 must already be true.
- `--source=. --remote=origin --push` creates the repo, adds the remote, and
  pushes `main` in one step. Do not add a second remote.
- If the push is rejected, check `gh auth status` before anything else.
- `gh repo view --web` is the first read: look at the rendered README, the
  banner, both Mermaid diagrams, and the license badge.

## 6. Immediately after publication

- [ ] Enable private vulnerability reporting: *Settings* → *Code security* →
      *Private vulnerability reporting* → Enable. `SECURITY.md` points at it.
- [ ] Add topics: `security-research`, `ios`, `gltf`, `supply-chain`,
      `telegram-ios`.
- [ ] Set the repository description to the positioning line, no adjectives:
      "A hidden production screen in Telegram-iOS that feeds a vendored GLTF
      parser from a mutable channel."
- [ ] Disable nothing that matters: keep Issues on (corrections arrive there),
      keep Discussions off unless moderated.
- [ ] Send the vendor note the same day: `security@telegram.org`, short, with
      the repository URL and an explicit "no payload attached, none will be
      published". Publishing first is a deliberate choice — the report contains
      a description, not a weapon — but the vendor should hear it from you, not
      from a timeline.
- [ ] Watch for a reply for 90 days; any correction goes in as a new commit, not
      as a history rewrite.

## 7. Do not

- [ ] Do not push a reproducer file, a hex dump, or "just for maintainers" branch
      with one. Branches are public too.
- [ ] Do not add a second remote pointing at a mirror that carries what the main
      repo refuses to carry.
- [ ] Do not @-mention Telegram developers, security staff, or the CVE authors in
      issues or commits.
- [ ] Do not rewrite history after the push to remove an accidental leak — a
      force-push hides nothing on a public forge, and the `git log` of a
      rewritten repo is itself a signal. Rotate/remove the content, say so, move
      on.
- [ ] Do not tag the repository in link aggregators with wording the report
      itself avoids ("critical", "0-day", "RCE", "hack").

## 8. Sign-off

| Check | Owner | State |
|---|---|---|
| Content clean (section 1) | R3 | pass, 2026-11-16 — no artifacts, no paths, no placeholders |
| Identity clean (section 2) | R3 | pass — `nimo <Kkuwkl@users.noreply.github.com>`, one commit, no remote |
| Paths and links clean (section 3) | R3 | pass — 15 tracked files, zero hits |
| `check_repo.py` exit 0 (section 4) | R3 | pass — `problems: 0` |
| README license line matches `LICENSE` | R1/R2 | **open** — README says "MIT", LICENSE is dual (prose CC BY 4.0, code MIT) |
| NOTICE linked from README | R1/R2 | **open** — attribution file exists but is not in the repository map |
| README/README.ru reviewed by a second reader | R1/R2 | pending |
| Vendor note sent | owner | pending |
