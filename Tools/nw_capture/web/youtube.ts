import { existsSync, readFileSync, statSync, writeFileSync, renameSync } from 'node:fs';

const path = process.env.YOUTUBE_OAUTH_CONFIG;
let config: Record<string, string> | undefined;
if (path) {
  if (statSync(path).mode & 0o077 || statSync(path).size > 8192) throw Error('YouTube OAuth config must be private and small');
  const value: unknown = JSON.parse(readFileSync(path, 'utf8'));
  if (!value || typeof value !== 'object') throw Error('Invalid YouTube OAuth config');
  config = {};
  for (const key of ['client_id', 'client_secret', 'refresh_token', 'channel_id', 'stream_id']) {
    if (!(key in value) || typeof value[key as keyof typeof value] !== 'string' || !value[key as keyof typeof value]) throw Error(`Missing YouTube ${key}`);
    config[key] = String(value[key as keyof typeof value]);
  }
}
export const youtubeManaged = Boolean(config);
let accessToken = '';
let expiresAt = 0;
let refreshing: Promise<void> | undefined;
async function jsonResponse(response: Response): Promise<any> {
  if (!response.ok) throw Error(`YouTube HTTP ${response.status}; inspect authorization/quota, not raw responses`);
  const reader = response.body?.getReader();
  if (!reader) throw Error('Missing YouTube response');
  const chunks: Uint8Array[] = []; let bytes = 0;
  try {
    for (;;) {
      const chunk = await reader.read(); if (chunk.done) break;
      bytes += chunk.value.length;
      if (bytes > 1024 * 1024) throw Error('YouTube response too large');
      chunks.push(chunk.value);
    }
  } finally { await reader.cancel(); }
  const result: unknown = JSON.parse(Buffer.concat(chunks).toString());
  if (!result || typeof result !== 'object' || Array.isArray(result)) throw Error('Invalid YouTube response');
  return result;
}
async function token() {
  if (!config) throw Error('YouTube OAuth not configured');
  if (Date.now() < expiresAt) return accessToken;
  if (!refreshing) refreshing = (async () => {
    const result = await jsonResponse(await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(15000),
      body: new URLSearchParams({ client_id: config!.client_id, client_secret: config!.client_secret,
        refresh_token: config!.refresh_token, grant_type: 'refresh_token' }) }));
    if (typeof result.access_token !== 'string' || !result.access_token || typeof result.expires_in !== 'number' || !Number.isFinite(result.expires_in) || result.expires_in < 60) throw Error('Invalid OAuth token response');
    accessToken = result.access_token; expiresAt = Date.now() + (Math.min(result.expires_in, 3600) - 30) * 1000;
  })().finally(() => { refreshing = undefined; });
  await refreshing;
  return accessToken;
}
async function api(method: string, resource: string, parameters: Record<string, string>, body?: object) {
  const response = await fetch(`https://www.googleapis.com/youtube/v3/${resource}?${new URLSearchParams(parameters)}`, {
    method, redirect: 'error', signal: AbortSignal.timeout(20000),
    headers: { Authorization: `Bearer ${await token()}`, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined });
  if (response.status === 401) expiresAt = 0;
  if (method === 'DELETE' && response.status === 204) return {};
  return jsonResponse(response);
}
type Owned = { id: string; name: string; ended: boolean; cancelled?: boolean };
const ownershipPath = path ? path + '.sessions.json' : '';
const owned: Record<string, Owned> = Object.create(null);
if (ownershipPath && existsSync(ownershipPath)) {
  if (statSync(ownershipPath).size > 65536 || statSync(ownershipPath).mode & 0o077) throw Error('Invalid private YouTube ownership file');
  const entries: unknown = JSON.parse(readFileSync(ownershipPath, 'utf8'));
  if (!entries || typeof entries !== 'object' || Array.isArray(entries) || Object.keys(entries).length > 100) throw Error('Invalid YouTube ownership');
  for (const [id, entry] of Object.entries(entries)) {
    if (!/^[a-f0-9-]{36}$/.test(id) || !entry || typeof entry !== 'object' || typeof entry.id !== 'string' || (entry.id && !/^[\w-]{11}$/.test(entry.id)) || typeof entry.name !== 'string' || typeof entry.ended !== 'boolean') throw Error('Invalid owned broadcast');
    owned[id] = entry;
  }
}
function save() {
  writeFileSync(ownershipPath + '.tmp', JSON.stringify(owned), { mode: 0o600 });
  renameSync(ownershipPath + '.tmp', ownershipPath);
}
export async function youtube(action: 'start' | 'status' | 'stop', sessionId: string, name: string) {
  if (!config) throw Error('YouTube OAuth not configured');
  if (!/^[a-f0-9-]{36}$/.test(sessionId) || !name.trim() || name.length > 100 || /[\x00-\x1f\x7f<>]/.test(name)) throw Error('Invalid YouTube session');
  let session = owned[sessionId];
  const marker = `New World capture session ${sessionId}`;
  if (action === 'start' && !session) {
    if (Object.keys(owned).length >= 100 || Object.values(owned).some(value => !value.ended)) throw Error('YouTube ownership cleanup required');
    const channels = await api('GET', 'channels', { part: 'id', mine: 'true' });
    if (!Array.isArray(channels.items) || !channels.items.some((item: any) => item.id === config!.channel_id)) throw Error('OAuth authorized a different channel');
    const streams = await api('GET', 'liveStreams', { part: 'id,snippet,cdn', id: config.stream_id });
    const stream = streams.items?.[0];
    const keyFile = process.env.YOUTUBE_KEY_FILE;
    if (!keyFile || statSync(keyFile).mode & 0o077 || statSync(keyFile).size > 512 || stream?.snippet?.channelId !== config.channel_id || stream?.cdn?.ingestionInfo?.streamName !== readFileSync(keyFile, 'utf8').trim()) throw Error('Configured stream/key/channel mismatch');
    session = owned[sessionId] = { id: '', name, ended: false }; save();
    const result = await api('POST', 'liveBroadcasts', { part: 'id,snippet,status,contentDetails' }, {
      snippet: { title: name, description: marker, scheduledStartTime: new Date(Date.now() + 60000).toISOString() },
      status: { privacyStatus: 'unlisted', selfDeclaredMadeForKids: false },
      contentDetails: { enableAutoStart: true, enableAutoStop: true, recordFromStart: true, monitorStream: { enableMonitorStream: false } } });
    if (typeof result.id !== 'string' || !/^[\w-]{11}$/.test(result.id)) throw Error('YouTube creation unresolved');
    session.id = result.id; save();
    await api('POST', 'liveBroadcasts/bind', { id: session.id, part: 'id,contentDetails', streamId: config.stream_id });
  }
  if (!session) {
    if (action === 'stop') return { url: '', state: 'ENDED' };
    throw Error('Unknown YouTube session');
  }
  if (session.name !== name || (action === 'start' && session.ended)) throw Error('Session already used');
  if (!session.id) {
    // ponytail: recovery scans 150 broadcasts; inspect manually beyond that, never create a duplicate.
    let pageToken = '';
    for (let page = 0; page < 3; page++) {
      const result = await api('GET', 'liveBroadcasts', { part: 'id,snippet', mine: 'true', maxResults: '50', ...(pageToken ? { pageToken } : {}) });
      const match = result.items?.find((item: any) => item.snippet?.description === marker && item.snippet?.channelId === config!.channel_id);
      if (match && typeof match.id === 'string' && /^[\w-]{11}$/.test(match.id)) { session.id = match.id; save(); break; }
      pageToken = typeof result.nextPageToken === 'string' ? result.nextPageToken : '';
      if (!pageToken) break;
    }
    if (!session.id) throw Error('Broadcast creation unresolved; inspect ownership before restarting');
  }
  const url = `https://www.youtube.com/watch?v=${session.id}`;
  if (session.ended) return { url: session.cancelled ? '' : url, state: session.cancelled ? 'CANCELLED' : 'ENDED' };
  const result = await api('GET', 'liveBroadcasts', { part: 'id,snippet,status,contentDetails', id: session.id });
  const broadcast = result.items?.[0];
  if (broadcast?.snippet?.channelId !== config.channel_id || broadcast?.snippet?.title !== name || broadcast?.snippet?.description !== marker || broadcast?.status?.privacyStatus !== 'unlisted') throw Error('Broadcast ownership/title/privacy verification failed');
  const state = broadcast.status.lifeCycleStatus;
  if (action === 'stop') {
    if (state === 'live') {
      const ended = await api('POST', 'liveBroadcasts/transition', { broadcastStatus: 'complete', id: session.id, part: 'status' });
      if (ended.status?.lifeCycleStatus !== 'complete') throw Error('YouTube end not confirmed');
    } else if (state !== 'complete' && state !== 'revoked') {
      if (!['created', 'ready', 'testing'].includes(state)) throw Error('YouTube transition in progress; closure unresolved');
      await api('DELETE', 'liveBroadcasts', { id: session.id }); session.cancelled = true;
    }
    session.ended = true; save(); return { url: session.cancelled ? '' : url, state: session.cancelled ? 'CANCELLED' : 'ENDED' };
  }
  if (broadcast.contentDetails?.boundStreamId !== config.stream_id || !['created', 'ready', 'testing', 'live', 'complete', 'revoked', 'testStarting', 'liveStarting'].includes(state)) throw Error('YouTube binding/state verification failed');
  return { url, state: state.toUpperCase() };
}
