chrome.storage.local.get(['connected', 'lastSeen']).then(s => {
  document.querySelector('#status').textContent = s.connected && Date.now() - s.lastSeen < 15000
    ? '已连接本机助手。' : '尚未连接。请启动 Jev-Cache，并完成浏览器桥接注册。';
});
