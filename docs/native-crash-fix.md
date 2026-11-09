# CARLA 原生闪退修复 — 2026-11-09

## 已确认原因

最近多次原生崩溃为 `Exception thrown: close: Bad file descriptor`，堆栈经现有调试符号还原到 `rpc::detail::server_session::close()`。现用官方 CARLA rpclib v2.2.1_c5 在连接读线程和写线程均有关闭同一套接字的路径，且使用会抛异常的 `socket.close()`；本构建禁用异常，ASIO 抛错转为 Carla.cpp:136 的 Fatal。

另有历史崩溃为 Vulkan `VK_ERROR_DEVICE_LOST`，并有 NVIDIA Xid 109 上下文切换超时及 Xid 31 记录。这与 RPC 关闭异常属于不同错误路径。

## 已安装的原生改动

- 同一会话启动、读取回调、写入及关闭均经同一 strand 串行执行。
- 关闭操作幂等，取消/关闭均使用 error_code 接口，重复或失效描述符关闭不会中止 UE4。
- 保留原类布局，避免与现有 CARLA / UE4 对象文件 ABI 不一致。
- 以原 Clang/libc++ 构建环境编译 RPC，复用原 Shipping 对象文件重新链接；重新生成并部署可执行文件、debug 和 sym。未重新 Cook 地图、车辆和其他资产。

已部署至实际 carla-runtime 运行目录及 CARLA 源工程 Shipping 输出目录；服务器侧依赖库同步更新。

## GPU 稳定配置

控制台默认 `-quality-level=Epic`，使用隔离的 `runtime/carla-profile/Saved/Config/LinuxNoEditor` 配置目录，设置 FrameRateLimit 和 t.MaxFPS 为 30。Shipping 构建会忽略命令行 ExecCmds，因此本修复未继续使用该无效限帧方法。空闲/异步模式实测 3.00 秒推进 90 帧，约 29.97 FPS；CARLA 同步定步长采用 benchmark 模式，仿真可快于墙钟，其帧率不应直接与异步限帧混同；不会改动用户全局 UE4 配置、系统驱动或内核。

可使用 `CARLADT_QUALITY=Low` 切换为低画质、`CARLADT_MAX_FPS=30` 覆盖帧率；0 表示不限帧。更高负载可能重新暴露未定位的图形驱动问题，此配置属于缓解措施，不代表修复显卡驱动。

## 按钮恢复

被动读取 TCP LISTEN 表，不再裸连接 RPC 端口。回收已退出子进程，排除 zombie/dead。0.5 秒独立状态轮询不再被 RPC 连接或资源采样阻塞。断开后清空实时车辆及相机状态。真实空实例强制退出测试中，0.777 秒恢复为“启动可按，重启/停止不可按”，无需刷新。

## 已完成验证

1. 旧原生库的最小回归测试稳定触发 `close: Bad file descriptor`，退出码 134；修复库通过同一测试。
2. 隔离修复实例完成 1800 次短 TCP 连接、60 次合法 RPC 会话，无错误。
3. 带车辆 RGB 相机持续运行 181 秒，接收 1813 帧，无崩溃。
4. 正式入口已重启，核对实际进程加载的 SHA256 与安装修复文件一致。正式入口连续观测 121.3 秒，期间用户进行了导航、归位及再次导航，保持运行和连接；结果见 `runtime/diagnostics/installed-fix-verification.json`。
5. 控制台全部 30 项回归测试通过。长期 GPU 稳定性仍需持续实验验证。

## 备份与回滚

备份清单：`/home/liumeng/deepseek_workspace/carlaDT-service/native-fixes/backups/20261109-193741/manifest.json`。所有被替换文件先按内容哈希去重备份，并保存权限；替换采用同目录临时文件原子重命名。

停止 CARLA 后可恢复：

```bash
cd /home/liumeng/deepseek_workspace/carlaDT-service
.venv/bin/python native-fixes/deploy-native.py --restore /home/liumeng/deepseek_workspace/carlaDT-service/native-fixes/backups/20261109-193741/manifest.json
```

源码补丁：`native-fixes/rpclib-safe-close.patch`。构建脚本与回归测试保存在 native-fixes 目录，编译产物及原文件备份已加入 Git 忽略规则。

参考：[CARLA 官方 rpclib 关闭实现](https://github.com/carla-simulator/rpclib/blob/v2.2.1_c5/lib/rpc/detail/server_session.cc)、[CARLA 0.9.13 渲染配置](https://carla.readthedocs.io/en/0.9.13/adv_rendering_options/)、[NVIDIA Xid 目录](https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html)。
