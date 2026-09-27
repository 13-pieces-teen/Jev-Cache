# Jev-Cache · Python + PySide6 MVP

Windows 悬浮窗内存助手。当前为 **0.1 开发预览**，以 PRD v0.6 为依据；实际支持范围以本文和验证记录为准。

[产品 PRD](docs/PRD.md) · [Python 实施方案](docs/MVP-TECH-PLAN.md) · [验证记录](VALIDATION.md)

## 运行

仓库提供源码与构建脚本，不包含虚拟环境、运行记录或二进制产物。自行构建后，双击 `dist/JevCache/JevCache.exe`；打包目录须完整保留，运行时无需另装 Python。关闭面板会收起到悬浮窗／托盘；托盘菜单“退出助手”才会结束程序。

源码版（Windows 11，Python 3.12）：

```powershell
git clone https://github.com/13-pieces-teen/Jev-Cache.git
cd Jev-Cache
uv python install 3.12
uv venv --managed-python --python 3.12 .venv
uv sync --locked
.venv\Scripts\python.exe -m jev_cache
```

建议独立 managed Python；本机 Anaconda Python 曾导致 QtCore DLL 加载失败，独立环境已解决。依赖版本记录在 `uv.lock`。程序只用 Qt Widgets，未引入 QtWebEngine。

## Jev 配置

1. 打开“设置”，填入 TypeSafe API Key。默认模型为 `jev-latest`；开发时方便试用，正式效果验证须固定实际模型版本。
2. “测试连接”仅发送固定测试文本，会产生一次真实 API 调用，不上传电脑状态，也不执行清理。
3. 勾选允许发送本轮最小状态摘要，再保存。API Key 经 Windows DPAPI 当前用户加密保存在本地 SQLite；不会放在源码或日志中。
4. 简短网页标题为单独可选项；默认不上传完整 URL、路径、原始窗口标题、网页正文或命令行。输入“当前在做什么”属于你主动提供的模型上下文。

未配置时明确显示“基础模式”。规则结果不会标为 Jev 判断，自动模式不会执行新的语义清理；仍能观察占用、保留对象和由用户明确选择应用请求正常关闭。本人开发验证支持 API Key，对外发布前仍需完成服务端网关与受限凭据。

## 目前能做什么

- 真实系统可用内存、应用分组与占用列表；原生悬浮窗、托盘、自动／手动入口。
- 显式保留、暂停、可关闭习惯记忆、清除学习与历史记录。
- 独立策略核心：访问去重、近期使用、衰减频率、四路候选、有限模型答案和本地小批次规划。
- Jev 官方 SDK 接入、结构化输出验证、超时保留、连接测试；真实模型效果等待配置后的实测。
- 对有明确单窗口入口、未受保护且不是当前活动的应用，用户可单独请求正常关闭。只发送 `WM_CLOSE`，不确认放弃保存，不升级强杀；是否真正退出会再次检查。
- Edge MV3 扩展及 Native Messaging 桥接源码与构建。网页卸载保留原标签；重新打开会加载。开发适配限定 Python／Qt 只读文档，必须满足页面探针、媒体、输入、活动、导航及保护检查。
- 动作回执、固定窗口的系统内存观测、5 分钟 Ghost 观察、明确纠正和相关反馈检索。

应用列表的工作集之和可能包含共享内存，不代表可释放量。效果数字来自系统可用内存窗口，正负均保留；日常观测不声称全部由助手贡献。

## 尚未完成的发布条件

- 两款真实第三方应用的自动退出适配及真实残留组件验证；当前桌面正常关闭仅由用户单独发起。
- Edge 稳定版真实接入与各类页面反例验收；源码／模拟协议通过不能替代浏览器实测。
- Jev 的真实判断质量、阈值校准及规则／记忆对照。当前阈值是开发参数，不是已校准的安全概率。
- 活动分组习惯、全量用户主动重开归因、跨重启 Ghost 覆盖恢复、严格 token 计量、产品网关和升级分发。
- 24 小时稳定性、总体净收益及完整负载下的资源观察。内存和 CPU 数值不作为 MVP 硬门槛，优先交互流畅和核心闭环；短时记录不等于长期验证。
- DeepSeek 条件复核尚未启用；没有任意进程树清理、内存硬裁剪、驱动或游戏注入。

自动模式仅在已连接 Jev、允许摘要上传、持续内存压力和有合格网页时工作；默认关闭。开发版本中，可先用手动模式校验具体页面再测试自动模式。

## 本地数据

默认 `%LOCALAPPDATA%/JevCache/`：`memory.sqlite3`、加密桥接凭据、滚动诊断日志。`JEVCACHE_DATA_DIR` 可指定独立测试目录。原始内存窗口只在 RAM 保留 10 分钟；日志和摘要定期裁剪。关闭习惯记忆不再读写使用历史，明确保留设置独立存在。

## 工程与验证

本轮 **28 项 Python 检查、4 项扩展模拟检查、打包版启动与原生桥接通信检查通过**；真实 Jev 和真实 Edge 页面操作尚未验证，详见 [验证记录](VALIDATION.md)。

```powershell
New-Item -ItemType Directory -Path .local -Force | Out-Null
.venv\Scripts\python.exe -m pytest -q --basetemp=.local/test-tmp
.venv\Scripts\ruff.exe check src tests scripts
```

首次扩展构建：进入 `extensions/edge`，运行 `npm ci --registry=https://registry.npmjs.org` 与 `npm run build`。

先完成上述扩展构建，再打包：`powershell -ExecutionPolicy Bypass -File scripts/build.ps1`。该参数只影响此构建脚本进程，不修改系统策略。

核心模块：`core.py`（确定性策略）、`runtime.py`（唯一状态维护者）、`windows.py`（采集／正常关闭）、`provider.py`（Jev）、`storage.py`（本地记录）、`bridge.py`／`native_host.py`（浏览器）、`ui.py`（界面）。
