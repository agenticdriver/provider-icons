import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {extractArtwork} from '../scripts/extract_lobehub_tsx.mjs';
import {providerIcons, providerIconTheme, providerIconComponentNames, resolveProviderIcon} from '../index.js';
import {providerIconSvg} from '../svg.js';
import * as components from '../react.js';

const entry = 'src/Example/components/Color.tsx';
const fixture = (body, before = '') => ({
  'src/Example/style.ts': "export const TITLE = 'Example'; export const COLOR_PRIMARY = '#123456';",
  [entry]: `import {memo} from 'react'; import {useFillIds} from '@/hooks/useFillId';
import {TITLE, COLOR_PRIMARY} from '../style'; ${before}
const Icon = memo(({size = '1em', style, ...rest}) => { ${body} }); export default Icon;`,
});

test('static JSX extraction preserves geometry, literal arrays and local gradient references', () => {
  const files = fixture(`const [a,b] = useFillIds(TITLE, 2);
return <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" height={size} {...rest}>
<title>{TITLE}</title><defs><linearGradient id={a.id}><stop stopColor={COLOR_PRIMARY}/></linearGradient><linearGradient id={b.id}/></defs>
{PATHS.map((d) => <path key={d.slice(0, 2)} d={d} fill={a.fill}/>)}
<line x1={POINT.x} y1={-2} x2={24} y2={12} stroke={b.fill} strokeOpacity={0.5}/>
<path d={\`M\${POINT.x} 0V\${POINT.y}\`}/></svg>;`,
  "const POINT = {x: 2.5, y: 10}; const PATHS = ['M0 0L1 1','M2 2L3 3'] as const;");
  const result = extractArtwork(files, entry, 'Example');
  assert.match(result.svg, /<path d="M2 2L3 3" fill="url\(#example-0\)"/);
  assert.match(result.svg, /<line x1="2.5" y1="-2" x2="24" y2="12" stroke="url\(#example-1\)" stroke-opacity="0.5"/);
  assert.match(result.svg, /d="M2.5 0V10"/);
  assert.match(result.svg, /stop-color="#123456"/);
  assert.doesNotMatch(result.svg, /\bkey=/);
  assert.deepEqual(result.sources, [entry, 'src/Example/style.ts']);
});

test('unreviewed imports, executable expressions and unknown spreads fail without running them', () => {
  for (const [body, before] of [
    ['return <svg>{process.exit(1)}</svg>;', ''],
    ['return <svg/>;', "globalThis.__prSourceExecuted = true;"],
    ['return <svg/>;', "import fs from 'node:fs';"],
    ['return <svg>{(() => { throw new Error("executed") })()}</svg>;', ''],
    ['return <svg {...external}/>;', ''],
    ['return <svg style={{...external}}/>;', ''],
    ['return <svg>{POINT.constructor}</svg>;', 'const POINT = {x:1};'],
    ['return <svg/>;', "const memo2 = require('react').memo;"],
  ]) {
    assert.throws(() => extractArtwork(fixture(body, before), entry, 'Example'));
    assert.equal(globalThis.__prSourceExecuted, undefined);
  }
});

test('every reviewed PR icon exposes its source name, colour metadata and React artwork', () => {
  const snapshot = JSON.parse(readFileSync(new URL('../sources/lobehub-prs.json', import.meta.url)));
  for (const pr of snapshot.pullRequests) for (const [id, source] of Object.entries(pr.icons)) {
    assert.equal(providerIcons[id].name, source.name);
    assert.equal(providerIconComponentNames[id], source.componentName);
    assert.ok(components[source.componentName]);
    assert.ok(providerIconTheme(id).primaryColour, id);
    for (const [artwork, styles] of Object.entries(source.artworks ?? {})) {
      for (const [style, file] of Object.entries(styles)) assert.equal(resolveProviderIcon(id, {artwork, style}).file, file);
    }
  }
  assert.equal(providerIcons.happyhorse.name, 'HappyHorse');
  assert.equal(resolveProviderIcon('5dive').id, 'fivedive');
  assert.deepEqual(providerIconTheme('hefu').colourTheme, ['#0D9488','#06B6D4']);
  assert.match(providerIconSvg('hubris'), /<line\b/);
  assert.equal(providerIconSvg('personastack', {artwork: 'text'}), undefined, 'Font-dependent wordmark is explicitly omitted');
  assert.ok(providerIconSvg('personastack', {style: 'color'}));
  assert.equal(providerIconSvg('orcarouter', {artwork: 'text'}), undefined, 'Malformed source glyphs are not exposed as a wordmark');
  assert.match(providerIconSvg('deyin', {artwork: 'text'}), /viewBox="18 4.75 11.25 4.5"/);
  assert.match(providerIconSvg('openference', {artwork: 'text'}), /translate\(0 24\) scale\(1 -1\)/);
});
