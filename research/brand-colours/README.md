# Brand colour source audit

Checked 2026-09-29. The [searchable dataset](2026-09-29.json) covers all **352 catalogue IDs**, with official numerical colour evidence for **90**. Every ID records attempted searches or source visits. Make also has official named-colour guidance without verified numeric values. The remaining entries are unresolved, blocked, or supported only by historical third-party metadata; they are not presented as official palettes.

| Evidence | Entries | Meaning |
| --- | ---: | --- |
| Official guidelines | 39 | Explicit numerical colours in owner-published guides, press kits or brand instructions. |
| Official artwork | 49 | Exact vector fills and gradient stops, limited to the supplied artwork. |
| Official UI tokens | 2 | Owner-maintained design-system or terminal themes, kept separate from brand identity. |
| Official names only | 1 | Make names colours but the examined guide supplies no verified numeric values. |
| Unresolved or restricted | 261 | See each entry’s status, attempts and notes. |

This research does **not** change the released icon artwork, `primaryColour`, `colourTheme`, package version or live website. The current runtime metadata still comes from its pinned LobeHub snapshot. This file is a source audit for a subsequent reviewed catalogue update, not a new package API.

## Reading the data

- `sources` records owner pages, direct asset or guide URLs, evidence scope, retrieval date and available SHA-256 digests. Downloads on a third-party host are tied to an owner backlink.
- `colourTheme` is present where a flat set is meaningful. `palettes` preserves light/dark, primary/secondary, historical/current and gradient groups; do not flatten unrelated groups into one brand theme.
- `primaryColour` is omitted when the source does not establish one. Being first in an array does not make a colour primary.
- `existingCatalogue` is the unchanged library snapshot for comparison. `candidatePalette`, `candidatePalettes` and discovery leads are explicitly unverified.
- A `not-found` result describes this search, not proof that a guide does not exist. A source being official also does not make its logo colours a complete corporate palette.

## Findings that affect adoption

- [Anthropic’s brand instructions](https://github.com/anthropics/skills/blob/ef740771ac901e03fbca3ce4e1c453a96010f30a/skills/brand-guidelines/SKILL.md) and its [press kit](https://anthropic.com/press-kit) distinguish the company palette from Claude and Claude Code. Corporate Slate is `#141413`; the supplied Claude product wordmark uses `#151514`.
- [LiveKit](https://livekit.com/brand) publishes different light and dark pairs. [Hugging Face](https://huggingface.co/brand) lists three colours without designating a single primary. Those distinctions are retained.
- [GitHub](https://brand.github.com/foundations/color) and [GitHub Copilot](https://brand.github.com/brand-identity/copilot) have different palettes. Microsoft Copilot is researched separately.
- [Google Cloud’s current logo](https://www.gstatic.com/cgc/google-cloud-logo-fullcolor.svg), [Google’s wordmark](https://www.gstatic.com/images/branding/googlelogo/svg/googlelogo_clr_74x24px.svg), gradient G, Gemini spark and legacy product icons are separate treatments. AI Studio’s examined SVG contains embedded raster artwork; its two recorded vector base fills are only partial evidence.
- [Luma’s 2026 guide](https://lumalabs.ai/media-kit), [Figma’s identity kit](https://www.figma.com/using-the-figma-brand/), [W&B](https://wandb.ai/site/brand-identity/), [Together AI](https://www.together.ai/brand), [AssemblyAI](https://www.assemblyai.com/media) and [Anyscale](https://www.anyscale.com/resources/datasheet/brand?source=editors) expose differences from older catalogue colours or artwork. Their current palette should not silently recolour an older logo.
- Some published guides disagree internally: Figma and Manus have inconsistent HEX/RGB labels; Snowflake and Hyperbolic also have flagged numeric discrepancies. The dataset preserves the explicit published hex and records the conflict.
- The current catalogue labels ID `microsoft` as “Azure” although its artwork is the Microsoft four-square symbol. That identity issue is recorded without changing public IDs or runtime behaviour.

## Gaps and review limits

Mistral’s official brand-kit downloads returned HTTP 403. Full Adobe and Google partner guidance requires approved access. Bing’s current guide supplied usage rules without a verified numeric palette. The Perplexity guide on Standards contains useful colours, but its publisher ownership was not independently confirmed by an owner backlink, so its values remain a candidate.

Two delegated research passes covered the catalogue and major platform families. The main pass recorded 321 targeted search queries and 343 homepage attempts, followed by owner-linked resources and press kits. Those visit counts are search coverage, not palette certification. The parent review independently re-fetched delegated sources and static assets, checked recorded hashes, and visually read outlined PDF labels where text extraction failed. No raster colour sampling, arbitrary website-CSS palette inference, parent-to-product inheritance or brand endorsement is claimed.

Keep original source scope, version and usage notes when adopting these values. Update artwork and public colour metadata together where identities have changed; preserve uncertainty for the unresolved entries. Source snapshots can change after this date, and dynamic HTML hashes are observations rather than permanent release checksums.
