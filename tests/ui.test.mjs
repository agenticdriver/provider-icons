import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {JSDOM} from 'jsdom';
import * as React from 'react';
import {renderToString, renderToStaticMarkup} from 'react-dom/server';
import {build} from 'esbuild';
import ts from 'typescript';
import {providerIcons, providerIconComponentNames} from '../index.js';
import {providerIconSvg} from '../svg.js';
import {createProviderIcon, mountProviderIcon} from '../dom.js';
import * as components from '../react.js';

const root = fileURLToPath(new URL('../', import.meta.url));
const document = new JSDOM('<div id="icon">Placeholder</div>').window.document;
const parse = svg => new JSDOM(svg, {contentType: 'image/svg+xml'}).window.document;

function assertReferences(markup) {
  const ids = [...markup.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
  assert.equal(ids.length, new Set(ids).size, 'IDs are unique across placements and layout parts');
  for (const [, id] of markup.matchAll(/url\(#([^)]+)\)/g)) assert.ok(ids.includes(id), `Missing ${id}`);
}

test('sized layouts retain real wordmark proportions and reject unavailable/invalid options', () => {
  const svg = parse(providerIconSvg('ppio', {artwork: 'combine', style: 'color', size: 56})).documentElement;
  assert.equal(svg.getAttribute('height'), '56');
  assert.equal(svg.getAttribute('width'), '182');
  assert.equal(svg.querySelectorAll('svg').length, 2);
  assert.equal(svg.querySelectorAll('text').length, 0, 'Vector wordmark, no substitute font');
  const missing = Object.entries(providerIcons).find(([, entry]) => !entry.artworks?.text)[0];
  assert.equal(providerIconSvg(missing, {artwork: 'combine'}), undefined);
  for (const size of [0, -1, NaN, Infinity, '24', '" onload="bad']) {
    assert.equal(providerIconSvg('ppio', {size}), undefined);
  }
  for (const artwork of ['__proto__', 'constructor', 'unknown']) assert.equal(providerIconSvg('ppio', {artwork}), undefined);
  assert.equal(providerIconSvg('ppio', {artwork: 'combine', prefix: '" onload="bad'}), undefined);
  const first = providerIconSvg('gemini', {artwork: 'combine', style: 'color'});
  const second = providerIconSvg('gemini', {artwork: 'avatar', style: 'color'});
  assertReferences(first + second);
});

test('DOM helpers mount complete, accessible SVGs with no user stylesheet or ID management', () => {
  const icon = mountProviderIcon('#icon', 'ppio', {document, artwork: 'combine', style: 'color', size: 56, label: 'PPIO'});
  assert.equal(icon, document.querySelector('#icon > svg'));
  assert.equal(icon.getAttribute('height'), '56');
  assert.equal(icon.getAttribute('width'), '182');
  assert.equal(icon.getAttribute('role'), 'img');
  assert.equal(icon.getAttribute('aria-label'), 'PPIO');
  assert.equal(icon.hasAttribute('aria-hidden'), false);
  assert.equal(mountProviderIcon('#icon', 'unknown', {document}), undefined);
  assert.equal(document.querySelector('#icon > svg'), icon, 'Unavailable icon leaves the placeholder intact');
  assert.equal(mountProviderIcon('#missing', 'ppio', {document}), undefined);
  const target = new JSDOM('<div></div>').window.document.querySelector('div');
  const other = mountProviderIcon(target, 'gemini', {style: 'color', artwork: 'avatar'});
  assert.equal(other.ownerDocument, target.ownerDocument);
  assert.equal(other.getAttribute('height'), '24');
  assert.equal(other.getAttribute('aria-hidden'), 'true');
  const labelled = createProviderIcon('openai', {document, label: '<script>"bad"</script>', className: 'brand'});
  assert.equal(labelled.querySelector('script'), null);
  assert.equal(labelled.getAttribute('class'), 'brand');
  assertReferences(other.outerHTML + createProviderIcon('gemini', {document, style: 'color'}).outerHTML);
});

test('each named React export exposes only the artwork supplied by its catalogue entry', () => {
  for (const [id, entry] of Object.entries(providerIcons)) {
    const Component = components[providerIconComponentNames[id]];
    assert.ok(Component, `Missing ${id} component`);
    const members = {Color: 'icon', Avatar: 'avatar'};
    if (entry.artworks?.text) Object.assign(members, {Text: 'text', TextColor: 'text', Combine: 'combine'});
    if (entry.artworks?.brand) Object.assign(members, {Brand: 'brand', BrandColor: 'brand'});
    if (entry.artworks?.['text-cn']) Object.assign(members, {TextCn: 'text-cn', TextCnColor: 'text-cn'});
    assert.equal(Boolean(Component.Combine), Boolean(entry.artworks?.text));
    for (const name of ['default', ...Object.keys(members)]) {
      const markup = renderToStaticMarkup(React.createElement(name === 'default' ? Component : Component[name], {size: 32}));
      assert.match(markup, /^<svg\b/, `${id}.${name}`);
      assert.match(markup, /height="32"/);
      assert.doesNotMatch(markup, /__AD_ICON__|NaN|<script/);
      assertReferences(markup);
    }
  }
});

test('React components provide sizing, colour, labels and dynamic selection', () => {
  const markup = renderToStaticMarkup(React.createElement(components.PPIO.Combine, {size: 56, mode: 'color', 'aria-label': 'PPIO', className: 'test'}));
  const svg = parse(markup).documentElement;
  assert.equal(svg.getAttribute('width'), '182');
  assert.equal(svg.getAttribute('height'), '56');
  assert.equal(svg.getAttribute('role'), 'img');
  assert.equal(svg.hasAttribute('aria-hidden'), false);
  assert.equal(svg.getAttribute('class'), 'test');
  const pair = renderToStaticMarkup(React.createElement(React.Fragment, null,
    React.createElement(components.Gemini.Combine, {mode: 'color'}),
    React.createElement(components.Gemini.Color)));
  assertReferences(pair);
  assert.match(pair, /url\(#/);
  const dynamic = renderToStaticMarkup(React.createElement(components.ProviderIcon, {provider: 'claude', variant: 'claude-code', mode: 'color', artwork: 'avatar'}));
  assert.match(dynamic, /<circle/);
  assert.equal(renderToStaticMarkup(React.createElement(components.ProviderIcon, {provider: 'unavailable'})), '');
  assert.equal(renderToStaticMarkup(React.createElement(components.Claude, {size: -1})), '');
});

test('named imports bundle only their selected artwork', async () => {
  const result = await build({stdin: {contents: "import {Claude} from './react.js'; export default Claude.Combine;", resolveDir: root}, bundle: true, write: false, format: 'esm', minify: true, metafile: true, external: ['react'], logLevel: 'silent'});
  const inputs = Object.keys(Object.values(result.metafile.outputs)[0].inputs);
  assert.ok(inputs.some(file => file.endsWith('react/claude.js')));
  assert.ok(!inputs.some(file => file.endsWith('react/openai.js')));
  assert.ok(!inputs.some(file => file.endsWith('svg-data.js')));
  assert.ok(result.outputFiles[0].contents.length < 50_000, 'A named icon must not bundle the full catalogue');
});

test('copyable public API examples pass strict TypeScript', () => {
  const filename = path.join(root, 'work/example.tsx');
  const source = `import {PPIO, Claude, OpenAI, ProviderIcon} from '@agenticdriver/provider-icons/react';
import {mountProviderIcon, createProviderIcon} from '@agenticdriver/provider-icons/dom';
import {providerIconSvg} from '@agenticdriver/provider-icons/svg';
export const Example = () => <><PPIO.Combine size={56} mode="color" /><Claude.Color size={24} /><OpenAI.Text /><ProviderIcon provider="ppio" artwork="combine" mode="color" /></>;
mountProviderIcon('#icon', 'ppio', {artwork: 'combine', size: 56});
const svg: SVGSVGElement | undefined = createProviderIcon('claude', {label: 'Claude'});
const text: string | undefined = providerIconSvg('ppio', {artwork: 'combine', size: 56});
// @ts-expect-error unavailable artwork must not be advertised
export const Missing = () => <OpenAI.TextCn />;
// @ts-expect-error React takes CSS style separately from icon mode
export const Invalid = () => <Claude style="color" />;`;
  const options = {strict: true, noEmit: true, skipLibCheck: true, jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, moduleResolution: ts.ModuleResolutionKind.Bundler, target: ts.ScriptTarget.ES2022};
  const host = ts.createCompilerHost(options), original = host.getSourceFile;
  host.getSourceFile = (file, ...args) => file === filename ? ts.createSourceFile(file, source, ts.ScriptTarget.ES2022, true) : original(file, ...args);
  const diagnostics = ts.getPreEmitDiagnostics(ts.createProgram([filename], options, host));
  assert.deepEqual(diagnostics.map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
});

test('React hydration keeps gradient IDs and refs stable', async () => {
  const ref = React.createRef();
  const app = React.createElement(React.Fragment, null,
    React.createElement(components.Gemini.Combine, {mode: 'color', ref}),
    React.createElement(components.Gemini.Color));
  const html = renderToString(app);
  const dom = new JSDOM(`<div id="app">${html}</div>`, {pretendToBeVisual: true});
  const beforeHydration = dom.window.document.querySelector('#app').innerHTML;
  const previous = new Map(['window', 'document', 'IS_REACT_ACT_ENVIRONMENT'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  Object.defineProperties(globalThis, {window: {value: dom.window, configurable: true}, document: {value: dom.window.document, configurable: true}, IS_REACT_ACT_ENVIRONMENT: {value: true, configurable: true}});
  let mounted;
  try {
    const {hydrateRoot} = await import('react-dom/client');
    const errors = [];
    await React.act(async () => { mounted = hydrateRoot(dom.window.document.querySelector('#app'), app, {onRecoverableError: error => errors.push(error.message)}); });
    assert.deepEqual(errors, []);
    assert.equal(dom.window.document.querySelector('#app').innerHTML, beforeHydration);
    assert.equal(ref.current.tagName, 'svg');
    assertReferences(html);
  } finally {
    if (mounted) await React.act(async () => mounted.unmount());
    dom.window.close();
    for (const [key, descriptor] of previous) descriptor ? Object.defineProperty(globalThis, key, descriptor) : delete globalThis[key];
  }
});
