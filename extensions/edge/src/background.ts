declare const chrome: any;

const HOST = 'ai.typesafe.jevcache';
let port: any = null;
let session = '';
let seq = 0;
let nav: Record<string, number> = {};
let pendingEvents: any[] = [];
let sending = false;
const completed = new Map<string, any>();
const seenInFlight = new Set<string>();

async function boot() {
  const saved = await chrome.storage.session.get(['session', 'nav', 'seq']);
  session = saved.session || crypto.randomUUID();
  nav = saved.nav || {};
  seq = saved.seq || 0;
  await chrome.storage.session.set({session, nav, seq});
  connect();
}
function connect() {
  if (port) return;
  try {
    const connection = chrome.runtime.connectNative(HOST);
    port = connection;
    connection.onMessage.addListener(async (message: any) => {
      if (port !== connection) return;
      await chrome.storage.local.set({connected: !message.error, lastSeen: Date.now(),
        connectionError: message.error || ''});
      for (const cmd of message.commands || []) await execute(cmd);
    });
    connection.onDisconnect.addListener(() => {
      const error = chrome.runtime.lastError?.message || 'native_host_disconnected';
      if (port !== connection) return;
      port = null;
      chrome.storage.local.set({connected: false, connectionError: error, checkedAt: Date.now()});
      setTimeout(connect, 5000);
    });
    void snapshot();
  } catch (error) {
    port = null;
    chrome.storage.local.set({connected: false, connectionError: (error as Error).message, checkedAt: Date.now()});
  }
}
async function inspected(tab: any) {
  let probe: any = null;
  if (!tab.discarded) {
    try { probe = await chrome.tabs.sendMessage(tab.id, {type: 'probe'}); } catch {}
  }
  const readonly = /^https:\/\/(docs\.python\.org\/3\/|doc\.qt\.io\/qtforpython-6\/)/.test(tab.url || '');
  const verified = readonly && probe?.ready && !probe.dirty && !probe.interactive && !probe.frames && !probe.media;
  let domain = '网页';
  try { domain = new URL(tab.url).hostname; } catch {}
  const normalized = (tab.url || '').split('#')[0];
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(normalized));
  const objectKey = [...new Uint8Array(digest)].map(n => n.toString(16).padStart(2, '0')).join('');
  return {
    object_key: objectKey,
    id: tab.id, window_id: tab.windowId, session, navigation: nav[tab.id] || 0,
    name: domain, title: (tab.title || '').slice(0, 160),
    active: tab.active, pinned: tab.pinned, audible: !!tab.audible, discarded: !!tab.discarded,
    loading: tab.status !== 'complete', last_used: tab.lastAccessed ? tab.lastAccessed / 1000 : null,
    verified: !!verified, dirty: !!probe?.dirty, auto_discardable: tab.autoDiscardable !== false,
  };
}
async function snapshot() {
  if (sending || !port || !session) return;
  sending = true;
  try {
    const all = (await chrome.tabs.query({})).filter((t: any) => !t.incognito);
    const tabs = [];
    // Sequential probes avoid a flood of messages on many open tabs.
    for (const tab of all.slice(0, 160)) tabs.push(await inspected(tab));
    const events = pendingEvents.splice(0, 100);
    port?.postMessage({protocol: 1, kind: 'snapshot', session, seq: ++seq, tabs, events,
                      truncated: all.length > 160});
    await chrome.storage.session.set({seq});
  } catch {} finally { sending = false; }
}
async function execute(cmd: any) {
  if (completed.has(cmd.id)) { pendingEvents.push(completed.get(cmd.id)); return; }
  if (seenInFlight.has(cmd.id)) return;
  seenInFlight.add(cmd.id);
  const receipt: any = {type: 'receipt', action_id: cmd.id, event_id: crypto.randomUUID(),
                        at: Date.now() / 1000, status: 'rejected'};
  try {
    if (cmd.expires_at < Date.now() / 1000 || cmd.session !== session) throw Error('stale');
    if ((nav[cmd.tab_id] || 0) !== cmd.navigation) throw Error('navigated');
    const tab = await chrome.tabs.get(cmd.tab_id);
    if (tab.incognito) throw Error('private');
    if (cmd.action === 'reopen') {
      if (!tab.discarded) throw Error('already_loaded');
      await chrome.tabs.update(tab.id, {active: true});
      await chrome.windows.update(tab.windowId, {focused: true});
      pendingEvents.push({type: 'revisit', tab_id: tab.id, navigation: nav[tab.id] || 0,
                          event_id: crypto.randomUUID(), origin: 'user', at: Date.now() / 1000});
    } else if (cmd.action === 'discard_tab') {
      const current = await inspected(tab);
      if (current.active || current.pinned || current.audible || current.loading || current.discarded
          || current.dirty || !current.auto_discardable || !current.verified) throw Error('protected');
      // Re-read identity immediately before applying a browser action.
      if ((nav[cmd.tab_id] || 0) !== cmd.navigation) throw Error('navigated');
      const refreshed = await chrome.tabs.get(cmd.tab_id);
      if (refreshed.active || refreshed.audible || refreshed.pinned || refreshed.discarded) throw Error('changed');
      const discarded = await chrome.tabs.discard(cmd.tab_id);
      if (!discarded?.discarded) throw Error('not_completed');
    } else throw Error('unsupported');
    receipt.status = 'completed';
  } catch (error) { receipt.reason = (error as Error).message; }
  completed.set(cmd.id, receipt);
  if (completed.size > 128) completed.delete(completed.keys().next().value!);
  seenInFlight.delete(cmd.id);
  pendingEvents.push(receipt);
}
chrome.tabs.onUpdated.addListener((id: number, change: any) => {
  if (change.url) { nav[id] = (nav[id] || 0) + 1; chrome.storage.session.set({nav}); }
  if (change.discarded === false) pendingEvents.push({type: 'revisit', tab_id: id,
    navigation: nav[id] || 0, origin: 'unknown', event_id: crypto.randomUUID(), at: Date.now() / 1000});
});
chrome.tabs.onRemoved.addListener((id: number) => { delete nav[id]; chrome.storage.session.set({nav}); });
chrome.runtime.onMessage.addListener((msg: any, sender: any) => {
  if (msg.type === 'retry_connection' && !sender.tab) {
    const old = port;
    port = null;
    old?.disconnect();
    connect();
    return;
  }
  if (msg.type === 'user_activity' && sender.tab && !sender.tab.incognito) {
    pendingEvents.push({type: 'usage', tab_id: sender.tab.id, navigation: nav[sender.tab.id] || 0,
                        origin: 'user', event_id: crypto.randomUUID(), at: Date.now() / 1000});
  }
});
chrome.alarms.create('bridge', {periodInMinutes: 0.5});
chrome.alarms.onAlarm.addListener(() => { connect(); void snapshot(); });
setInterval(() => { connect(); void snapshot(); }, 2500);
void boot();
export {};
