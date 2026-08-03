# Language-Aware ACCE — Architecture

**Status:** FROZEN · **Applies to:** ACCE language dimension (English + Hindi V1, more later) · **Reference:** multilingual support

This document is the architectural reference for making ACCE language-aware.
It has been reviewed and approved. It is **frozen**: implementation follows
this document, and future features fit *into* this design rather than changing
it (see [Governance](#governance)).

The pipeline is never branched by language; every difference flows through one
configuration object and per-language data. English and Hindi first; more
languages later without modifying any module.

**Final review incorporated:** capability-advertising TTS providers (§5),
Narrator as a voice-identity object separate from Locale (§6), a plugin-based
TTS router with graceful fallback (§7), and the Translation seam between Script
Generation and Narration (§8, not a V1 feature).

---

## 0. Goals & Non-Goals

**Goals**

- The user picks a **language** (English / Hindi) at generation time. Everything
  language-dependent adapts; everything else is untouched.
- The pipeline has **no "English mode" and no "Hindi mode"** — one code path,
  language arriving as data.
- Narration, script, subtitles, metadata, and visual search are all driven by
  one configuration object.
- Adding a language is **adding data** (a language pack), never a code change.
- The user never thinks about TTS engines, voices, or providers — the system
  resolves them. **Provider selection is data-driven over advertised
  capabilities, and TTS providers are plugins:** install one by adding its
  implementation + an API key (or local model); the router picks the best
  available provider for the language and falls back gracefully.
- **Locale (language) is independent of narrator (who speaks).** Narrator
  selection, custom voices, and voice cloning are additive features that never
  modify Locale.
- English + Hindi ship in V1; Bengali, Tamil, Telugu, French, Japanese, … plug
  in later with the same mechanism.
- Cross-language features become possible later without a redesign: bilingual
  subtitles, EN-narration + HI-subtitles, HI-narration + EN-subtitles, dubbing,
  multilingual documentaries. A **Translation seam** between Script Generation
  and Narration is the documented extension point (not a V1 feature).

**Non-goals (V1)**

- No per-scene language mixing yet (the seam is designed, see §9).
- No translation of *visual assets* or *research sources* — research stays
  internal and language-agnostic.
- No user-editable voice/engine settings — the language pack + router are
  authoritative. (A *narrator* picker is explicitly future work, §6.)
- No changes to Timeline semantics, Renderer, or Director Mode's model.

---

## 1. The single configuration object

The requirement names five language-dependent surfaces:

| Surface | What it controls |
|---|---|
| Script language | What the narration *text* is written in |
| Narration language | What the TTS *speaks* |
| Subtitle language | What text is burned into the video / written to SRT |
| Metadata language | Title, description, research summary presentation |
| Retrieval language | Language of internal visual search queries |

These live on **one object**: `Locale`. Every module that needs language reads
`Locale` (via `JobContext.locale`) — never a bare string, never a provider name,
never an `if locale == "hi"` branch.

```python
class Locale(BaseModel):
    """Single per-job language configuration. Language ONLY — no voice, no
    narrator identity. Who speaks is a separate object (§6)."""
    language: str            # user-facing primary code, e.g. "hi" (the radio value)
    script_language: str     # what narration is written in       → defaults to language
    narration_language: str  # what TTS speaks                    → defaults to language
    subtitle_language: str   # SRT/ASS burn-in text               → defaults to language
    metadata_language: str   # title / description / summary      → defaults to language
    retrieval_language: str  # visual search-query language       → defaults to "en" (see §4)
```

`Locale` is **derived, never typed in full by the user**. The user picks one
language; the registry builds the object (all dimensions collapse to the pick in
V1). `UserInput` gains exactly one field:

```python
class UserInput(BaseModel):   # existing fields unchanged
    topic: str
    instructions: list[str] = []
    duration: int | None = None
    style: str | None = None
    language: str = "en"       # ← the only addition
```

`UserInput.language` stays a plain code (what the UI sends). The rich `Locale`
is resolved once by the factory and attached to `JobContext`, so stages read
`ctx.locale` — one source of truth at runtime, never re-parsed.

### Why the five dimensions live on one object

They collapse to the same value in V1, but they are *different concerns* and
must be able to diverge. The entire cross-language future (§9) is just "make two
of these fields disagree." That is impossible with a single `language: str`.

---

## 2. Language packs (static, per-language data)

A language is a **profile** — curated data, not code. Each profile carries
everything the pipeline needs to behave correctly in that language:

```yaml
# config/languages/hi.yaml
code: hi
native_name: हिन्दी            # shown in the UI radio
english_name: Hindi
script: devanagari            # → tokenizer, punctuation, burn-in font
words_per_minute: 140         # narration pacing (speaking rate differs by language)
punctuation:                  # sentence terminators beyond .!?
  - "।"                        #   Devanagari danda
readability: none             # Flesch is English-only; see §3.2
tts_preference: [edge, stub]  # ordered provider candidates for this language
default_voice: hi-IN-MadhurNeural   # seeds the default Narrator (§6); never a Locale field
retrieval_language: en        # visual queries stay English (see §4)
burn_font: "Noto Sans Devanagari"   # ASS font-family for subtitle burn-in
```

```python
class LanguageProfile(BaseModel):
    code: str
    native_name: str
    english_name: str
    script: str                       # "latin" | "devanagari" | …
    words_per_minute: int
    punctuation: tuple[str, ...]
    readability: str                  # "flesch" | "none" (V1: hi → none)
    tts_preference: list[str]         # provider names, stub last
    default_voice: str | None
    retrieval_language: str = "en"
    burn_font: str                    # ASS font family
```

The `LanguageRegistry` owns four jobs:

```python
class LanguageRegistry:
    def profile(code: str) -> LanguageProfile          # one per installed pack
    def resolve(user_pick: str) -> Locale              # pick → 5-dimension Locale
    def default_narrator(code: str) -> Narrator        # pack.default_voice → Narrator (§6)
    def languages() -> list[LanguageProfile]           # UI radio population
```

**Adding a language = adding a YAML file.** Bengali, Tamil, Telugu, French,
Japanese: each is a new `config/languages/{code}.yaml`, registered by dropping
it in the directory. No module change, no pipeline branch.

---

## 3. Pipeline impact

| Module | Classification | What changes |
|---|---|---|
| **Research** | Lightly language-aware | Prompt gains a language directive so facts/summary match the topic's language. No new logic — a prompt field. |
| **Script Generator** | Language-aware | Prompt directive ("write narration in Hindi, Devanagari"); per-language `words_per_minute` (already a parameter — now fed from the profile); language-aware tokenizer + readability (§3.2); title/description in `metadata_language`; `ScriptOutput` carries `language`. |
| **Scene Planner** | **Unchanged** | Deterministic splitter; narration is opaque text to it. Inherits language from the script. |
| **Shot Planner** | Language-aware (queries only) | Prompt forces `search_queries` into `retrieval_language` (English), and the *visual_description* stays in the LLM's working language. |
| **Visual Retrieval** | **Unchanged (code)** | Consumes opaque `search_queries`; the cache→Pexels→Pixabay→Wikimedia→placeholder chain is untouched. Queries are made English upstream. (§4) |
| **Timeline** | **Unchanged** | Time-only; durations are *measured* (I7). Language affects pacing upstream (WPM), never the Timeline math. |
| **Music Planner** | **Unchanged** | Music intent is emotion/tempo — language-agnostic. Keyword matching stays English (best coverage). |
| **Audio — Narration** | Language-aware | `self.tts` is a **`RoutingTTSProvider`** (see §7) resolved for `narration_language`. The module calls `synthesize(text, out_path=out)` exactly as today and **never knows which provider produced the audio**. Voice comes from the `Narrator` (§6), not Locale. Text is already in `script_language`. File suffix comes from `provider.output_suffix` (replaces the `name == "edge"` check). |
| **Audio — Mix / Timeline** | **Unchanged** | Mix is volume/fades/ducking; timing is narration-measured. |
| **Audio — Subtitles** | Language-aware (data) | `build_cues` already derives text from scene narration → subtitles are in `script_language` automatically. Cues carry a language tag for the future. SRT is already UTF-8. |
| **Director Mode** | **Unchanged** | Post-production overlay on the frozen audio. The documentary's language is baked at generation; Director Mode edits music only. |
| **Renderer** | **Unchanged** | Consumes the manifest (I5, I12). Subtitle *burn-in* gets a font-appropriate ASS — the Production module picks `burn_font` when composing `subtitles.ass`; the renderer just renders the ASS it's given. |
| **Quality** | Language-aware (readability) | Flesch is English-only. `_check_script` reads a per-language readability strategy: run Flesch for `en`, skip/neutral for `hi` (no fake English scores on Devanagari). |

### 3.1 The one real bug hiding today

`modules/script/metrics.py` counts words with `[A-Za-z']+`. For Devanagari that
returns **zero** — so word count, syllable count, Flesch score, and the
`estimated_duration` (which drives pacing) are all broken for Hindi *right now*.
Fixing this is what makes `hi` viable, and it is exactly the kind of thing that
must be profile data, not a branch:

```python
# language-aware tokenizer, selected by profile
def count_words(text: str, profile: LanguageProfile) -> int:
    if profile.script == "latin":
        return len(re.findall(r"[A-Za-z']+", text))
    return len(text.split())   # Devanagari & friends: whitespace-delimited
```

### 3.2 Readability

Flesch Reading Ease / Kincaid are English-only (syllable counting, 100–0 scale).
Hindi has no syllable model in V1. `profile.readability == "none"` means the
script metrics emit `ReadabilityStats=None` and Quality **skips** the
`script.readability` check for that language — it never scores Devanagari with
an English formula. A future Hindi readability metric plugs in as profile data
(`readability: "hindi-flesch-ish"` → a registered metric), no module change.

---

## 4. Visual retrieval: English queries, with a designed native fallback

**Question:** should search queries stay English even when narration is Hindi?

**Trade-offs.**

*English-primary (Option A)*
- Stock providers are indexed by English metadata. Pexels/Pixabay tags are
  predominantly English; a Devanagari query returns near-nothing on both.
  Wikimedia Commons search is strongest in English even though its captions are
  multilingual.
- One canonical query language keeps the media cache deterministic and
  shareable: the same shot retrieves the same asset regardless of narration
  language — a consistent brand across languages.
- An LLM translating a *query* (a few words) into English is trivial and
  reliable; translating narration prose is where quality risk lives.

*Native-language-primary (Option B)*
- Captures culturally specific visual vocabulary (a festival, a local landmark)
  that English search may not surface.
- Cost: dramatically worse coverage on all three providers; cache
  fragmentation; ranking nondeterminism across languages.

**Recommendation: English-primary retrieval with a native fallback (A, plus a
retry seam).**

1. `retrieval_language` defaults to `"en"` in **every** Locale — including
   Hindi jobs. The Shot Planner's prompt states: *"search_queries must be in
   English"* (a directive, not a branch — the LLM translates the query for
   free). Visual descriptions stay in the LLM's working language.
2. The **Media module code is unchanged**: it consumes opaque `search_queries`
   through the existing chain (cache → Pexels → Pixabay → Wikimedia →
   placeholder).
3. **Designed (not built in V1) native fallback:** the Shot Planner emits an
   optional `native_queries` field (the same query in the narration language,
   for cultural recall). `DefaultMediaModule._retrieve` gains a *data-driven*
   loop — "if no satisfactory asset after the English chain, retry the chain
   with `native_queries[0]` before placeholder." This is a loop over query
   variants, **not** a `if locale == "hi"` branch, and it only fires for
   low-recall shots. Wikimedia benefits most (multilingual search).

The principle: **translation happens at the query boundary (LLM), never inside
the retrieval chain.** The pipeline's providers, ranking, and cache stay
language-blind.

---

## 5. TTS abstraction: capability advertisement

The provider contract is a thin, stable seam. Providers **advertise** what they
can do; the router (§7) selects from that data. The pipeline-facing call shape
never changes.

```python
class VoiceSpec(BaseModel):
    id: str                          # "hi-IN-MadhurNeural"
    language: str                    # "hi"
    name: str | None = None          # "Madhur" (UI label, future)
    gender: str | None = None
    styles: list[str] = []           # per-voice style tags, if supported
    local: bool = False              # bundled/offline-capable voice

class TTSCapabilities(BaseModel):
    languages: set[str]              # what the provider can speak
    voices: list[VoiceSpec]          # catalog the router can surface
    streaming: bool = False          # incremental audio output
    emotion_control: bool = False    # emotion/style tags accepted at synthesize
    style_presets: list[str] = []    # ["calm", "news", "narration", …] if emotion_control
    deployment: Literal["cloud", "local", "edge"] = "cloud"
    offline: bool = False            # works with no network
    requires_key: bool = False       # needs an API key / local model license
    max_input_chars: int | None = None   # None = no hard limit (splitting may apply)
    output_suffix: str = "mp3"       # what it writes (replaces name == "edge" checks)
    cost_tier: int = 0               # router tie-break when several providers qualify

class TTSProvider(Provider):
    name: str
    capabilities: TTSCapabilities    # class-level, advertised at registration

    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,           # voice id from capabilities.voices
        options: TTSSynthesizeOptions | None = None,   # rate / emotion / style
        out_path: Path,
    ) -> Path:
        ...
```

`TTSSynthesizeOptions` carries per-call modulation (rate multiplier, emotion
preset, style tag) that providers supporting it consume; others ignore it
harmlessly. **Adding a capability is a data change to the descriptor, not a
contract change** — the router and the pipeline never special-case a provider.

Error taxonomy for the router's fallback logic (§7). Extend the existing
`ProviderError` family so the router can distinguish *recoverable* failures
from real bugs:

```python
class ProviderError(RuntimeError): ...            # existing
class ProviderUnavailableError(ProviderError): ...  # network / 5xx / local model missing
class UnauthenticatedError(ProviderError): ...       # bad or missing key
class QuotaExceededError(ProviderError): ...         # 429 / daily limit
```

These are the **only** codes the router catches for fallback. Any other
`ProviderError` propagates to the pipeline's normal retry path unchanged.

---

## 6. Narrator: voice identity, separate from Locale

Locale answers *what language*. **Narrator** answers *who speaks* — and it is a
**different object** so that voice features are additive, never a Locale change:

```python
class Narrator(BaseModel):
    """Who speaks the narration. Language is NOT here — that's Locale."""
    voice_id: str | None = None      # None → the language pack's default_voice
    provider: str | None = None      # None → the router's choice for the language
    emotion: str | None = None       # style preset, if the provider supports it
    rate: float | None = None        # speaking-rate multiplier
    clone_source: str | None = None  # future voice cloning: reference clip/voice id
```

- **V1:** the factory derives a default `Narrator` from the pack
  (`registry.default_narrator(locale.language)`), so the UX stays "pick a
  language, never a voice." `JobContext` carries `ctx.locale` **and**
  `ctx.narrator`.
- **Future narrator selection:** the UI adds a "Narrator" dropdown populated
  from `router.voices_for(locale.narration_language)` (aggregated provider
  catalogs, §7). Picking one sets `Narrator.voice_id` — **Locale is untouched.**
- **Custom voices / voice cloning:** a custom voice is a `Narrator` whose
  `voice_id` points at a user-supplied voice (cloned via a `clone_source`
  reference). Again — a Narrator field, never a Locale field.

Rule: **Locale is frozen once a job starts; Narrator is what grows.** Every
"who speaks" feature in the future list lands on Narrator.

---

## 7. Provider selection: plugin architecture + routing

### 7.1 Plugins

A TTS provider is a **plugin**:

1. **Implement** `TTSProvider` in a module (`providers/tts/elevenlabs.py`)
   declaring `name`, `capabilities`, and `synthesize`.
2. **Register** it by name in the existing provider registry
   (`get_provider("tts", name)`) — one line.
3. **Install** its dependency: `pip install acce[tts-elevenlabs]` (optional
   extra; a missing extra degrades to stub, exactly like edge-tts today).
4. **Configure** its key or local model path in `.env`:
   `ACCE_TTS__API_KEYS={"elevenlabs":"..."}`. `TTSConfig` gains
   `api_keys: dict[str, str]`.

A provider with `capabilities.offline=True` (local model) needs no key. That is
the whole install story — no module, no router, no pipeline change.

### 7.2 The router

`TTSRouter` is itself a `TTSProvider` — the **`RoutingTTSProvider`** — so the
audio module keeps its single `self.tts.synthesize(...)` call and **never learns
which real provider produced the narration**:

```python
class RoutingTTSProvider(TTSProvider):
    """Pipeline-facing facade. capabilities = union of candidates."""
    name = "router"

    def synthesize(self, text, *, voice=None, options=None, out_path) -> Path:
        for provider in self._candidates:            # priority order (§7.3)
            if not self._usable(provider):           # static pre-check
                continue
            try:
                return provider.synthesize(text, voice=voice,
                                           options=options, out_path=out_path)
            except (ProviderUnavailableError, UnauthenticatedError,
                    QuotaExceededError) as exc:       # recoverable → next candidate
                log.warning("tts fallback: %s (%s)", provider.name, exc)
                out_path.unlink(missing_ok=True)
        return self._stub.synthesize(text, voice=None, out_path=out_path)  # always works
```

### 7.3 Candidate ranking (all data-driven)

```python
def _candidates(locale: Locale, narrator: Narrator) -> list[TTSProvider]:
    profile = registry.profile(locale.narration_language)
    order = []
    for name in profile.tts_preference:              # pack preference, e.g. [edge, stub]
        provider = get_provider("tts", name)          # registry lookup
        if provider is None:
            continue                                  # not installed
        if locale.narration_language not in provider.capabilities.languages:
            continue                                  # capability filter
        order.append(provider)
    # deterministic tie-break: cost_tier, then registration order
    return sorted(order, key=lambda p: (p.capabilities.cost_tier, order.index(p)))
```

Ranking uses only **data**: pack preference order → capability filter →
`cost_tier` tie-break. No `if language == "hi": use edge` anywhere.

### 7.4 Graceful fallback tiers

1. **Not installed** → filtered out at candidate build (no exception at all).
2. **Unauthenticated** (missing key, `requires_key=True` but no key) → skipped
   in `_usable()` static pre-check.
3. **Unavailable / quota-limited at call time** (network drop, 5xx, HTTP 429)
   → caught in `synthesize`, next candidate tried, partial output unlinked.
4. **Nothing works** → stub synthesizes (writes the text), preserving the
   pipeline's existing key-free guarantee. A job never fails because every real
   TTS provider is down.

The `provider` recorded in `AudioTrack` metadata is the one that actually
produced audio — observability, not branching. The audio module's *logic* is
identical for every provider.

---

## 8. Translation seam (documented extension point — NOT V1)

Between **Script Generation** and **Narration** there is a natural boundary:
the scene narration text. In V1 it flows straight from script → scene planner →
TTS untouched. The seam formalizes what happens when `script_language ≠
narration_language` (or ≠ `subtitle_language`): **derived text** instead of
duplicated generation.

```python
class TranslationProvider(Provider):
    name: str
    def translate(self, text: str, *, source: str, target: str) -> str:
        ...
```

**Invocation points** (both are *boundaries*, resolved lazily, identity in V1):

1. **Narration boundary** — the audio stage narrates
   `narration_text(scene, locale)`:
   `script_language == narration_language` → identity (V1, no provider needed);
   otherwise `translator.translate(scene.narration_segment, source=script,
   target=narration)`.
2. **Subtitle boundary** — `build_cues` renders cue text via
   `subtitle_text(cue, locale)`: identity in V1; translation for bilingual
   subtitles later.

**What this seam enables without redesign:**

- **Dubbing** — one script, narration derived in another language (the
  documentary's visuals, timeline, and Director Mode are all untouched).
- **Multilingual exports** — one script → N narration languages, each an
  independent audio pass.
- **Bilingual subtitles** — subtitle language diverges from narration language;
  SRT/ASS already support parallel streams.

**Invariants it preserves (architecture-v2.md):**

- **I7 / I8** — narration owns the global clock. Timing is *measured* from
  actual TTS output, so translated narration feeds the measured clock exactly
  like original narration; nothing estimates.
- **I10** — subtitles and master mix follow the narration that was actually
  spoken; the subtitle boundary derives from the same source text, so they stay
  aligned.
- The seam is **dormant in V1**: `Locale` resolution collapses
  script = narration = subtitle, so no translation provider exists, no text is
  ever rewritten, and no pipeline code branches. Lifting the collapse later is a
  provider addition, not a pipeline change.

---

## 9. Future features (each maps to an existing seam)

| Future feature | Seam that makes it work — no redesign |
|---|---|
| **Bilingual subtitles** | `subtitle_language` → `subtitle_languages: list[str]`. `build_cues` already separates timing from text; SRT/ASS support parallel streams. Uses the §8 subtitle boundary. |
| **EN narration + HI subtitles** | `Locale { script: en, narration: en, subtitles: hi }` + the §8 subtitle boundary. Already expressible — this is *why* the five dimensions exist. |
| **HI narration + EN subtitles** | Same object, dimensions crossed the other way. |
| **Dubbing** | §8 narration boundary: script stays, narration derived per language. |
| **Voice cloning / custom narrator** | `Narrator.clone_source` / `voice_id` (§6); a `voice-clone` provider plugin (§7.1). Locale untouched. |
| **Narrator picker in the UI** | Populated from `router.voices_for(language)` (§7); sets `Narrator.voice_id`. |
| **Multilingual documentaries** | Per-scene language tag on `Scene.narration_segment`; the audio stage iterates providers per segment. Additive — `synthesize` is already a self-contained per-call API, and the router is a plugin. |

---

## 10. UI / UX

- **Generate flow:** a "Language" radio — `English` / `हिन्दी` — populated from
  `registry.languages()` (`native_name`). Sent as `UserInput.language`.
- **No voice/provider controls anywhere (V1).** The router + default Narrator
  are invisible. If a language resolves to the stub (no real TTS installed),
  the panel shows a passive chip *("Narration will use placeholder text —
  install a TTS provider")* — surfaced from the resolved Locale, never by asking
  the user to pick a voice.
- **Future:** a "Narrator" dropdown only appears once more than one voice exists
  for the language (§7 `voices_for`). It edits a `Narrator`, never Locale.
- **Director Mode:** unchanged — it is post-production over a frozen,
  language-baked documentary.
- **Artifacts:** subtitle file, ASS burn-in (correct `burn_font`), title,
  description all render in the job's language with nothing further to
  configure.

---

## 11. Migration path (incremental, behavior-preserving)

**Phase 1 — the seams exist, nothing behaves differently.**
- Add `LanguageProfile` / `LanguageRegistry` / `Locale` / `Narrator` +
  `en.yaml`.
- Add `TTSCapabilities` / `VoiceSpec`; edge and stub **advertise** their
  catalogs; add the `ProviderError` subclasses.
- `UserInput.language = "en"`; factory resolves `Locale` + default `Narrator`
  onto `JobContext`; wrap TTS in the `RoutingTTSProvider` (single-candidate
  router — identical behavior).
- Replace the English-only tokenizer in `metrics.py` with the profile-driven one
  (`en` → identical output). Replace the `name == "edge"` suffix check with
  `output_suffix` (identical behavior). All 233 tests stay green — pure
  refactor.

**Phase 2 — Hindi.**
- Add `hi.yaml` (WPM, danda punctuation, `readability: none`, Edge voice,
  Devanagari font). Script/Shot prompts get the language directive. Quality
  skips readability for `hi`. Studio adds the radio. A Hindi job generates
  end-to-end: Devanagari script, Hindi narration (Edge, resolved by the router),
  Hindi subtitles (UTF-8, correct ASS font), English visual queries,
  English-or-Hindi metadata.

**Phase 3 — more languages.** Drop in `bn.yaml`, `ta.yaml`, `te.yaml`,
`fr.yaml`, `ja.yaml`. No module changes unless a new *script* type appears
(Japanese: no spaces — its tokenizer + WPM land in profile data).

**Phase 4 — translation seam (explicitly after the language foundation).**
When dubbing/bilingual needs appear, add `TranslationProvider` + the §8
boundaries. Nothing in Phases 1–3 anticipates it or conflicts with it.

---

## 12. Recommendation: `Locale`, not a bare `language`

**Recommend a richer object (a resolved `Locale`, backed by per-language
`LanguageProfile` packs) rather than a bare `language: str`.** Three reasons,
grounded in this pipeline:

1. **The product vision is cross-language, not single-language.** "English
   narration + Hindi subtitles" is not expressible with `language: str`. The
   five-dimension `Locale` expresses it as data; V1 just collapses the
   dimensions. The object costs nothing now and buys the entire §9 roadmap.
2. **A language code cannot carry what the pipeline needs.** WPM, tokenizer +
   punctuation, readability strategy, TTS provider preference + default voice,
   burn-in font, retrieval language — all of this is per-language *data* the
   modules already consume (WPM is literally an existing function parameter).
   Without packs, these become scattered `if lang == "hi"` branches across
   script, metrics, audio, and production. With packs, every one is a lookup.
3. **Adding languages stays data-only.** `fr.yaml` is a file; nothing in
   `modules/` knows French exists. That is the constraint "future languages
   without modifying existing modules," made concrete.

**Two boundaries keep the richness from leaking into the user experience:**

- **Locale (language) ≠ Narrator (voice).** Locale is frozen language data;
   Narrator is the growth point for voices, cloning, and custom narrators. They
   travel side by side on `JobContext` but are never the same object.
- **The router is a provider.** The pipeline sees one `TTSProvider`
   ("the narrator") and never learns which engine produced the audio. Provider
   selection, fallback, and plugin installation are all data + one plugin file.

The user-facing surface is exactly one radio button (and, later, an optional
Narrator dropdown). The complexity of language-awareness is felt by module
authors once, in the packs and plugins, and never by the user.

---

## 13. Governance (frozen architecture)

- This architecture is **frozen** as the reference design for multilingual
  support. Implementation follows it.
- **Locale and Narrator are sealed as separate objects.** Any feature that
  would add a voice/narrator field to `Locale`, or a language field to
  `Narrator`, is an architectural change, not an implementation detail.
- **Provider selection is data-driven.** Any `if language == …` / `if provider
  == …` branch in a module is a governance violation — the branch belongs in a
  language pack (§2) or a capability descriptor (§5).
- **The pipeline is provider-blind.** The audio module must never branch on
  which provider produced narration; `AudioTrack.provider` is observability
  only.
- If a future feature requires a change to any of the above, it must be
  **explained and approved before implementation**, per the same process as
  [architecture-v2.md](architecture-v2.md) §12.
