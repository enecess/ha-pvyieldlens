# PVYieldLens 使用说明 / User guide

打开 Web UI，在设置中选择实际功率、组件温度和同平面辐照度实体，输入总额定功率与温度系数。K 的单位为 `%/°C`，规格书 `-0.35%/°C` 就填写 `-0.35`，无需转换。

App 自动通过 Supervisor 连接；独立 Docker 需要 HA 地址、管理员长期访问令牌和 `PVYL_WEB_PASSWORD`，Web 用户名为 `admin`。

统计粒度为 1／5／10 分钟，实时默认最近 60 秒平滑、每 5 秒更新。高级保持期限默认功率／辐照 300 秒、温度 900 秒，超时作为缺测。使用瞬时／持续状态来源，不自动将区间平均值视为瞬时值。

预计、实际功率和 PR 使用共同有效时段，预计电量也只累计这些时段。部分覆盖显示比例，不把缺测补零。预计功率为零时 PR 不可用；PR 可超过 100%，可优化功率可为负。

Web 支持中、英、法、德、波兰、意大利语，自动跟随浏览器语言，缺省英语。App 配置项翻译跟随 HA 界面语言。

保留并备份 `/data`。日累计按 HA 时区重置，总累计不重置；删除数据会丢失累计与配置。历史补算不能写入 HA 过去的时间点。服务异常终止可能留下旧 REST 状态，请检查时间属性。完整说明见仓库 README。

## English

Select PV power, module temperature and plane-of-array irradiance sensors. Enter rated power in watts and the datasheet coefficient directly: **−0.35 %/°C → −0.35**.

App authentication is automatic. Standalone Docker needs a HA URL, administrator long-lived token and a Web password (username `admin`). Statistics use 1/5/10-minute windows; live data defaults to a 60-second average updated every 5 seconds.

Inputs must be instantaneous or persistent states. Missing data is not replaced by zero. Energy accumulates only while all three sources are valid. Back up `/data`. REST entities lack native registry management and cannot insert historical Recorder states; a crashed service may leave stale states. The dashboard follows browser language preferences, with English fallback.
