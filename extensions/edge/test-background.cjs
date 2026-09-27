const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');

function listener() { let fn; return {addListener(f){fn=f}, fire(...args){return fn?.(...args)}}; }
async function environment() {
  const tab = {id: 7, windowId: 1, url: 'https://docs.python.org/3/library/json.html',
    title: 'JSON reference', status: 'complete', active: false, pinned: false, audible: false,
    discarded: false, autoDiscardable: true, lastAccessed: Date.now() - 600000};
  const data = {session: 'test-session', nav: {}, seq: 0};
  const posted = [];
  const connectionState = {};
  let discarded = 0;
  let interval;
  const port = {onMessage: listener(), onDisconnect: listener(), postMessage(m){posted.push(m)}};
  const onUpdated = listener();
  const chrome = {
    storage: {session: {async get(){return data}, async set(v){Object.assign(data,v)}}, local: {async set(v){Object.assign(connectionState,v)}}},
    runtime: {connectNative(){return port}, onMessage: listener()},
    tabs: {async query(){return [tab]}, async get(){return {...tab}},
      async sendMessage(){return {ready:true,dirty:false,interactive:false,frames:false,media:false}},
      async discard(){discarded++;tab.discarded=true;return {...tab}}, async update(){},
      onUpdated, onRemoved: listener()},
    windows: {async update(){}}, alarms: {create(){}, onAlarm: listener()},
  };
  vm.runInNewContext(fs.readFileSync('dist/background.js','utf8'), {
    chrome, crypto:webcrypto, TextEncoder, URL, Date, console, setTimeout(){},
    setInterval(fn){interval=fn},
  });
  for(let i=0;i<8;i++) await new Promise(resolve=>setTimeout(resolve,5));
  return {tab, port, posted, onUpdated, chrome, connectionState, get discarded(){return discarded}, interval};
}
function command(overrides={}) {
  return {id:'action-1',action:'discard_tab',tab_id:7,session:'test-session',navigation:0,
    expires_at:Date.now()/1000+5,explicit:false,...overrides};
}
test('verified inactive document is discarded at most once', async()=>{
  const e=await environment();
  assert.equal(e.posted[0].tabs[0].verified,true);
  assert.equal(e.posted[0].tabs[0].object_key.length,64);
  await e.port.onMessage.fire({commands:[command()]});
  await e.port.onMessage.fire({commands:[command()]});
  assert.equal(e.discarded,1);
});
test('reactivated tab is protected at execution time', async()=>{
  const e=await environment();e.tab.active=true;
  await e.port.onMessage.fire({commands:[command()]});
  assert.equal(e.discarded,0);
});

test('manual release is rejected if the page can no longer be verified', async()=>{
  const e=await environment();
  assert.equal(e.posted[0].tabs[0].verified,true);
  e.chrome.tabs.sendMessage=async()=>{throw Error('probe unavailable')};
  await e.port.onMessage.fire({commands:[command({explicit:true})]});
  assert.equal(e.discarded,0);
});
test('navigation invalidates an old plan', async()=>{
  const e=await environment();e.onUpdated.fire(7,{url:'https://docs.python.org/3/new'});
  await e.port.onMessage.fire({commands:[command()]});
  assert.equal(e.discarded,0);
});
test('expired action and private tab never execute', async()=>{
  const e=await environment();
  await e.port.onMessage.fire({commands:[command({expires_at:0})]});
  e.tab.incognito=true;
  await e.port.onMessage.fire({commands:[command({id:'action-2'})]});
  assert.equal(e.discarded,0);
});

test('native launch errors are preserved for diagnosis and cleared by a successful reply', async()=>{
  const e=await environment();
  e.chrome.runtime.lastError={message:'Specified native messaging host not found.'};
  e.port.onDisconnect.fire();
  assert.equal(e.connectionState.connected,false);
  assert.equal(e.connectionState.connectionError,'Specified native messaging host not found.');
  e.chrome.runtime.lastError=undefined;
  await e.interval();
  await e.port.onMessage.fire({protocol:1,commands:[]});
  assert.equal(e.connectionState.connected,true);
  assert.equal(e.connectionState.connectionError,'');
});
