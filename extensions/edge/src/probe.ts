declare const chrome: any;

let dirty = false;
let lastInput = 0;
function state() {
  return {
    ready: document.readyState === 'complete', dirty,
    interactive: !!document.querySelector('textarea,[contenteditable="true"],input:not([type="search"]):not([type="hidden"])'),
    frames: !!document.querySelector('iframe'),
    media: [...document.querySelectorAll('audio,video')].some((e: any) => !e.paused),
    last_input: lastInput,
  };
}
function changed(event: Event) {
  if (event.isTrusted) dirty = true;
}
document.addEventListener('input', changed, true);
document.addEventListener('change', changed, true);
document.addEventListener('pointerdown', event => {
  if (event.isTrusted && document.hasFocus()) {
    lastInput = Date.now();
    chrome.runtime.sendMessage({type: 'user_activity', at: lastInput}).catch(() => {});
  }
}, {capture: true, passive: true});
chrome.runtime.onMessage.addListener((message: any, _sender: any, reply: any) => {
  if (message.type === 'probe') reply(state());
});
export {};
