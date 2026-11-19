[English](README.md) | **中文** | [Français](README.fr.md) | [Deutsch](README.de.md) | [Polski](README.pl.md) | [Italiano](README.it.md)

# PVYieldLens

## 概览

PVYieldLens 对比光伏系统的实际发电与当前条件下的预估发电。在 Home Assistant 中跟踪性能比（PR），并查看未来七天的发电预测。

## 安装

### Home Assistant OS

本应用要求 Home Assistant 2025.9.0 或更新版本。

[![添加 PVYieldLens 应用仓库](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens%23dev_v0)

1. 点击上方按钮，在 Home Assistant 中确认**添加**。如需手动添加仓库，打开**设置 > 应用 > 安装应用 > ⋮ > 仓库**，输入 `https://github.com/enecess/ha-pvyieldlens#dev_v0`。
2. 在**应用商店**找到 **PVYieldLens**，点击**安装**。
3. 点击**启动**，然后选择**打开网页界面**。

Home Assistant 2026.2 之前的版本请前往**设置 > 加载项 > 加载项商店**，再从 ⋮ 菜单添加仓库。

### Docker

1. 下载此仓库并进入目录。将 `.env.example` 复制为 `.env`，在 `PVYL_WEB_PASSWORD` 中设置登录密码。
2. 运行 `docker compose up -d --build`。
3. 在 Docker 主机上打开 [localhost:8099](http://localhost:8099)，以 `admin` 为用户名，使用刚设置的密码登录。

如需从其他设备访问，将 `compose.yaml` 中的端口映射从 `127.0.0.1:8099:8099` 改为 `8099:8099`。

## 配置

在 PVYieldLens 中打开**设置**。右上角的**语言**菜单可以切换界面语言。

### 连接 Home Assistant

Home Assistant 应用会自动连接。使用 Docker 时，填写 **Home Assistant 地址**和 Home Assistant 管理员的**长期访问令牌**，然后点击**刷新实体**。发布输出传感器需要管理员权限。

首次设置或修改地址时须填写令牌。地址相同时，将令牌留空即可沿用已保存的令牌。

### 光伏组件

| 设置 | 填写内容 |
| --- | --- |
| **STC 下总最大功率** | 将各组件的额定最大功率相加，单位为 W。例如 10 块 500 W 组件合计 5,000 W。 |
| **Pmax 温度系数** | 填写规格书中的 %/°C 数值，例如 −0.35。 |
| **组件倾角** | 0° 至 90°。 |
| **组件朝向** | 从正北（0°）顺时针计算方位角，小于 360°。可选预设方位或**自定义**。 |
| **标称电池片工作温度（NOCT）** | 填写规格书中的数值，大于 20 °C 且不超过 80 °C。默认为 45 °C。 |

倾角和朝向可分别选择**固定值**或 **HA 实体**。角度实体可使用以度（°）上报的 `sensor.*`、`number.*` 或 `input_number.*`。如果采用跟踪支架，每次刷新都会把当时读取的角度用于整批预测。

*Berlin Demo 的光伏阵列为 5,000 W，倾角 35°，朝向为**南 · 180°**。*

<!-- screenshot: settings-pv-modules.png -->

### 传感器

| 设置 | 传感器及支持的单位 |
| --- | --- |
| **实际功率** | 光伏发电功率，W 或 kW。 |
| **辐照度** | 组件所在平面的辐照度，W/m² 或 kW/m²。 |
| **组件温度（可选）** | 组件温度，°C、°F 或 K。留空时，使用 Open-Meteo 的气温、实测辐照度和 NOCT 估算。 |

*Berlin Demo 使用模拟的功率、辐照度和组件温度传感器。*

<!-- screenshot: settings-sensors.png -->

### 预测

在**设置**的**预测**中检查位置和时区。如需修改，请在 Home Assistant 中设置。可以通过**历史 PR 天数**调整用于修正预测的历史范围，默认为 14 天。

### 监测设置

默认每 5 分钟结算电量和 PR。实时值取最近 60 秒的平均值，每 5 秒刷新。超过传感器的**数据超时**时限后，受影响的时段按缺测处理。

点击**保存配置**。

## 可查看的结果

### 看板

查看当前实际功率、预估功率、**PR** 和**可优化功率**。**实时数据**展示最近 10 分钟的功率。

*Berlin Demo 的实时功率和 PR。*

<!-- screenshot: dashboard.png -->

在**发电数据**中查看今天已结算时段的功率、辐照度和组件温度。

*Berlin Demo 当天已结算的发电数据与传感器读数。*

<!-- screenshot: dashboard-generation.png -->

在**历史发电量**中对比每日实际与预估电量。可以选择 **7 天**、**30 天**或**自定义**（最多 90 个自然日）。如需查看 Berlin Demo 所示的过去七个完整自然日，选择**自定义**，将结束日期设为昨天，开始日期设在结束日期的六天前。点击**应用范围**。

*Berlin Demo 七个完整自然日的发电量。*

<!-- screenshot: dashboard-history.png -->

实时 PR 是实际功率除以预估功率所得的百分比，可以超过 100%。**可优化功率**为预估功率减去实际功率，可以为负。缺测会留下空白，实测为零则显示零。预估功率为零时，PR 显示 **—**。

### 能效

选择**今天**、**24 小时**、**7 天**或 **30 天**。**今天**与昨天截至同一本地时间的结果对比，**7 天**包含今天。

查看区间 PR、较上一时段变化的百分点，以及预估与实际电量之差。用 **PR 趋势**和**发电对比**查看变化。按自然日查看时，可在**每天汇总**和按结算间隔显示之间切换。区间 PR 为同一批有效结算时段的实际电量除以预估电量所得的百分比。

*Berlin Demo 今日能效，与昨天同一时刻的结果对比。*

<!-- screenshot: efficiency.png -->

### 预测

对比今天及接下来六天的**原始预测**和**修正预测**。原始预测使用 Open-Meteo 天气和阵列设置。修正使用近期按电量加权的 PR，需要至少三个符合条件且预估电量大于零的完整自然日。历史不足时，修正值显示 **—**。

顶部卡片展示**今日剩余预测**和**明日预测**。在**每日预测电量**中，**今天**为全天预测，**7 日总量**涵盖全部七天。点击**刷新预测**可请求更新天气数据。

*Berlin Demo 的原始与修正预测电量、日期选择和**导出 CSV** 按钮。*

<!-- screenshot: forecast.png -->

选择日期查看功率曲线，展开**每 15 分钟明细**，查看各时段的功率、电量、辐照度和温度。

*Berlin Demo 所选日期的功率曲线和每 15 分钟明细。*

<!-- screenshot: forecast-details.png -->

对于使用单台光伏逆变器的 EMHASS 配置，点击**导出 CSV**，选择原始或修正后的功率序列。使开始时间、步长和步数与本次优化一致。将 `data_weather_forecast.csv` 保存到 EMHASS 的 `data_path` 中，并设置 `set_use_pv=true` 和 `weather_forecast_method=csv`。[EMHASS 配置说明](pvyieldlens/DOCS.md#export-a-pv-power-forecast-to-emhass)

### Home Assistant 输出传感器

| 指标 | HA 实体名称 | 单位 |
| --- | --- | --- |
| 结算预估功率 | `settled_estimated_power` | W |
| 结算实际功率 | `settled_actual_power` | W |
| 结算 PR | `settled_pr` | % |
| 今日预估电量 | `estimated_energy_today` | kWh |
| 累计预估电量 | `estimated_energy_lifetime` | kWh |
| 实时预估功率 | `live_estimated_power` | W |
| 实时实际功率 | `live_actual_power` | W |
| 实时 PR | `live_pr` | % |
| 实时可优化功率 | `live_optimizable_power` | W |
| 今日预测电量 | `forecast_energy_today` | kWh |
| 今日剩余预测电量 | `forecast_energy_remaining_today` | kWh |
| 明日预测电量 | `forecast_energy_tomorrow` | kWh |
| 七天预测电量 | `forecast_energy_7d` | kWh |

上表列出 Home Assistant 中显示的实体名称。在自动化中使用完整 ID，例如 `sensor.pvyieldlens_settled_estimated_power`。四个预测传感器均提供**原始预测**电量。今日预估电量在家庭时区的午夜归零，累计预估电量从首次配置起计算。
