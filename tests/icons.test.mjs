import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, readdirSync} from 'node:fs';
import {providerIcons, providerAliases, providerIconVersion, PROVIDER_ICON_FILES, resolveProviderIcon} from '../index.js';
import {providerIconSvg} from '../svg.js';
test('every asset and alias resolves, with explicit colour fallback', () => {
  const upstream = JSON.parse(readFileSync(new URL('../sources/lobehub.json', import.meta.url)));
  assert.ok(Object.keys(providerIcons).length >= Object.keys(upstream.icons).length);
  for (const id of Object.keys(upstream.icons)) assert.ok(providerIcons[id], id);
  for (const id of Object.keys(PROVIDER_ICON_FILES)) {
    for (const style of ['color','monochrome']) {
      const icon=resolveProviderIcon(id,{style});
      assert.ok(readFileSync(new URL('../assets/'+icon.file,import.meta.url)).length);
      const svg=providerIconSvg(id,{style,prefix:'fixture'});
      assert.match(svg, /<svg/);assert.doesNotMatch(svg, /<script|<title|__AD_ICON__|(?:href|onload)=/);
    }
  }
  assert.equal(resolveProviderIcon('openai',{style:'color'}).style,'monochrome');
});
test('every SVG is discoverable, including wordmarks, and has isolated local references', () => {
  const files = new Set();
  for (const [id, entry] of Object.entries(providerIcons)) {
    assert.ok(!Object.hasOwn(providerAliases, id), `Alias shadows ${id}`);
    for (const artwork of ['icon', ...Object.keys(entry.artworks ?? {})]) {
      for (const style of ['color', 'monochrome']) {
        const options = {style, artwork, prefix: 'coverage'};
        const resolved = resolveProviderIcon(id, options);
        assert.equal(resolved.id, id);
        assert.equal(resolved.artwork, artwork);
        files.add(resolved.file);
        const svg = providerIconSvg(id, options);
        assert.match(svg, /^<svg\b/);
        assert.doesNotMatch(svg, /<script|<title|__AD_ICON__|(?:href|onload)=/);
        const ids = [...svg.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
        assert.equal(new Set(ids).size, ids.length, resolved.file);
        for (const match of svg.matchAll(/url\(#([^)]+)\)/g)) {
          assert.ok(ids.includes(match[1]), `${resolved.file}: missing ${match[1]}`);
          assert.ok(match[1].startsWith('coverage-'));
        }
        for (const match of svg.matchAll(/\bstyle="([^"]+)"/g)) {
          for (const declaration of match[1].split(';')) {
            assert.match(declaration, /^(?:mask-type:(?:alpha|luminance)|mix-blend-mode:(?:overlay|screen)|filter:grayscale\(100%\)|stroke-width:1)$/);
          }
        }
      }
    }
  }
  assert.deepEqual([...files].sort(), readdirSync(new URL('../assets/', import.meta.url)).filter(f => f.endsWith('.svg')).sort());
  assert.equal(providerIconVersion, JSON.parse(readFileSync(new URL('../package.json', import.meta.url))).version);
});
test('artworks preserve style fallback and product alternatives', () => {
  assert.equal(resolveProviderIcon('ai21', {artwork: 'brand', style: 'color'}).file, 'ai21-brand-color.svg');
  assert.equal(resolveProviderIcon('adobe', {artwork: 'text', style: 'color'}).style, 'monochrome');
  assert.equal(resolveProviderIcon('alibaba', {artwork: 'text-cn'}).file, 'alibaba-text-cn.svg');
  assert.equal(resolveProviderIcon('xai', {variant: 'grok'}).id, 'grok');
  assert.equal(resolveProviderIcon('opencode-go', {variant: 'opencode'}).id, 'opencode');
  for (const artwork of ['__proto__', 'constructor', '../../text', 'missing']) {
    assert.equal(resolveProviderIcon('adobe', {artwork}), undefined);
  }
  assert.equal(resolveProviderIcon('openai', {artwork: 'text-cn'}), undefined);
});
test('product alternatives do not change provider identity', () => {
  assert.equal(resolveProviderIcon('codex',{variant:'chatgpt'}).file,'openai.svg');
  assert.equal(resolveProviderIcon('claude',{variant:'claude-code',style:'color'}).file,'claudecode-color.svg');
  assert.equal(resolveProviderIcon('codex',{variant:'claude'}),undefined);
  for(const id of ['__proto__','constructor','../../codex','unknown']) assert.equal(resolveProviderIcon(id),undefined);
  assert.equal(providerIconSvg('gemini',{prefix:'" onload="bad'}),undefined);
  assert.notEqual(providerIconSvg('gemini',{style:'color',prefix:'one'}),providerIconSvg('gemini',{style:'color',prefix:'two'}));
});
