import test from 'node:test';
import assert from 'node:assert/strict';
import {providerIcons, providerAliases, providerIconCategories, searchProviderIcons} from '../index.js';

test('discovery finds localized names, source keywords, punctuation and aliases', () => {
  for (const [query, id] of [['千问','qwen'], ['Nemotron','nvidia'], ['StableDiffusion','stability'],
    ['  CLAUDE CODE  ','claudecode'], ['claude-code','claudecode'], ['Google AI Studio','aistudio'], ['5dive','fivedive']]) {
    assert.ok(searchProviderIcons(query).some(icon => icon.id === id), `${query} finds ${id}`);
  }
  for (const id of Object.keys(providerIcons)) assert.ok(searchProviderIcons(id).some(icon => icon.id === id), id);
  for (const [alias,id] of Object.entries(providerAliases)) assert.ok(searchProviderIcons(alias).some(icon => icon.id === id), alias);
  assert.equal(searchProviderIcons('openai')[0].id, 'openai');
  assert.deepEqual(searchProviderIcons('nonexistent-brand-xyz'), []);
  assert.deepEqual(searchProviderIcons(null), []);
  assert.deepEqual(searchProviderIcons('', {category: '__proto__'}), []);
});

test('category filtering partitions the catalogue without inventing metadata', () => {
  const found = [];
  for (const category of [...providerIconCategories, 'other']) {
    const matches = searchProviderIcons('', {category});
    assert.ok(matches.length);
    matches.forEach(icon => {
      assert.equal(icon.category ?? 'other', category);
      found.push(icon.id);
    });
  }
  assert.deepEqual(found.sort(), Object.keys(providerIcons).sort());
  assert.equal(searchProviderIcons('claude code', {category: 'model'}).length, 0);
  assert.equal(searchProviderIcons('claude code', {category: 'application'})[0].id, 'claudecode');
  assert.equal(providerIcons.happyhorse.fullName, 'HappyHorse');
  assert.ok(!searchProviderIcons('Hedra').some(icon => icon.id === 'happyhorse'));
  assert.ok(Object.isFrozen(providerIcons.qwen.searchTerms));
  assert.throws(() => providerIcons.qwen.searchTerms.push('invented'));
  assert.match(providerIcons.appwrite.upstreamUrl, /\/pull\/382$/);
  assert.equal(providerIcons.warp.category, undefined);
});
