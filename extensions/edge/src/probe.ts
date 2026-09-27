declare const chrome: any;

let dirty = false;
let lastInput = 0;
function navigationControl(input: Element) {
  if (input.getAttribute('type') !== 'checkbox') return false;
  if (location.hostname === 'docs.python.org') {
    return input.id === 'menuToggler' && input.classList.contains('toggler__input')
      && input.getAttribute('aria-controls') === 'navigation';
  }
  if (location.hostname === 'doc.qt.io') {
    return (input.classList.contains('sidebar-toggle') && ['__navigation', '__toc'].includes(input.id))
      || (input.classList.contains('toctree-checkbox') && /^toctree-checkbox-\d+$/.test(input.id));
  }
  return false;
}
function documentSearch(input: HTMLInputElement) {
  if (input.name !== 'q' || !['search', 'text'].includes(input.type)) return false;
  const form = input.closest('form');
  if (!form || (form.getAttribute('method') || 'get').toLowerCase() !== 'get') return false;
  const action = new URL(form.getAttribute('action') || '', location.href);
  return action.origin === location.origin && action.pathname.endsWith('/search.html');
}
function meaningfulInput(input: HTMLInputElement) {
  if (navigationControl(input) || ['hidden', 'button', 'submit', 'reset'].includes(input.type)) return false;
  // An empty documentation search is harmless; typed queries are kept.
  if (documentSearch(input)) return !!input.value.trim();
  return true;
}
function state() {
  return {
    ready: document.readyState === 'complete', dirty,
    interactive: !!document.querySelector('textarea,select,[contenteditable]:not([contenteditable="false"])')
      || [...document.querySelectorAll('input')].some(meaningfulInput),
    frames: !!document.querySelector('iframe'),
    media: [...document.querySelectorAll('audio,video')].some((e: any) => !e.paused),
    last_input: lastInput,
  };
}
function changed(event: Event) {
  if (event.isTrusted && !(event.target instanceof Element && navigationControl(event.target))) dirty = true;
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
