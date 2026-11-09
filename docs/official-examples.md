# 官方示例清单

来自本机 CARLA 0.9.16/PythonAPI/examples。网页入口提供常用适配功能；“官方原程序”启动本机原程序，需要匹配的CARLA及依赖。

| 程序 | 功能 | 接入方式 |
|---|---|---|
| `no_rendering_mode.py` | 道路、标线与 actor 图层；支持缩放、平移及驾驶 | 网页适配 + 官方原程序 |
| `manual_control.py` | WASD、相机、车灯、遥测与天气控制 | 网页适配 + 官方原程序 |
| `automatic_control.py` | Basic / Behavior / ConstantVelocity 导航 | 网页适配 + 官方原程序 |
| `generate_traffic.py` | 车辆、行人、Traffic Manager 与随机种子 | 本机原程序 / 日志 |
| `dynamic_weather.py` | 连续变化太阳、云层和降雨 | 本机原程序 / 日志 |
| `vehicle_gallery.py` | 生成车辆并切换观察视角 | 本机原程序 / 日志 |
| `tutorial.py` | 生成车辆、自动驾驶与相机采集 | 本机原程序 / 日志 |
| `client_bounding_boxes.py` | 简单驾驶与包围盒投影 | 本机原程序 / 日志 |
| `bounding_boxes.py` | 可视化并记录图像和标注 | 本机原程序 / 日志 |
| `visualize_multiple_sensors.py` | 多相机、LiDAR 与语义 LiDAR | 本机原程序 / 日志 |
| `open3d_lidar.py` | 独立原生点云窗口，需 Open3D | 本机原程序 / 日志 |
| `lidar_to_camera.py` | 点云与 RGB 融合及图像保存 | 本机原程序 / 日志 |
| `draw_skeleton.py` | 行人骨架三维投影与显示 | 本机原程序 / 日志 |
| `tutorial_gbuffer.py` | 相机颜色、深度、法线等纹理采集 | 本机原程序 / 日志 |
| `synchronous_mode.py` | 同步时钟与传感器取帧示例 | 本机原程序 / 日志 |
| `sensor_synchronization.py` | 队列收集与帧号一致性 | 本机原程序 / 日志 |
| `start_recording.py` | 记录仿真，同时生成测试车辆 | 本机原程序 / 日志 |
| `start_replaying.py` | 时间区间、倍速与跟随相机 | 本机原程序 / 日志 |
| `show_recorder_file_info.py` | 查询记录帧和事件 | 本机原程序 / 日志 |
| `show_recorder_collisions.py` | 查询记录中的碰撞对象 | 本机原程序 / 日志 |
| `show_recorder_actors_blocked.py` | 查找长时间受阻 actor | 本机原程序 / 日志 |
| `vehicle_physics.py` | 力、冲量和车辆状态 | 本机原程序 / 日志 |
| `get_component_test.py` | 查询车辆部件世界变换 | 本机原程序 / 日志 |
| `V2XDemo.py` | 驾驶与 V2X 消息接收 | 本机原程序 / 日志 |
| `test_addsecondvx.py` | 本地小型测试入口，固定连接地址 | 本机原程序 / 日志 |
| `manual_control_steeringwheel.py` | 需要方向盘和 wheel_config.ini | 本机原程序 / 日志 |
| `manual_control_carsim.py` | 需要 CarSim 许可、车辆配置与支持构建 | 本机原程序 / 日志 |
| `manual_control_chrono.py` | 需要 Chrono 构建和车辆配置 | 本机原程序 / 日志 |
| `invertedai_traffic.py` | 需要 SDK、API 凭据和外部服务 | 本机原程序 / 日志 |
| `carla_cosmos_gen.py` | 基于 CARLA 记录生成传感器控制数据 | 本机原程序 / 日志 |
| `ros2/ros2_native.py` | 需要 --ros2 服务启动与 ROS2/RViz 环境 | 本机原程序 / 日志 |
| `rss/manual_control_rss.py` | 需要支持 RSS 的 CARLA 构建 | 本机原程序 / 日志 |
| `nvidia/nurec/example_nurec_replay_save_images.py` | 需要 NuRec 服务、模型和场景数据 | 本机原程序 / 日志 |
| `nvidia/cosmos/client/carla_cosmos_gen.py` | 需要 Cosmos 配置与服务环境 | 本机原程序 / 日志 |
