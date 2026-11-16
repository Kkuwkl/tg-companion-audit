# Diagrams

Rendered by GitHub from the Mermaid sources below. Numbers and paths match
`FACTS.md`; both diagrams are descriptive, not executable.

## 1. Data flow: from deeplink to Metal

```mermaid
flowchart TD
    A["tg://companion<br/>opened by any app, message or browser"] --> B{"OpenUrl.swift:395-404<br/>scheme is 'tg' and host is 'companion'"}
    B -->|no match| Z["normal Telegram UI"]
    B -->|match| C["DebugCompanionScreen<br/>no #if DEBUG, no runtime flag, no testonly"]
    C --> D["resolvePeerByName 'tttt3dexample'<br/>no peerId pin, no accessHash pin, no case .channel"]
    D --> E["public channel post<br/>catalog entry"]
    E --> F["attachment fetch<br/>filter: .glb suffix and 32 MiB cap"]
    F --> G["local cache<br/>TTL 48 h"]
    G --> H["CompanionRenderer.mm / GiftModel.cpp<br/>cgltf parse, texture and skin decode"]
    H --> I["OpenSubdiv RefineAdaptive<br/>budget nFaces * 4^level"]
    I --> J["Metal buffers, GPU submit"]
    H -.->|"invalid UTF-8 in id, slot or socket"| K["stringWithUTF8String: returns nil<br/>NSInvalidArgumentException inside a C++ catch"]
    K -.->|"zero @try blocks, no uncaught handler"| L["process crash<br/>file size 716-952 bytes"]
```

Stages: URL match, screen, peer lookup, attachment, parse, refine, render. The
dashed path is the failure branch from Finding 1; the four amplification
measurements of Finding 2 enter at `cgltf parse` and `RefineAdaptive`.

## 2. Trust model: four sources, one boundary

```mermaid
flowchart TB
    subgraph REVIEW["reviewable: built, pinned or signed"]
        direction TB
        A1["1 - app bundle<br/>bundled .glb models, fixed at build time"]
        A2["2 - vendored libraries<br/>cgltf 85cd623 (v1.15-11), OpenSubdiv 9dab8a47 (3.7.0), LTC"]
        A3["3 - companion code<br/>OpenUrl.swift:395-404, DebugCompanionScreen, GiftModel.cpp"]
    end
    A4["4 - channel content<br/>@tttt3dexample by username, no pin<br/>bytes, 32 MiB cap, 48 h cache"]
    P["companion pipeline<br/>parse, validate, refine, render"]
    A1 --> P
    A2 --> P
    A3 --> P
    A4 -.->|"trust boundary"| P
    style A4 stroke:#f85149,stroke-width:2px,stroke-dasharray:6 4
```

Sources 1-3 are reviewable artifacts: built, pinned by commit, or code-signed,
so a reader can diff them against a known revision. Source 4 is not an artifact
at all — it is whatever the channel owner posted, resolved by *name* at runtime.
The red edge is the trust boundary: bytes cross it on the strength of a username
lookup, with no `peerId` + `accessHash` pin, no `case .channel` check, and a
`GiftModel.cpp` filter that tests only the `.glb` suffix and a 32 MiB cap. The
48-hour cache means a warm client keeps reading the peer it already resolved
while a cold client switches to whatever the name points at now.
