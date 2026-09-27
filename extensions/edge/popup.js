async function update() {
  const state = await chrome.storage.local.get(['connected', 'lastSeen', 'connectionError']);
  const fresh = state.connected && Date.now() - (state.lastSeen || 0) < 15000;
  const error = state.connectionError || '';
  let text = fresh ? '已连接本机助手，正在同步网页状态。' : '尚未收到本机助手的回应。';
  if (!fresh && /not found|not registered/i.test(error)) {
    text = '找不到本地桥接。请在助手设置中点击“准备 Edge 接入”，然后重试。';
  } else if (!fresh && /forbidden|not allowed|disabled/i.test(error)) {
    text = '浏览器拒绝了本地桥接，请把下方错误文字提供给开发者。';
  } else if (!fresh && error === 'bridge_authentication_failed') {
    text = '桥接与助手的连接配置不一致。请在助手设置中重新“准备 Edge 接入”，然后重试。';
  } else if (!fresh && error === 'assistant_unavailable') {
    text = '扩展已启动桥接，但暂时找不到桌面助手。请先启动 Jev-Cache。';
  } else if (!fresh && /exited|disconnected/i.test(error)) {
    text = '本地桥接已退出，请把下方错误文字提供给开发者。';
  }
  document.querySelector('#status').textContent = text;
  const detail = document.querySelector('#error');
  detail.hidden = fresh || !error;
  detail.textContent = error;
}
document.querySelector('#retry').addEventListener('click', () => {
  document.querySelector('#status').textContent = '正在重新连接…';
  chrome.runtime.sendMessage({type: 'retry_connection'}).catch(() => {});
});
chrome.storage.onChanged.addListener(() => void update());
setInterval(update, 2000);
void update();
