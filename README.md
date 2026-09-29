# AgenticDriver provider icons

One maintained catalogue for AgenticDriver and UsageStat-Bar: 352 provider and
product marks, 965 SVG files, monochrome and original colour, with explicit
product alternatives, brand marks and wordmarks. Includes all 340 icons and 950
static SVGs from [LobeHub](https://lobehub.com/icons) at the revision recorded in
`sources/lobehub.json`. No remote requests. Core and DOM helpers have no runtime
dependencies; the optional React entrypoint uses the application's React.

Install the standalone alpha from its immutable GitHub release archive:

```sh
npm install --save-exact https://github.com/agenticdriver/provider-icons/releases/download/v0.1.0-alpha.3/agenticdriver-provider-icons-0.1.0-alpha.3.tgz
```

This installs only `@agenticdriver/provider-icons`, not AgenticDriver. The package
is currently distributed through GitHub Releases; it is not yet on npm.

## React

```tsx
'use client';

import { Claude } from '@agenticdriver/provider-icons/react';

export default () => <Claude.Combine size={32} mode="color" />;
```

Use `<Claude />`, `<Claude.Color />`, `<Claude.Text />`, `<Claude.Combine />`
or `<Claude.Avatar />`. Components handle sizing, layout, colour fallback and
hydration-safe SVG IDs. No wrapper, stylesheet or `dangerouslySetInnerHTML` is
needed in your app. `size` is the height in pixels (default 24); width follows the
artwork. `mode="color"` selects colour for Combine/Avatar; `style` remains a normal
React CSS object. React 18 and 19 are supported. The client directive makes
these examples usable in a Next.js App Router component as well.

Text, Combine, Brand/BrandColor and TextCn/TextCnColor are exported only where the
catalogue contains that artwork. Named imports are tree-shakable: importing one
provider does not include all the other providers' SVGs. For dynamic selection:

```tsx
'use client';

import { ProviderIcon } from '@agenticdriver/provider-icons/react';

export default () => <ProviderIcon provider="ppio" artwork="combine" size={32} mode="color" />;
```

Icons are decorative by default. Add `aria-label` for a standalone accessible
image, or label the surrounding button. Standard SVG props and refs are supported.

## JavaScript

```js
import { mountProviderIcon } from '@agenticdriver/provider-icons/dom';

mountProviderIcon('#provider-icon', 'ppio', { artwork: 'combine', style: 'color', size: 32 });
```

Pass a container selector or element. The helper inserts a complete sized SVG and
handles unique IDs; missing icons leave the container unchanged. Use
`createProviderIcon(provider, options)` when you want the SVG element without
mounting it. Add `label` for an accessible image, or `className` to customise it.

## SVG and native applications

```js
import { providerIconSvg } from '@agenticdriver/provider-icons/svg';

const svg = providerIconSvg('ppio', { artwork: 'combine', style: 'color', size: 32 });
```

The SVG helper also supports `combine` (logo plus actual vector wordmark) and
`avatar` (padded logo in a circle). `size` is optional for this lower-level helper.
IDs are generated automatically; a stable explicit `prefix` is available for
manual hydration or deterministic exports. React components manage this for you.

## Catalogue lookup

```js
import {resolveProviderIcon} from '@agenticdriver/provider-icons';
resolveProviderIcon('codex', {style: 'color', variant: 'chatgpt'});
// {id: 'openai', file: 'openai.svg', style: 'monochrome', ...}
resolveProviderIcon('claude', {style: 'color', variant: 'claude-code'});
```

`style` is `monochrome` or `color`. Marks without a colour variant return the
monochrome artwork and report the actual style. `variant` selects a related
product's mark, never an account, model, provider runtime or billing route.
Unknown providers or unrelated alternatives return `undefined` for an app's
own fallback. ChatGPT/OpenAI and Codex are alternatives; Anthropic, Claude and
Claude Code are alternatives; Copilot and GitHub Copilot are alternatives.
Grok now has its own mark, with xAI as an alternative. OpenCode now has its own
mark, with the existing `opencode-go` mark as an alternative. The original IDs
and artwork remain available.

`artwork` selects `icon` (default), `brand`, `text` or `text-cn` where available:

```js
resolveProviderIcon('ai21', {artwork: 'brand', style: 'color'});
resolveProviderIcon('alibaba', {artwork: 'text-cn'});
```

Unavailable artwork returns `undefined`; colour fallback applies within the
selected artwork. `variant` still selects a related product. Enumerate
`providerIcons` and each entry's optional `artworks` to build galleries without
hardcoded lists. `providerIconVersion` exports the installed package version
for version labels and release links; `manifest.json` has `packageVersion` too.

For inline browser SVG, import `providerIconSvg` from the `/svg` entrypoint.
An optional unique `prefix` makes exports deterministic. This static markup
has no scripts or external references. Only exact allowlisted rendering styles
(masks, blending, grayscale and stroke width) survive. It is decorative; label
the surrounding UI. Monochrome artwork inherits `currentColor` inline; an
external `<img>` cannot inherit text colour. Render or use a mask for that case.

For Python, Go, Rust, GTK or other applications, read `manifest.json` and serve
or bundle `assets/*.svg`. GJS can import `index.js` directly. Non-npm apps can
vendor an immutable npm-format release tarball using `scripts/vendor.py` with
its required SHA-256. The copied catalogue and assets are generated dependency
files: update the version/digest and run the vendor script, never edit copies.

Maintain artwork here, then run `npm run build`, `npm test` and `npm pack`.
Commit source and generated catalogue together. Consumers pin releases; they
never download icons while displaying provider settings. See `NOTICE`,
`licenses/` and `provenance.json` for original sources and trademark attribution.

Refresh the complete LobeHub catalogue with `npm run sync:lobehub -- --latest`,
then build and test. The sync resolves one immutable upstream commit and records
it with SHA-256 provenance. To replay it, omit `--latest`; to select a revision,
use `--ref <full-commit-sha>`. Upstream SVGs are verified against the pinned Git
tree, including fixes newer than the static npm archive. Existing local artwork
is preserved; previously imported files are refreshed only if locally unchanged.
Unrecognized variants or unsupported SVG content stop the import for review.
The source snapshot keeps brand/text variants out of the provider list and
retains artwork retired upstream, so existing consumers keep working.
