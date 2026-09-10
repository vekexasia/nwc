import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';

const directory = mkdtempSync(join(tmpdir(), 'youtube-oauth-'));
const file = join(directory, 'oauth.json');
writeFileSync(file, JSON.stringify({ client_id: 'client', client_secret: 'secret', refresh_token: 'refresh', channel_id: 'channel', stream_id: 'stream' }), { mode: 0o600 });
process.env.YOUTUBE_OAUTH_CONFIG = file;
process.env.YOUTUBE_KEY_FILE = join(directory, 'stream.key');
writeFileSync(process.env.YOUTUBE_KEY_FILE, 'private-key', { mode: 0o600 });
const original = globalThis.fetch;
let broadcast: any;
let tokenCalls = 0; let inserts = 0; let deletes = 0;
let privacy = 'unlisted'; let lifecycle = 'ready'; let failBind = false; let lostInsert = false;
let key = 'private-key'; let unauthorized = false;
try {
  globalThis.fetch = async (input, options) => {
    const url = new URL(String(input));
    assert.equal(options?.redirect, 'error');
    if (url.hostname === 'oauth2.googleapis.com') {
      tokenCalls++;
      const body = options?.body as URLSearchParams;
      assert.equal(body.get('refresh_token'), 'refresh');
      assert.equal(body.get('grant_type'), 'refresh_token');
      return Response.json({ access_token: 'access', expires_in: 3600 });
    }
    assert.equal(url.hostname, 'www.googleapis.com');
    assert.equal((options?.headers as Record<string, string>).Authorization, 'Bearer access');
    if (unauthorized) return new Response(null, { status: 401 });
    const resource = url.pathname.split('/v3/')[1];
    if (resource === 'channels') return Response.json({ items: [{ id: 'channel' }] });
    if (resource === 'liveStreams') return Response.json({ items: [{ snippet: { channelId: 'channel' }, cdn: { ingestionInfo: { streamName: key } } }] });
    if (resource === 'liveBroadcasts/bind') {
      if (failBind) return new Response(null, { status: 500 });
      broadcast.contentDetails.boundStreamId = 'stream'; return Response.json(broadcast);
    }
    if (resource === 'liveBroadcasts/transition') {
      assert.equal(url.searchParams.get('broadcastStatus'), 'complete');
      broadcast.status.lifeCycleStatus = 'complete'; return Response.json(broadcast);
    }
    assert.equal(resource, 'liveBroadcasts');
    if (options?.method === 'POST') {
      inserts++; broadcast = JSON.parse(String(options.body));
      assert.equal(broadcast.status.privacyStatus, 'unlisted');
      assert.equal(broadcast.contentDetails.enableAutoStart, true);
      assert.equal(broadcast.contentDetails.enableAutoStop, true);
      assert.equal(broadcast.contentDetails.monitorStream.enableMonitorStream, false);
      broadcast.id = '12345678901'; broadcast.snippet.channelId = 'channel';
      if (lostInsert) throw Error('Lost insert response');
      return Response.json(broadcast);
    }
    if (options?.method === 'DELETE') { deletes++; return new Response(null, { status: 204 }); }
    broadcast.status.privacyStatus = privacy; broadcast.status.lifeCycleStatus = lifecycle;
    return Response.json({ items: [broadcast] });
  };
  const { youtube } = await import('./youtube.ts');
  const id = randomUUID();
  assert.equal((await youtube('start', id, 'Nome à')).state, 'READY');
  assert.equal((await youtube('start', id, 'Nome à')).url, 'https://www.youtube.com/watch?v=12345678901');
  assert.equal(inserts, 1);
  await assert.rejects(youtube('start', randomUUID(), 'Other'), /cleanup/);
  privacy = 'public'; await assert.rejects(youtube('status', id, 'Nome à'), /verification/);
  privacy = 'unlisted'; lifecycle = 'live';
  assert.equal((await youtube('status', id, 'Nome à')).state, 'LIVE');
  assert.equal((await youtube('stop', id, 'Nome à')).state, 'ENDED');
  assert.equal((await youtube('stop', id, 'Nome à')).state, 'ENDED');
  assert.equal(tokenCalls, 1); assert.equal(deletes, 0);
  await assert.rejects(youtube('start', id, 'Nome à'), /already used/);
  assert.equal(JSON.parse(readFileSync(file + '.sessions.json', 'utf8'))[id].ended, true);
  const mismatch = randomUUID(); key = 'wrong';
  await assert.rejects(youtube('start', mismatch, 'Wrong key'), /mismatch/);
  assert.equal(inserts, 1); key = 'private-key';
  const failed = randomUUID(); failBind = true; lifecycle = 'created';
  await assert.rejects(youtube('start', failed, 'Failed bind'), /500/);
  assert.equal((await youtube('stop', failed, 'Failed bind')).state, 'CANCELLED');
  assert.equal(deletes, 1); failBind = false;
  const lost = randomUUID(); lostInsert = true;
  await assert.rejects(youtube('start', lost, 'Lost response'), /Lost/);
  assert.equal((await youtube('stop', lost, 'Lost response')).state, 'CANCELLED');
  assert.equal(inserts, 3); assert.equal(deletes, 2); lostInsert = false;
  const last = randomUUID(); lifecycle = 'ready';
  await youtube('start', last, 'Token expired');
  unauthorized = true;
  await assert.rejects(youtube('status', last, 'Token expired'), /401/);
  unauthorized = false;
  await youtube('stop', last, 'Token expired'); assert.equal(tokenCalls, 2);
  await assert.rejects(youtube('start', '__proto__', 'Bad ID'), /Invalid/);
  globalThis.fetch = async () => new Response('x'.repeat(1024 * 1024 + 1));
  await assert.rejects(youtube('start', randomUUID(), 'Oversized'), /too large/);
  console.log('PASS: OAuth refresh, unlisted title/binding, key/channel match, idempotence, owned stop, failed bind, lost insert recovery, 401 and bounded response');
} finally {
  globalThis.fetch = original;
  delete process.env.YOUTUBE_OAUTH_CONFIG; delete process.env.YOUTUBE_KEY_FILE;
  rmSync(directory, { recursive: true, force: true });
}
