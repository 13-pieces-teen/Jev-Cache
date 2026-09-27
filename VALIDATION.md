# Jev-Cache 0.1 · 验证记录

日期：2026-09-27。环境：本机 Windows 11，CPython 3.12.12，PySide6 6.11.2，typesafe-sdk 0.7.2。当前状态为可运行开发预览。

## 本轮结果

| 检查 | 结果 | 能说明什么 |
| --- | --- | --- |
| Python 测试 | 28 项通过 | 候选、保护、使用去重、衰减、状态失效、反馈、测量口径、存储与 SDK 请求契约 |
| Ruff 与语法编译 | 通过 | Python 静态检查、格式及源码可编译 |
| Windows 正常关闭 | 通过 | 自建的无用户数据窗口收到 WM_CLOSE 并确实退出；错误的进程创建时间被拒绝 |
| 打包版启动 | 通过 | JevCache.exe 读取真实内存、枚举 62 个可访问应用组、生成自身窗口截图并正常退出；无后台错误日志 |
| 打包浏览器桥接 | 通过 | 打包 GUI 与打包原生宿主经标准输入输出、认证 Named Pipe 完成空快照通信 |
| Jev SDK | 模拟传输通过 | 使用真实 SDK 进行请求序列化及有限答案解析；没有真实服务调用 |
| Edge 扩展 | 构建通过，4 项模拟检查通过 | 已验证文档的释放、幂等、重新活动保护、导航变化及过期／隐私模式拒绝 |

执行正常关闭检查时只操作本轮创建的临时测试窗口。没有关闭任何已有用户应用，没有注册 Edge 或改变现有浏览器页面。

## 证据

以下文件由本机检查生成，可能包含设备状态或本地路径，不纳入 Git。公开仓库提供检查脚本及本次结果摘要；他人在自己电脑上运行后可取得自己的证据，数值不保证相同。

- `artifacts/packaged-main.png` 与 `artifacts/smoke-state.json`：本轮为真实状态，provider_configured=false。
- `artifacts/controlled-close.json`：third_party_compatibility_claim=false。
- `artifacts/native-host-check.json`：actual_edge_browser_tested=false，cleanup_executed=false。
- `artifacts/profile-source.json`：详情收起、悬浮窗显示、40 秒、未接入 Edge／Jev，私有驻留内存 P95 约 52.4 MiB，平均 CPU 约一个逻辑核心的 0.27%。这不是打包版全负载或长期结论，也不作为 MVP 硬性门槛。

## 尚未验证

Jev 实际判断质量与请求延迟，等待用户配置 Key；真实 Edge 安装和页面释放；真实第三方应用自动退出及残留清理；5 分钟／长期净内存收益、规则对照和记忆增量；24 小时稳定性和普通用户安装体验。

受控窗口退出不能证明第三方应用兼容；空快照通信和浏览器模拟不能代替真实 Edge 验证；工作集显示不能证明可释放量。界面仅显示已观察到的动作和数值。

## 重现

在项目根目录：

```powershell
New-Item -ItemType Directory -Path .local -Force | Out-Null
.venv\Scripts\python.exe -m pytest -q --basetemp=.local/test-tmp-new
.venv\Scripts\ruff.exe check src tests scripts
.venv\Scripts\ruff.exe format --check src tests scripts
.venv\Scripts\python.exe -m compileall -q src scripts
.venv\Scripts\python.exe scripts/check_packaged_app.py
.venv\Scripts\python.exe scripts/check_native_host.py
```

在 `extensions/edge` 目录：

```powershell
npm run build
node --test test-background.cjs
```

打包检查会创建隔离数据目录并启动自己的临时实例，随后自动退出，不执行真实应用清理或 Jev 请求。默认 pytest 临时目录在本机存在权限问题，重跑时使用新的项目内 basetemp。
