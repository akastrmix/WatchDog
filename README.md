# WatchDog

WatchDog 是一套为 3x-ui / Xray 节点量身设计的轻量化滥用监测内核。目前我们已经提供了**第一阶段的可执行骨架**：只需几条指令即可在 VPS 上完成环境准备，随后能同时对接 3x-ui API、Xray access 日志以及 Xray gRPC Stats API，快速验证节点连通性并生成过去 24 小时的用户/IP 行为快照。

## 系统目标

* **以客户 (client/email) 为核心**：统一聚合每个客户的来源 IP、访问域名分类、带宽/流量等信息，并维持 24 小时滚动时间序列。
* **可配置的封禁模型**：根据连接数、跨 /24 IP、短时间大流量、扫描爆破迹象、高危域名访问等指标动态调整严格程度，区分“告警”和“立即封禁”。
* **轻量部署**：目标运行环境为 1C1G VPS，仅依赖 3x-ui 官方 API 与 Xray 日志，避免重复造轮子。
* **可观测性**：Xray Stats API + access log + 系统级计数器组合，配合本地日志与 Telegram 推送输出详细上下文以便调试与取证。

## 部署架构对比

WatchDog 既可以**每台机器独立运行**，也可以设计为**集中式主控 + 轻量探针**。两种方式的差异如下：

### 1. 单节点独立部署

每台运行 3x-ui/Xray 的服务器都启动一份 WatchDog 服务，直接访问本机的 3x-ui API 与 Xray 日志。

* **优点**
  * 不需要额外的网络拓扑或远程认证机制，部署最简单。
  * 日志与封禁动作都在本地完成，延迟最小。
* **缺点**
  * 多台服务器时无法全局查看告警历史或统一配置。
  * 升级/维护需要逐台执行，规模扩大后管理成本高。

### 2. 集中式主控 + 探针模式

在每台节点上运行一个“探针”进程，仅负责读取本地日志、调用 3x-ui API 并将整理后的指标推送给中心主控服务；主控集中执行规则评估、封禁和告警。

* **优点**
  * 主控集中存储所有客户的历史行为，便于建立统一的封禁策略与面板。
  * 节点端探针逻辑更轻量，只需定时推送指标或被动响应主控请求。
  * 更新策略或内核时只需改动主控端，探针通过版本化配置保持兼容。
* **缺点**
  * 需要在主控与探针之间建立安全通信（可选 HTTPS + Token、WireGuard 等）。
  * 主控出现故障时所有节点的集中封禁能力会受影响，需要冗余设计。

> **小结**：目前我们选择“单节点独立部署”作为第一阶段目标，后续如需扩展再平滑迁移到集中式方案。

## 独立部署内核框架

为落实上述目标，仓库新增了 Python 模块化骨架，涵盖采集、指标、规则、告警与服务编排等功能。后续开发可在此基础上逐步实现具体逻辑。

```
watchdog/
├── __init__.py            # 导出核心子模块，便于统一引用
├── config.py              # 所有配置项的 dataclass 定义
├── collectors/            # 与外部系统交互的采集层
│   ├── __init__.py
│   ├── xui_client.py      # 3x-ui API 客户端接口（含上下文管理器）
│   ├── xray_log_watcher.py# Xray 日志流式读取与解析接口
│   └── xray_stats_client.py# Xray gRPC Stats API 客户端
├── metrics/
│   ├── __init__.py
│   └── aggregator.py      # 用户/IP 10 秒桶聚合器（保留 24 小时）
├── rules/
│   ├── __init__.py
│   ├── engine.py          # 规则引擎骨架，负责选择配置档位并执行策略
│   └── policies.py        # 策略协议与判定结果结构体
├── notifiers/
│   ├── __init__.py
│   └── telegram.py        # Telegram 推送接口与消息结构
└── services/
    ├── __init__.py
    ├── scheduler.py       # 背景调度器接口（后续可挂载 asyncio/APScheduler）
    └── watchdog_service.py# 汇总所有组件的服务编排入口
```

### 关键设计点

* **配置集中管理**：`config.py` 用 dataclass 描述 3x-ui 认证、Xray 日志位置、Xray gRPC API（`xray_api.address/port/use_tls`）、指标窗口/桶大小、规则档位、Telegram 推送和调度参数，确保独立部署时只需一份配置即可运行。
* **解耦采集与处理**：`collectors` 模块只关心与 3x-ui / Xray / 系统计数器的交互，后续可以按需替换实现，比如自定义 gRPC 安全链路或改用 `journalctl` 读取日志。
* **流式指标聚合**：`metrics.MetricsAggregator` 持续维护“用户/源 IP × 10 秒”的滑动窗口，持续 24 小时，既可以接收 Xray Stats API 带来的真实带宽，也能在缺少系统指标时按连接占比估算 IP 带宽。
* **可配置策略引擎**：`rules` 模块定义了规则档位、策略协议与决策结构，支持为不同客户选择不同严格等级，并明确了告警 (`warn`) 与封禁 (`block`) 等动作的语义。
* **告警与执行分离**：`services.watchdog_service` 约束了指标处理、通知推送与封禁执行的顺序，同时预留 `TelegramNotifier` 可选（对无 Telegram 需求的部署可禁用）。
* **调度与生命周期管理**：`Scheduler` 接口让我们可以在后续阶段选择最合适的调度库，同时保持核心逻辑与框架无关。

## 核心模块（讨论版）

1. **数据采集层**：按 3x-ui API 认证方式与频率限制轮询，解析 Xray JSON 日志，按客户聚合原始数据。
2. **指标计算与存储**：围绕客户建立指标 Schema（并发、流量、源 IP、访问分类），支持多时间窗口，使用 SQLite 等嵌入式数据库持久化。
3. **封禁策略引擎**：将规则抽象成可配置阈值/权重，计算风险评分或命中规则后调用 3x-ui 封禁接口，并记录详细操作日志。
4. **告警通道**：Telegram 机器人推送 + 本地详细日志，预留接口扩展邮件/Webhook。
5. **部署与维护**：规划模块化目录结构，提供一键安装/更新脚本与 README、FAQ，确保 1C1G 环境下资源占用可控。

欢迎继续补充需求或对上述方案提出修改建议。

## 快速部署与采集演示

以下步骤假设系统中已经安装了 Python 3.9+ 与 Git：

1. 克隆仓库并进入项目目录：

   ```bash
   git clone https://github.com/your-org/WatchDog.git
   cd WatchDog
   ```

2. 执行安装脚本（会在仓库根目录创建 `.venv` 虚拟环境，并安装 `httpx`、`PyYAML` 等依赖）：

   ```bash
   ./scripts/install.sh
   ```

3. 根据实际环境复制并修改配置文件：

   ```bash
   cp config.example.yaml watchdog.yaml
   # 编辑 watchdog.yaml，填入 3x-ui 面板地址、账号、密码与 Xray 日志路径
   ```

   * `xui.*` 与 [官方 Postman 文档](https://documenter.getpostman.com/view/5146551/2sB3QCTuB6) 完全对齐。
   * `xray.*` 指向本机的 access/error log。如果 access log 是 JSON，请显式将 `is_json` 设为 `true`。
   * `xray_api.*` 用于连接 Xray 的 gRPC API。若你沿用官方推荐，在 Xray 配置里添加 `api` 服务和 `tunnel` 入站（监听 127.0.0.1:62789），这里保持默认即可。
   * `metrics.bucket_interval` 决定 10 秒时间桶，可按需调整；`retention` 决定保留多久的窗口（默认 7 天）。

4. 激活虚拟环境并运行一次性采集命令：

   ```bash
   source .venv/bin/activate
   python -m watchdog collect-once --config watchdog.yaml --xray-limit 20
   ```

   * 若需要同时查询 `clientIps` 接口，可追加 `--include-client-ips` 开关。
   * 输出为 JSON，包含所有客户的基础统计（`/panel/api/inbounds/list` 与 `/panel/api/inbounds/getClientTraffics/{email}`）以及最新的 Xray 日志条目，便于快速检查接口连通性。

5. （可选）运行指标采样命令，生成 24 小时窗口的用户/IP 数据：

   ```bash
   python -m watchdog collect-metrics --config watchdog.yaml --duration 300
   ```

   * 该命令会在 5 分钟内每 10 秒从 Xray Stats API 拉取所有用户的上传/下载流量，同时 tail access log 聚合连接数、来源 IP、目标域名等信息。
   * 结束后会打印一份 JSON，其中包含 `users[]` 和 `ips[]` 列表：每个元素都是一个 10 秒时间桶（UTC 时间），带宽/连接数/unique IP/host 分布等指标均可直接用于可视化或后续规则分析。
   * 如需更长时间的采样，调整 `--duration` 即可（必须 ≥10 秒）。命令会自动滚动保留 24 小时内的数据。

运行成功后即可确认 WatchDog 能够在目标 VPS 上对接 3x-ui、Xray Stats API 与 access log，为下一阶段的指标计算与封禁策略奠定基础。

## 已部署环境的升级流程

当仓库发布了新的版本或你通过 Git 拉取了最新代码时，建议按照下列步骤在已经部署的 VPS 上完成平滑更新：

1. **进入项目目录并同步最新代码**：

   ```bash
   cd /path/to/WatchDog
   git pull
   ```

   如需保留本地修改，请先执行 `git status` 确认工作区干净，或自行创建分支处理冲突。

2. **重新安装或升级依赖**：

   安装脚本可以重复执行，它会复用已有的虚拟环境并升级依赖到 `requirements.txt` 中声明的最新版本。

   ```bash
   ./scripts/install.sh
   ```

3. **检查配置是否需要调整**：

   对比仓库中的 `config.example.yaml` 与现有的 `watchdog.yaml`。如果新增了配置项，请参考注释补全字段。

4. **重新激活虚拟环境并验证采集**：

   ```bash
   source .venv/bin/activate
   python -m watchdog collect-once --config watchdog.yaml --xray-limit 20
   ```

   输出中应包含最新的 3x-ui 客户列表与 Xray 日志条目，确认后即可继续运行常驻服务或调度任务。

若你通过 systemd、Supervisor 等方式常驻运行 WatchDog，请在更新完成后重启对应的服务进程，使其加载新的代码版本。
