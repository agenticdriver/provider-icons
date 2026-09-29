import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import {setTimeout as pause} from 'node:timers/promises';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const directory = join(root, 'work/release');
const repository = 'agenticdriver/provider-icons';
const registry = 'https://registry.npmjs.org';
const versionPattern = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-alpha\.(0|[1-9]\d*))?$/;
const json = path => JSON.parse(readFileSync(path, 'utf8'));
const hash = (data, algorithm = 'sha256', encoding = 'hex') => createHash(algorithm).update(data).digest(encoding);
const capture = (command, args, cwd = root) => execFileSync(command, args, {cwd, encoding: 'utf8', maxBuffer: 8_000_000});
const run = (command, args) => execFileSync(command, args, {cwd: root, stdio: 'inherit'});

export function releaseIdentity(pkg, commit) {
  assert.equal(pkg.name, '@agenticdriver/provider-icons');
  assert.match(pkg.version, versionPattern, 'Use a stable or alpha.N version');
  assert.match(commit, /^[a-f0-9]{40}$/);
  assert.notEqual(pkg.private, true);
  return {name: pkg.name, version: pkg.version, commit, tag: `v${pkg.version}`,
    distTag: pkg.version.includes('-') ? 'alpha' : 'latest',
    filename: `agenticdriver-provider-icons-${pkg.version}.tgz`};
}

export async function registryMetadata(candidate, request = fetch) {
  const response = await request(`${registry}/${encodeURIComponent(candidate.name)}/${candidate.version}`, {
    redirect: 'error', signal: AbortSignal.timeout(30_000),
  });
  if (response.status === 404) return null;
  assert.ok(response.ok, `Registry lookup failed: HTTP ${response.status}`);
  return response.json();
}

export async function waitForRegistryMetadata(candidate, {
  request = fetch, delay = pause, attempts = 61, interval = 10_000,
} = {}) {
  for (let attempt = 0; attempt < attempts; attempt++) {
    const metadata = await registryMetadata(candidate, request);
    if (metadata) return metadata;
    if (attempt + 1 < attempts) await delay(interval);
  }
  assert.fail('npm accepted the upload but this version is still processing; retry verification later');
}

export function verifyMetadata(metadata, candidate) {
  assert.equal(metadata.name, candidate.name);
  assert.equal(metadata.version, candidate.version);
  assert.equal(metadata.dist?.integrity, candidate.integrity, 'Published archive differs; never overwrite a version');
  assert.equal(new URL(metadata.dist.tarball).origin, registry);
}

function cleanCommit() {
  assert.equal(capture('git', ['status', '--porcelain']).trim(), '', 'Commit source changes before preparing a release');
  return capture('git', ['rev-parse', 'HEAD']).trim();
}

function candidate() {
  const value = json(join(directory, 'candidate.json'));
  const expected = releaseIdentity(json(join(root, 'package.json')), cleanCommit());
  for (const [key, item] of Object.entries(expected)) assert.equal(value[key], item, `Candidate ${key} differs from this checkout`);
  const data = readFileSync(join(directory, value.filename));
  assert.equal(hash(data), value.sha256, 'Candidate SHA-256 differs');
  assert.equal(`sha512-${hash(data, 'sha512', 'base64')}`, value.integrity);
  assert.equal(readFileSync(join(directory, 'SHA256SUMS'), 'utf8'), `${value.sha256}  ${value.filename}\n`);
  return value;
}

function requireMain(value) {
  run('git', ['fetch', 'origin', 'main']);
  run('git', ['merge-base', '--is-ancestor', value.commit, 'origin/main']);
}

async function verifyPublished(value, wait = false) {
  const metadata = await (wait ? waitForRegistryMetadata(value) : registryMetadata(value));
  assert.ok(metadata, 'This version is not published to npm');
  verifyMetadata(metadata, value);
  const response = await fetch(metadata.dist.tarball, {redirect: 'error', signal: AbortSignal.timeout(60_000)});
  assert.ok(response.ok, `Archive download failed: HTTP ${response.status}`);
  assert.equal(hash(Buffer.from(await response.arrayBuffer())), value.sha256, 'Registry download SHA-256 differs');
  console.log(`Verified npm ${value.name}@${value.version}: exact archive bytes match.`);
}

async function prepare() {
  const value = releaseIdentity(json(join(root, 'package.json')), cleanCommit());
  assert.equal(json(join(root, 'manifest.json')).packageVersion, value.version);
  run('npm', ['test']);
  mkdirSync(directory, {recursive: true});
  // Pack tracked, committed inputs with Git's file modes. Shared filesystems may
  // report every working-tree file as executable even when Git records 100644.
  const staging = mkdtempSync(join(tmpdir(), 'provider-icons-pack-'));
  let packed;
  try {
    const source = join(staging, 'source');
    mkdirSync(source);
    run('git', ['archive', '--format=tar', `--output=${join(staging, 'source.tar')}`, value.commit]);
    run('tar', ['--no-same-owner', '--same-permissions', '-xf', join(staging, 'source.tar'), '-C', source]);
    [packed] = JSON.parse(capture('npm', ['pack', '--ignore-scripts', '--json', '--pack-destination', directory], source));
  } finally {
    rmSync(staging, {recursive: true, force: true});
  }
  assert.equal(packed.filename, value.filename);
  assert.ok(packed.files.every(file => file.path.split('/').every(part =>
    !['.npmrc', '.env', '.git', 'node_modules', 'work', 'research'].includes(part) && !part.startsWith('.env.'))),
  'Unexpected private/development package file');
  for (const path of ['README.md', 'LICENSE', 'NOTICE', 'manifest.json', 'index.d.ts', 'react.d.ts', 'docs/api.md']) {
    assert.ok(packed.files.some(file => file.path === path), `Missing ${path}`);
  }
  const archive = join(directory, value.filename);
  run(process.execPath, ['scripts/check-package.mjs', archive]);
  const data = readFileSync(archive);
  assert.ok(data.length <= 4_000_000, 'Archive exceeds the native vendor helper limit');
  assert.equal(cleanCommit(), value.commit);
  const result = {...value, schemaVersion: 1, sha256: hash(data), integrity: packed.integrity, size: data.length};
  writeFileSync(join(directory, 'candidate.json'), `${JSON.stringify(result, null, 2)}\n`);
  writeFileSync(join(directory, 'SHA256SUMS'), `${result.sha256}  ${value.filename}\n`);
  console.log(`Prepared ${value.filename} from ${value.commit}; SHA-256 ${result.sha256}`);
}

async function publishNpm() {
  const value = candidate();
  requireMain(value);
  const existing = await registryMetadata(value);
  if (existing) {
    verifyMetadata(existing, value);
    console.log('This exact version is already published; verifying without changing distribution tags.');
  } else {
    run('npm', ['publish', join(directory, value.filename), '--ignore-scripts', '--access', 'public', '--tag', value.distTag, '--registry', registry]);
    console.log('Upload accepted; waiting up to 10 minutes for npm registry processing.');
  }
  await verifyPublished(value, !existing);
}

function githubRelease(tag) {
  try {
    return JSON.parse(capture('gh', ['api', `repos/${repository}/releases/tags/${tag}`]));
  } catch (error) {
    if (String(error.stderr).includes('HTTP 404')) return null;
    throw error;
  }
}

async function publishGithub() {
  const value = candidate();
  requireMain(value);
  const tagRef = `refs/tags/${value.tag}`;
  if (!capture('git', ['ls-remote', '--tags', 'origin', tagRef]).trim()) {
    capture('gh', ['api', '--method', 'POST', `repos/${repository}/git/refs`, '-f', `ref=${tagRef}`, '-f', `sha=${value.commit}`]);
  }
  run('git', ['fetch', 'origin', 'tag', value.tag]);
  assert.equal(capture('git', ['rev-parse', `${value.tag}^{commit}`]).trim(), value.commit, 'Existing release tag points at another commit');
  let release = githubRelease(value.tag);
  if (!release) {
    const notes = join(directory, 'release-notes.md');
    writeFileSync(notes, `Standalone provider icons ${value.version}.\n\nInstall the attached archive or the matching npm version after registry publication. See the [README](https://github.com/${repository}/tree/${value.tag}) and [installation guide](https://github.com/${repository}/blob/${value.tag}/docs/installation.md).\n\nThe archive passed catalogue/source checks and isolated core, DOM, SVG and React 18/19 installation tests. SHA256SUMS verifies the attached bytes.\n`);
    run('gh', ['release', 'create', value.tag, '--repo', repository, '--target', value.commit, '--title', `Provider icons ${value.version}`, '--notes-file', notes, '--draft', ...(value.distTag === 'alpha' ? ['--prerelease'] : [])]);
    release = githubRelease(value.tag);
  }
  const names = [value.filename, 'SHA256SUMS'];
  const missing = names.filter(name => !release.assets.some(asset => asset.name === name));
  assert.ok(release.draft || !missing.length, 'Published release is incomplete; do not mutate it');
  if (missing.length) run('gh', ['release', 'upload', value.tag, ...missing.map(name => join(directory, name)), '--repo', repository]);
  const downloaded = mkdtempSync(join(tmpdir(), 'provider-icons-release-'));
  try {
    for (const name of names) {
      run('gh', ['release', 'download', value.tag, '--repo', repository, '--pattern', name, '--dir', downloaded]);
      assert.deepEqual(readFileSync(join(downloaded, name)), readFileSync(join(directory, name)), `Existing ${name} differs; never overwrite release assets`);
    }
  } finally {
    rmSync(downloaded, {recursive: true, force: true});
  }
  if (release.draft) run('gh', ['release', 'edit', value.tag, '--repo', repository, '--draft=false']);
  console.log(`Verified GitHub release: https://github.com/${repository}/releases/tag/${value.tag}`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const commands = {prepare, verify: () => verifyPublished(candidate()), publish: publishNpm, github: publishGithub};
  const command = process.argv[2];
  assert.ok(Object.hasOwn(commands, command), 'Use prepare, verify, publish or github');
  await commands[command]();
}
