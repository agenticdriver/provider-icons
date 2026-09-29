import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
import * as core from '../../index.js';
import * as svg from '../../svg.js';
import * as dom from '../../dom.js';
import * as react from '../../react.js';

const read = file => readFileSync(new URL(`../../${file}`, import.meta.url), 'utf8');

export function publicContract() {
  const pkg = JSON.parse(read('package.json'));
  const manifest = JSON.parse(read('manifest.json'));
  const modules = {'.': core, './svg': svg, './dom': dom, './react': react};
  const exports = {}, declarations = {};
  for (const [entrypoint, module] of Object.entries(modules)) {
    exports[entrypoint] = Object.fromEntries(Object.entries(module).map(([name, value]) => [name, typeof value]));
    const filename = pkg.exports[entrypoint].types;
    const source = ts.createSourceFile(filename, read(filename), ts.ScriptTarget.Latest, true);
    declarations[entrypoint] = source.statements
      .filter(node => ts.isInterfaceDeclaration(node) || ts.isTypeAliasDeclaration(node))
      .filter(node => node.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword))
      .map(node => node.name.text).sort();
  }
  return {
    entrypoints: pkg.exports,
    exports,
    declarations,
    manifestVersion: manifest.version,
    aliases: manifest.aliases,
    icons: Object.fromEntries(Object.entries(manifest.icons).map(([id, entry]) => {
      const component = core.providerIconComponentNames[id];
      return [id, {
        component,
        members: Object.keys(react[component]).filter(key => /^[A-Z]/.test(key)).sort(),
        alternatives: entry.alternatives,
        files: {icon: {monochrome: entry.monochrome, ...(entry.color && {color: entry.color})}, ...entry.artworks},
      }];
    })),
  };
}

/** Additions are allowed; every previously published key, mapping and member stays. */
export function assertCompatible(baseline, actual, path = 'public API') {
  if (Array.isArray(baseline)) {
    assert.ok(Array.isArray(actual), `${path} must remain an array`);
    for (const item of baseline) assert.ok(actual.includes(item), `${path} removed ${item}`);
  } else if (baseline && typeof baseline === 'object') {
    assert.ok(actual && typeof actual === 'object' && !Array.isArray(actual), `${path} must remain an object`);
    for (const [key, value] of Object.entries(baseline)) {
      assert.ok(Object.hasOwn(actual, key), `${path} removed ${key}`);
      assertCompatible(value, actual[key], `${path}.${key}`);
    }
  } else {
    assert.equal(actual, baseline, `${path} changed`);
  }
}
