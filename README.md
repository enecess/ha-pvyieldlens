# PVYieldLens

Home Assistant 光伏性能监测 App，也可作为独立 Docker 服务运行。通过实际功率、组件温度和组件平面辐照度实体，输出统一时间粒度统计、实时平滑指标和累计预计电量。

## 功能

- 统计粒度 1／5／10 分钟，默认 5 分钟。
- 实时默认最近 60 秒的时间加权平均，每 5 秒更新。
- 预计功率、实际功率、温度修正 PR、可优化功率，以及日／总累计预计电量。
- SQLite 持久化、重启恢复、最多 7 天 HA 历史回填。
- 中文、英语、法语、德语、波兰语、意大利语；Web 跟随浏览器语言，不支持的语言回退英语。
- 直接调用 HA API，无需 MQTT 或额外自定义集成。

## 独立 Docker 安装

```sh
cp .env.example .env
# Edit .env and set your own PVYL_WEB_PASSWORD.
docker compose up -d --build
```

打开 `http://localhost:8099`，用户名 `admin`，密码为 `.env` 中的 `PVYL_WEB_PASSWORD`。默认端口只绑定本机；局域网访问可调整 Compose 绑定地址，或使用 HTTPS 反向代理。

设置页填写 HA 地址（例如 `http://homeassistant.local:8123`，不带 `/api`）和管理员长期访问令牌，点击“连接并加载实体”，选择来源、填写光伏参数并保存。若 HA 也在 Docker 中运行，使用容器之间能互通的地址，不要填写 PVYieldLens 容器自身的 `localhost`。

`PVYL_HA_URL`／`PVYL_HA_TOKEN` 可作为首次启动默认连接；Web 保存后以保存值为准。令牌不回显，留空表示保留已有令牌。

## Home Assistant App 安装

HA OS 本地安装：将整个 `pvyieldlens/` 目录复制到 HA 主机 `/addons/pvyieldlens/`，在 App 商店菜单重新加载本地应用，安装 **PVYieldLens**。Supervisor 使用目录内 Dockerfile 构建。

启动后点击“打开 Web UI”，App 自动通过 Supervisor 连接 HA，无需填写 URL、令牌或 Web 密码。业务配置在 Web 页面完成；Supervisor 配置页只设置日志等级。可启用“显示在侧边栏”。

仓库根 `repository.yaml` 支持 App 仓库分发。文件推送到可访问仓库后才可通过 URL 安装；本地开发不会自动推送或发布镜像。声明支持 amd64 和 aarch64，实际验证平台见交付说明。App 使用 Ingress，不额外暴露宿主机端口。

## 输入和公式

| 配置 | 单位／示例 |
| --- | --- |
| 总额定功率 | W，例如 `5000` |
| 功率温度系数 K | `%/°C`，规格书 `-0.35%/°C` 填写 `-0.35` |
| 实际功率 | W 或 kW |
| 组件温度 | °C、°F 或 K |
| 组件平面辐照度 | W/m² 或 kW/m² |

```text
P_est = P_rated × [1 + K/100 × (T - 25)] × G/1000
PR = P_actual / P_est × 100%
Optimizable power = P_est - P_actual
```

用户无需将 K 转成小数。5000 W、K=-0.35 %/°C、45°C、800 W/m² 得到预计功率 3720 W；实际 3348 W 时 PR=90%，可优化功率 372 W。

按输入变化及有效期限分段，先计算各段预计功率，再按持续时间积分。**不按记录条数平均，不把缺测补零，不把低频数据复制为新测量。** PR 分子分母使用三个来源共同有效的时段；部分窗口显示有效时段均值及覆盖率。累计预计电量也只包含共同有效时段，实际功率缺测期间不会累计预计电量。

默认保持上限：功率 300 秒、辐照 300 秒、温度 900 秒，可在高级设置修改。来源应为瞬时值或持续状态；“过去 N 分钟平均值”需另行适配。HA 报告时间不保证设备物理采样时间，历史缺少重复报告时，恢复覆盖率可能低于实时观测。

预计功率为零时 PR 为 `unavailable`，有效夜间零功率保留为零。PR 可超过 100%，可优化功率可为负。负发电功率、错误单位和非有限数值按缺测处理。

## 输出实体

统一前缀 `sensor.pvyieldlens_`：

| 后缀 | 单位 | 通道 |
| --- | --- | --- |
| `estimated_power` | W | 统计 |
| `actual_power` | W | 统计 |
| `pr` | % | 统计 |
| `daily_estimated_energy` | kWh | 当地日累计 |
| `total_estimated_energy` | kWh | 启用以来累计 |
| `realtime_estimated_power` | W | 实时 |
| `realtime_actual_power` | W | 实时 |
| `realtime_pr` | % | 实时 |
| `realtime_optimizable_power` | W | 实时 |

属性包括窗口边界、覆盖率、质量与结算时刻。日累计按 HA 时区午夜归零，总累计从首次配置启用时刻开始。参数修改不重算既往累计。原始数据保留 7 天、窗口结果 90 天，累计值长期保留。

REST 状态实体可供仪表盘和自动化引用，但没有完整设备／实体注册表管理。HA 重启后服务重发；服务异常终止时 HA 可能保留旧状态，应结合时间属性判断；正常停止会尝试标记不可用。

历史补算修复本服务的曲线和累计值。REST 不能补写过去的 HA Recorder 时间戳，HA 会在重新发布时记录累计跃迁。HA 对 PR 的统计平均不是按电量加权的日 PR。

断线期间修改统计参数会保存新的生效边界，恢复后按各时段对应的参数结算。切换 HA 地址会隔离同名实体的观测；切换前旧 HA 尚未采集到的缺口只保留为缺测，不会用新 HA 的历史代替。

## 数据、备份与升级

`/data` 保存数据库，包含运行配置和 HA 凭据。Compose 使用 `pvyieldlens-data` 数据卷，App 的 `/data` 随 HA App 备份保存。备份时先停止容器，再复制整个数据卷／目录。

升级源码后执行 `docker compose up -d --build`。`docker compose down` 保留数据卷；带 `--volumes` 会删除累计和配置，仅在需要清空时使用。

## 开发验证

Python 3.13+，开发依赖见 `requirements-dev.txt`。前端无需打包或 CDN。按本项目约束先同步到 WSL：

```sh
rsync -a --exclude=.git --exclude=.venv --exclude=node_modules /mnt/d/UserFiles/AgentTasks/ha-pvyieldlens/ /dev-tmp/ha-pvyieldlens/
cd /dev-tmp/ha-pvyieldlens
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
node --test tests/frontend.test.mjs
docker build -t pvyieldlens:local pvyieldlens
```

完整浏览器验证：安装 `requirements-browser.txt`，执行 `.venv/bin/python -m playwright install chromium`，再运行 `PVYL_BROWSER_TESTS=1 .venv/bin/pytest -q`。容器验证：构建 `pvyieldlens:dev` 后执行 `.venv/bin/python tests/container_smoke.py`，测试会创建并清理专用模拟 HA、应用容器、网络和数据卷。

`tests/fake_ha.py` 仅用于本地模拟，不连接真实设备。设计和执行记录保留本地，不提交 `docs/superpowers/` 或 `.superpowers/`。

## English quick start

PVYieldLens reads three existing HA sensors, integrates their common valid time intervals, and publishes nine PV performance sensors. Its dashboard supports Chinese, English, French, German, Polish and Italian, selected from browser preferences with English fallback.

For Docker, copy `.env.example` to `.env`, set `PVYL_WEB_PASSWORD`, then run `docker compose up -d --build`. Open `http://localhost:8099`, sign in as `admin`, configure the HA base URL, administrator long-lived token, source entities and PV parameters. Enter the datasheet coefficient directly: **−0.35 %/°C → −0.35**.

For HA OS, copy `pvyieldlens/` into `/addons/`, refresh the local App store and install PVYieldLens. Open the Ingress UI; Supervisor authentication is automatic.

Statistics use completed 1/5/10-minute windows. Live results use a rolling time-weighted average, default 60 seconds updated every 5 seconds. Missing input is never filled with zero; energy accumulates only while all three sources are valid. REST states have no native entity registry management or backdated Recorder writes. Back up `/data` to retain configuration and energy totals.
