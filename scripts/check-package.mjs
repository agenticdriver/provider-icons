import assert from 'node:assert/strict';
import {mkdtempSync, writeFileSync, existsSync, rmSync, readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {execFileSync} from 'node:child_process';

const archive = resolve(process.argv[2] ?? '');
const version = JSON.parse(readFileSync(new URL('../package.json', import.meta.url))).version;
assert.ok(archive.endsWith('.tgz') && existsSync(archive), 'Pass the exact packed archive');
const directory = mkdtempSync(join(tmpdir(), 'provider-icons-installed-'));
const run = (program, args) => execFileSync(program, args, {cwd: directory, stdio: 'inherit', timeout: 120_000});
try {
  writeFileSync(join(directory, 'package.json'), JSON.stringify({name: 'independent-icon-consumer', private: true, type: 'module'}));
  run('npm', ['install', '--ignore-scripts', '--no-audit', '--no-fund', archive]);
  assert.ok(!existsSync(join(directory, 'node_modules/react')), 'Core install must not pull React');
  writeFileSync(join(directory, 'core.mjs'), `import assert from 'node:assert/strict';
import {providerIconVersion, resolveProviderIcon, providerIconTheme} from '@agenticdriver/provider-icons';
import {providerIconSvg} from '@agenticdriver/provider-icons/svg';
import {mountProviderIcon} from '@agenticdriver/provider-icons/dom';
assert.equal(providerIconVersion, ${JSON.stringify(version)});
assert.equal(resolveProviderIcon('chatgpt').id, 'openai');
assert.equal(providerIconTheme('claude').primaryColour, '#D97757');
assert.equal(resolveProviderIcon('5dive').id, 'fivedive');
assert.equal(providerIconTheme('greenpt').primaryColour, '#9BE755');
assert.match(providerIconSvg('hubris'), /<line/);
assert.match(providerIconSvg('ppio', {artwork: 'combine', size: 56}), /width="182" height="56"/);
assert.equal(typeof mountProviderIcon, 'function');
console.log('PASS packed core, SVG and DOM exports without React');`);
  run(process.execPath, ['core.mjs']);
  for (const version of ['18.3.1', '19.3.0']) {
    run('npm', ['install', '--ignore-scripts', '--no-audit', '--no-fund', `react@${version}`, `react-dom@${version}`]);
    writeFileSync(join(directory, 'react.mjs'), `import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {PPIO, Claude, Deyin, TypeSafeAI, FiveDive, ProviderIcon} from '@agenticdriver/provider-icons/react';
const html = renderToStaticMarkup(createElement(PPIO.Combine, {size: 56, mode: 'color'}));
assert.match(html, /width="182"/); assert.match(html, /height="56"/);
assert.match(renderToStaticMarkup(createElement(Claude.Color)), /<svg/);
assert.equal(Claude.primaryColour, '#D97757');
assert.deepEqual(Claude.colourTheme, ['#D97757']);
assert.match(renderToStaticMarkup(createElement(Deyin.Color)), /linearGradient/);
assert.match(renderToStaticMarkup(createElement(TypeSafeAI.Combine)), /<svg/);
assert.equal(FiveDive.primaryColour, '#1A1A1F');
assert.match(renderToStaticMarkup(createElement(ProviderIcon, {provider: 'gemini', artwork: 'avatar'})), /<circle/);
console.log('PASS packed React components on React ${version}');`);
    run(process.execPath, ['react.mjs']);
  }
} finally {
  rmSync(directory, {recursive: true, force: true});
}
