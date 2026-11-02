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

1. 将仓库中的 `pvyieldlens` 文件夹复制到 Home Assistant 主机的 `/addons/pvyieldlens`。
2. 在 App 商店重新加载本地应用列表，安装并启动 **PVYieldLens**。
3. 打开 Web 页面，在**设置**中选择传感器并填写组件参数。

### Docker

下载本仓库并进入目录，创建配置文件：

```sh
cp .env.example .env
```

在 `.env` 中设置登录密码 `PVYL_WEB_PASSWORD`，然后启动：

```sh
docker compose up -d --build
```

打开 [localhost:8099](http://localhost:8099)，用户名为 `admin`，密码为刚设置的密码。在**设置**中填写 Home Assistant 地址和访问令牌，点击**加载传感器**。

默认只能在运行 Docker 的电脑上打开页面。如需其他设备访问，将 `compose.yaml` 中的 `127.0.0.1:8099:8099` 改为 `8099:8099`。

## 配置

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

保存后打开**概览**。当前统计时段结束后，会显示第一组历史结果。在**数据超时**中，可设置每个传感器多久未更新就视为数据缺失。

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
