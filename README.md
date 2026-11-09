# CARLA 数字孪生控制台

代码目录：`/home/liumeng/deepseek_workspace/carlaDT-service`。

## 当前车辆定义

- **虚拟车 = CARLA 中的车辆 actor**。导航、键盘控制、相机、轨迹及控制量来自同一 actor。
- **物理车 = 后续通过 ROS 接入的真实车辆**。目前尚未接入，物理状态与虚实误差为空，物理车控制和同步控制不可选，后端也拒绝这些模式。
- 独立运动学虚拟车、蓝色矩形框、相机蓝框叠加、模拟执行延迟及旧 P4 引擎已从当前控制流程删除。原 dt_dynamic_nav 项目及旧实验文件保留为归档，不参与当前控制。

## 启动

```bash
cd /home/liumeng/deepseek_workspace/carlaDT-service
./start.sh
```

打开 http://127.0.0.1:8765/ 。首次安装：创建 `.venv`，安装 `requirements.lock`；执行 `npm ci`、`npm run build`。

原生 CARLA 适配进程使用 `/home/liumeng/miniconda3/envs/carla/bin/python`，可通过 `CARLADT_CARLA_PYTHON` 覆盖，需与服务器匹配。当前本机服务器为自定义 0.9.13，官方示例目录为 0.9.16，跨版本原始示例被阻止。

## 起终点位姿

进入场景编排，选择自车或障碍车，打开“起终点”。分别点击起点、终点的“地图拖拽设定位姿”：按下确定位置，拖动箭头确定航向，松开确认。单击保留当前航向。支持直接输入数值。

起点保存 `x/y/z/yaw`，终点保存 `goal_x/goal_y/goal_yaw`；角度单位为度。点击“保存起终点”持久化，导出/导入场景也包含航向。旧场景缺少终点航向时，使用该车起点航向迁移。

生成 actor 使用起点航向；路线导航使用终点航向构造最后 5m 的接近路径，复位则导航至起点位姿。目标与接近路径必须处于可行驶车道，航向需符合车道方向；不会静默改写用户位姿。完成判定同时检查位置、航向（10°）及速度。

## 地图与页面

8 个页面，默认运行总览。导航栏下的整行控制栏仅总览显示。地图支持平移、缩放、适应全图及全屏。

底图为 CARLA 原生 Waypoint 的车道边界，0.5m 采样；在线读取当前 world.get_map()，离线由 CARLA 客户端解析对应 OpenDRIVE 文件并按内容哈希缓存。与官方 no_rendering_mode.py 一致，+X 向右、+Y 向下，单位米。底图、车辆、轨迹和选点使用同一变换。断线时记住最近地图，不混用其他地图历史轨迹。

顶部 CARLA 启动、重启、停止按钮读取实际进程与 RPC 状态。默认服务器目录 `/home/liumeng/deepseek_workspace/carla-build/carla-runtime`，可由 `CARLADT_SERVER_ROOT` 修改，日志为 `runtime/carla-server.log`。停止/重启会结束当前模拟世界。

已安装原生 RPC 安全关闭修复，并采用 Epic 画质、30 FPS 的隔离启动配置；详见 [原生闪退修复记录](docs/native-crash-fix.md)。可用 `CARLADT_QUALITY=Low` 和 `CARLADT_MAX_FPS=30` 修改画质与帧率。

## 验证范围

已核对起终点拖拽航向回填、ROS 模式禁用、原生 actor 控制语义、位姿配置与记录契约。当前模拟器未就绪，尚未验证新终点位姿控制的完整 CARLA 行驶结果。此前自定义服务器出现同步模式下自行推进帧的问题；控制台保留时钟校验并拒绝争抢 tick。

旧实验录像及论文结果图属于历史归档，其中的旧蓝框和旧指标不代表当前模型。当前动态时间窗需后续接入相应规划模块，真实 ROS 车控制与同步控制尚未实现。

```bash
npm run build
.venv/bin/python -m pytest -q
```
