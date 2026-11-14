[English](README.md) | **中文** | [Français](README.fr.md) | [Deutsch](README.de.md) | [Polski](README.pl.md) | [Italiano](README.it.md)

# PVYieldLens

对比光伏预计功率与实际功率，查看 PR、今日预计电量和累计预计电量。

## 功能

- 查看实时功率、PR 和功率差。
- 按 1、5 或 10 分钟查看功率和 PR 历史。
- 查看今日及启用以来的预计电量。
- 查看最近 24 小时、7 天或 30 天的曲线。
- 支持六种语言，可在页面右上角切换。

## 快速开始

### Home Assistant App

适用于 Home Assistant OS。

[![添加 PVYieldLens 应用仓库](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens%23dev_v0)

1. 点击上方按钮，在 Home Assistant 中确认**添加**。
2. 在应用商店找到 **PVYieldLens**，安装并启动。
3. 打开 Web 页面，在**设置**中选择传感器并填写组件参数。

如果按钮无法打开 Home Assistant，请前往**设置 > 应用 > 安装应用 > 右上角菜单 > 仓库**，添加：

```text
https://github.com/enecess/ha-pvyieldlens#dev_v0
```

Home Assistant 2026.2 之前的版本，请前往**设置 > 加载项 > 加载项商店 > 右上角菜单 > 仓库**。本应用要求 Home Assistant 2025.9.0 或更新版本。

### Docker

下载本仓库并进入目录，创建配置文件：

```sh
cp .env.example .env
```

在 `.env` 中设置登录密码 `PVYL_WEB_PASSWORD`，然后启动：

```sh
docker compose up -d --build
```

打开 [localhost:8099](http://localhost:8099)，用户名为 `admin`，密码为刚设置的密码。首次连接时，在**设置**中填写 Home Assistant 地址，以及属于 Home Assistant **管理员**的长期访问令牌，然后点击**刷新传感器**。已配置地址和令牌时，首次进入**设置**会自动加载传感器。修改连接后、需要更新列表或请求失败后重试时，可点击**刷新传感器**。发布输出实体需要管理员权限。

默认只能在运行 Docker 的电脑上打开页面。如需其他设备访问，将 `compose.yaml` 中的 `127.0.0.1:8099:8099` 改为 `8099:8099`。

## 配置

**实时**显示传感器当前平均值和诊断；**历史**显示已结算时段及所选范围的电量、PR；**预测**显示基于天气的发电估算。历史页的今日及累计电量不随所选范围变化。右上角独立的齿轮和文字入口打开**设置**，三个数据页签始终可用。分类目录在同一张连续表单中滚动定位：连接 Home Assistant、光伏组件、传感器、监测设置和预测。

**保存**后停留在设置页。**取消**会从服务器重新读取已保存配置并替换修改；读取失败时保留草稿，便于重试。带有未保存修改离开时，可选择继续编辑或放弃修改。重新进入设置会再次读取已保存配置。

右上角的**明暗模式**提供自动、浅色和深色。在 Home Assistant 中，自动跟随其主题模式；无法使用 Home Assistant 上下文时跟随系统。选择浅色或深色会保存在本地并覆盖自动模式，重新选择自动即可恢复跟随。切换语言和主题会保留设置草稿。

| 配置项 | 填写内容 |
| --- | --- |
| 总额定功率 | 组件额定功率之和，单位 W，例如 `5000`。 |
| 温度系数 K | 组件规格书中的数值，单位 %/°C，例如 `-0.35`。 |
| 发电功率 | 选择光伏发电功率传感器，支持 W、kW。 |
| 组件温度 | 选择组件温度传感器，支持 °C、°F、K。 |
| 辐照度 | 选择与组件平面一致的辐照度传感器，支持 W/m²、kW/m²。 |
| 统计间隔 | 1、5 或 10 分钟，默认 5 分钟。 |
| 平均时长 | 实时数值取最近多长时间的平均值，默认 60 秒。 |
| 更新间隔 | 实时结果多久更新一次，默认 5 秒。 |

保存后打开**实时**。当前统计时段结束后，**历史**页会显示第一组已结算结果。在**数据超时**中，可设置每个传感器多久未更新就视为数据缺失。

## 发电预测

预测默认关闭，旧安装升级后也不会自动启用。在**设置 > 预测**中启用，填写组件倾角（0–90°）、罗盘朝向（北 0°、东 90°、南 180°、西 270°，或大于等于 0°、小于 360° 的自定义值），以及规格书中的 NOCT（大于 20°C、不超过 80°C，默认 45°C）。额定功率与 K 和监测共用。位置和时区自动来自已保存的 Home Assistant 连接，请在 HA 中修改。

Open-Meteo 提供今天及随后六个本地日历日的逐小时天气。选择日期可查看全天电量、逐小时功率曲线及区间数值明细，时间包含 UTC 偏移。今日预测包含今天全天，**今日剩余预测**只计算此刻至本地午夜；二者都基于最近一次成功获取的天气，与根据传感器读数计算的已结算理论电量独立。两次天气获取之间，剩余电量也随时间推进而减少；新天气还可修订全天预测。

天气通常每小时刷新，也可点击**刷新预测**。匹配的缓存会在重启后保留。刷新失败时保留原获取时间并标记为过期，15 分钟后重试；数据超过或达到两小时也标记为过期。天气区间缺失时，受影响的总量显示不可用，并单独显示完整度，缺失值不会当作零。页面明确区分关闭、HA 位置不可用、首次加载和无可用数据等状态。

这是单组光伏阵列的理论直流参考值，采用组件平面辐照度和简化 NOCT 温度模型，不包含逆变器效率或削峰、遮挡、积雪、污损及系统损耗，不保证实际交流发电量。四个预测实体的单位为 kWh、设备类型为 energy，且没有 `state_class`；刷新后可下降，与监测累计电量独立，不提供 HA 原生预测或能源仪表盘集成。

## 输出实体

| 结果 | 实体 ID | 单位 |
| --- | --- | --- |
| 预计功率 | `sensor.pvyieldlens_estimated_power` | W |
| 实际功率 | `sensor.pvyieldlens_actual_power` | W |
| PR | `sensor.pvyieldlens_pr` | % |
| 今日预计电量 | `sensor.pvyieldlens_daily_estimated_energy` | kWh |
| 累计预计电量 | `sensor.pvyieldlens_total_estimated_energy` | kWh |
| 实时预计功率 | `sensor.pvyieldlens_realtime_estimated_power` | W |
| 实时实际功率 | `sensor.pvyieldlens_realtime_actual_power` | W |
| 实时 PR | `sensor.pvyieldlens_realtime_pr` | % |
| 实时功率差 | `sensor.pvyieldlens_realtime_optimizable_power` | W |
| 今日预测电量 | `sensor.pvyieldlens_forecast_energy_today` | kWh |
| 今日剩余预测电量 | `sensor.pvyieldlens_forecast_energy_remaining_today` | kWh |
| 明日预测电量 | `sensor.pvyieldlens_forecast_energy_tomorrow` | kWh |
| 七日预测电量 | `sensor.pvyieldlens_forecast_energy_7d` | kWh |

## PR 公式

预计功率根据组件额定功率、温度和辐照度计算：

```text
P_expected = P_rated × [1 + (K / 100) × (T − 25)] × G / 1000
PR = P_actual / P_expected × 100%
```

`P_rated`：总额定功率（W）；`K`：温度系数（%/°C）；`T`：组件温度（°C）；`G`：组件平面的辐照度（W/m²）。

PR 表示实际功率占预计功率的比例。功率差为预计功率减去实际功率。

## 如何看结果

- PR 可以超过 100%。预计功率为零时，不显示 PR。
- 功率差为负，表示实际功率高于预计功率。
- 仅累计三个传感器都有数据时的电量，缺失时段不计入。
- 今日电量按 Home Assistant 时区在午夜归零；累计电量从首次配置开始计算。

中断后，部分时段的数据可能仍然缺失。更新或重新安装时，请保留应用数据。App 请使用 Home Assistant 备份；独立 Docker 部署请先停止容器，再复制 `/data` 目录。
