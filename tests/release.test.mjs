import test from 'node:test';
import assert from 'node:assert/strict';
import {releaseIdentity, registryMetadata, verifyMetadata, waitForRegistryMetadata} from '../scripts/release.mjs';

const pkg = {name: '@agenticdriver/provider-icons', version: '0.1.0-alpha.7'};
const commit = 'a'.repeat(40);

test('release identity keeps alpha separate from stable and rejects invalid packages', () => {
  assert.equal(releaseIdentity(pkg, commit).distTag, 'alpha');
  assert.equal(releaseIdentity({...pkg, version: '0.1.0'}, commit).distTag, 'latest');
  for (const version of ['../bad', '0.1.0-beta.1', '01.0.0', '0.1.0-alpha.01']) {
    assert.throws(() => releaseIdentity({...pkg, version}, commit));
  }
  assert.throws(() => releaseIdentity({...pkg, name: 'another-package'}, commit));
  assert.throws(() => releaseIdentity({...pkg, private: true}, commit));
  assert.throws(() => releaseIdentity(pkg, 'main'));
});

test('registry errors never become permission to publish and existing bytes must match', async () => {
  const value = {...releaseIdentity(pkg, commit), integrity: 'sha512-test'};
  assert.equal(await registryMetadata(value, async () => ({status: 404})), null);
  for (const status of [401, 403, 429, 500]) {
    await assert.rejects(registryMetadata(value, async () => ({status, ok: false})), /Registry lookup failed/);
  }
  const metadata = {...pkg, dist: {integrity: value.integrity, tarball: 'https://registry.npmjs.org/example.tgz'}};
  verifyMetadata(metadata, value);
  assert.throws(() => verifyMetadata({...metadata, version: '0.0.1'}, value));
  assert.throws(() => verifyMetadata({...metadata, dist: {...metadata.dist, integrity: 'sha512-changed'}}, value));
  assert.throws(() => verifyMetadata({...metadata, dist: {...metadata.dist, tarball: 'https://example.com/archive.tgz'}}, value));
});

test('accepted uploads wait for registry processing without retrying authentication errors', async () => {
  let requests = 0;
  const delays = [];
  const options = {
    attempts: 3, interval: 10,
    delay: async milliseconds => delays.push(milliseconds),
    request: async () => ++requests < 3 ? {status: 404} : {ok: true, json: async () => pkg},
  };
  assert.deepEqual(await waitForRegistryMetadata(pkg, options), pkg);
  assert.equal(requests, 3);
  assert.deepEqual(delays, [10, 10]);
  await assert.rejects(waitForRegistryMetadata(pkg, {...options, request: async () => ({status: 404})}), /still processing/);
  for (const status of [401, 403, 429, 500]) {
    let attempts = 0;
    await assert.rejects(waitForRegistryMetadata(pkg, {...options, request: async () => {
      attempts++;
      return {status, ok: false};
    }}), /Registry lookup failed/);
    assert.equal(attempts, 1);
  }
});
