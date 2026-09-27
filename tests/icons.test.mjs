import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {providerIcons, PROVIDER_ICON_FILES, resolveProviderIcon} from '../index.js';
import {providerIconSvg} from '../svg.js';
test('every asset and alias resolves, with explicit colour fallback', () => {
  assert.equal(Object.keys(providerIcons).length, 155);
  for (const id of Object.keys(PROVIDER_ICON_FILES)) {
    for (const style of ['color','monochrome']) {
      const icon=resolveProviderIcon(id,{style});
      assert.ok(readFileSync(new URL('../assets/'+icon.file,import.meta.url)).length);
      const svg=providerIconSvg(id,{style,prefix:'fixture'});
      assert.match(svg, /<svg/);assert.doesNotMatch(svg, /style=|<script|<title|__AD_ICON__|(?:href|onload)=/);
    }
  }
  assert.equal(resolveProviderIcon('openai',{style:'color'}).style,'monochrome');
});
test('product alternatives do not change provider identity', () => {
  assert.equal(resolveProviderIcon('codex',{variant:'chatgpt'}).file,'openai.svg');
  assert.equal(resolveProviderIcon('claude',{variant:'claude-code',style:'color'}).file,'claudecode-color.svg');
  assert.equal(resolveProviderIcon('codex',{variant:'claude'}),undefined);
  for(const id of ['__proto__','constructor','../../codex','unknown']) assert.equal(resolveProviderIcon(id),undefined);
  assert.equal(providerIconSvg('gemini',{prefix:'" onload="bad'}),undefined);
  assert.notEqual(providerIconSvg('gemini',{style:'color',prefix:'one'}),providerIconSvg('gemini',{style:'color',prefix:'two'}));
});
