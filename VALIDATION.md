# Jev-Cache 0.1 · 验证记录

日期：2026-09-27。环境：本机 Windows 11，CPython 3.12.12，PySide6 6.11.2，typesafe-sdk 0.7.2。当前状态为可运行开发预览。

## 本轮结果

| 检查 | 结果 | 能说明什么 |
| --- | --- | --- |
| Python 测试 | 提交前复验 46 项通过 | 策略、使用摘要、状态失效、反馈、测量口径、存储、SDK、安装注册、认证失败恢复、自动触发及 Qt 到 Runtime 的集成；手动点击直接执行且不持久化自动摘要权限 |
| Qt 界面 | 9 项交互检查通过 | 三层窗口、重复点击、忙碌与暂停、设置引导、保留过滤、重开与纠正、清除及 Esc 收起；使用模拟展示数据 |
| Ruff 与语法编译 | 通过 | Python 静态检查、格式及源码可编译 |
| Windows 正常关闭 | 通过 | 自建的无用户数据窗口收到 WM_CLOSE 并确实退出；错误的进程创建时间被拒绝 |
| 打包版启动 | 通过 | 更新后的 JevCache.exe 读取真实内存、枚举应用组、生成三层窗口截图并正常退出；隔离测试目录无后台错误日志 |
| 打包浏览器桥接 | 通过 | 打包 GUI 与打包原生宿主经标准输入输出、认证 Named Pipe 完成空快照通信 |
| Jev SDK | 模拟传输与真实连接通过 | 真实 SDK 请求契约通过；用户配置 Key 后，固定测试文本成功访问 jev-1.13.0，单次约 1.70 秒，未发送电脑状态 |
| Jev 合成候选 | 真实请求与解析通过，未执行动作 | 两个合成文档候选，单次约 1.25 秒；已完成候选建议释放但置信度 0.41，未知候选保留；按现有 0.85 阈值均不执行，不构成判断质量验收 |
| Edge 扩展 | 构建通过，11 项模拟检查通过 | 释放、幂等、活动／导航／过期／隐私／探针保护、连接错误恢复，以及已知文档导航与搜索控件的识别 |
| 真实 Edge 接入 | 通过状态同步 | Edge 启动的宿主与助手完成认证；真实捕获为已连接、2 个网页对象、无桥接错误。尚未执行真实网页释放／重载验收 |

执行正常关闭检查时只操作本轮创建的临时测试窗口。连接排查期间已为当前用户安装和注册 Jev-Cache 原生桥接，并重启助手自身；没有关闭其他已有用户应用，也没有执行真实网页清理。既有真实 Jev 测试只发送固定文本和合成候选，本轮未新增云端请求。

## 证据

以下文件由本机检查生成，可能包含设备状态或本地路径，不纳入 Git。公开仓库提供检查脚本及本次结果摘要；他人在自己电脑上运行后可取得自己的证据，数值不保证相同。

- `artifacts/packaged-main.png` 与 `artifacts/smoke-state.json`：本轮为真实状态，provider_configured=false。
- `artifacts/controlled-close.json`：third_party_compatibility_claim=false。
- `artifacts/native-host-check.json`：actual_edge_browser_tested=false，cleanup_executed=false。
- `artifacts/functional-final-live/smoke-state.json`：最终构建的真实 Edge 状态同步，browser_connected=true、browser_tab_count=2；与上述隔离协议测试分开记录。
- `artifacts/ui-functional-final/verification.json`：9 项 Qt 界面交互检查；fixture_data=true、real_cleanup_executed=false。
- `artifacts/real-jev-connection.json`：真实固定文本连接通过，不代表实际清理判断有效，也不是延迟分布测试。
- `artifacts/real-jev-shadow.json`：合成候选的真实 Jev 影子判断；`would_select` 为空，不产生清理回执。
- `artifacts/profile-source.json`：详情收起、悬浮窗显示、40 秒、未接入 Edge／Jev，私有驻留内存 P95 约 52.4 MiB，平均 CPU 约一个逻辑核心的 0.27%。这不是打包版全负载或长期结论，也不作为 MVP 硬性门槛。

## 尚未验证

Jev 对实际候选的判断质量与请求延迟分布；真实 Edge 网页释放／重新加载及长期连接；真实第三方应用自动退出及残留清理；5 分钟／长期净内存收益、规则对照和记忆增量；24 小时稳定性和普通用户安装体验。连接排查已从宿主未注册推进到认证失败，并通过明确凭据路径与认证失败恢复接通真实 Edge。完整范围和剩余浏览器验收步骤见 [功能验收](docs/FUNCTIONAL-ACCEPTANCE.md)。

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
npm test
```

打包检查会创建隔离数据目录并启动自己的临时实例，随后自动退出，不执行真实应用清理或 Jev 请求。默认 pytest 临时目录在本机存在权限问题，重跑时使用新的项目内 basetemp。
