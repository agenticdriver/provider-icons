import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, existsSync} from 'node:fs';
import {assertCompatible, publicContract} from './helpers/compatibility.mjs';

const baseline = JSON.parse(readFileSync(new URL('./fixtures/public-api-v1.json', import.meta.url)));
const actual = publicContract();

test('1.x preserves public entrypoints, exports, types, aliases, components and asset paths', () => {
  assertCompatible(baseline, actual);
  for (const entry of Object.values(actual.icons)) {
    for (const files of Object.values(entry.files)) {
      for (const file of Object.values(files)) {
        assert.ok(existsSync(new URL(`../assets/${file}`, import.meta.url)), `Missing public asset ${file}`);
      }
    }
  }
});

test('the compatibility guard rejects upstream removals or remapping but permits additions', () => {
  const breaks = [
    value => { delete value.entrypoints['./svg']; },
    value => { delete value.exports['.'].resolveProviderIcon; },
    value => { value.declarations['.'] = value.declarations['.'].filter(name => name !== 'IconStyle'); },
    value => { delete value.icons.openai; },
    value => { value.icons.openai.component = 'RenamedOpenAI'; },
    value => { value.icons.openai.members = []; },
    value => { value.icons.openai.alternatives = []; },
    value => { value.icons.openai.files.icon.monochrome = 'renamed.svg'; },
    value => { value.aliases.chatgpt = 'codex'; },
    value => { value.manifestVersion = 2; },
  ];
  for (const mutate of breaks) {
    const candidate = structuredClone(actual);
    mutate(candidate);
    assert.throws(() => assertCompatible(baseline, candidate));
  }
  const additive = structuredClone(actual);
  additive.icons.newicon = {component: 'NewIcon', members: [], alternatives: ['newicon'], files: {}};
  additive.aliases.newalias = 'openai';
  additive.exports['.'].newHelper = 'function';
  additive.icons.openai.members.push('NewLayout');
  assertCompatible(baseline, additive);
});

test('manifest v1 retains the documented field shapes for native consumers', () => {
  const manifest = JSON.parse(readFileSync(new URL('../manifest.json', import.meta.url)));
  assert.equal(manifest.version, 1);
  assert.equal(manifest.packageVersion, JSON.parse(readFileSync(new URL('../package.json', import.meta.url))).version);
  const strings = (value, name) => {
    assert.ok(Array.isArray(value), name);
    for (const item of value) assert.equal(typeof item, 'string', name);
  };
  const files = value => {
    assert.equal(typeof value.monochrome, 'string');
    if ('color' in value) assert.equal(typeof value.color, 'string');
    for (const filename of Object.values(value)) assert.match(filename, /^[a-z0-9-]+\.svg$/);
  };
  for (const entry of Object.values(manifest.icons)) {
    assert.equal(typeof entry.name, 'string');
    strings(entry.alternatives, 'alternatives');
    strings(entry.searchTerms, 'searchTerms');
    strings(entry.colourTheme, 'colourTheme');
    for (const field of ['fullName', 'primaryColour', 'upstreamUrl']) {
      if (field in entry) assert.equal(typeof entry[field], 'string', field);
    }
    if ('category' in entry) assert.ok(['model', 'provider', 'application'].includes(entry.category));
    files({monochrome: entry.monochrome, ...('color' in entry && {color: entry.color})});
    for (const [artwork, variants] of Object.entries(entry.artworks ?? {})) {
      assert.ok(['brand', 'text', 'text-cn'].includes(artwork));
      files(variants);
    }
  }
  for (const target of Object.values(manifest.aliases)) assert.ok(Object.hasOwn(manifest.icons, target));
});
