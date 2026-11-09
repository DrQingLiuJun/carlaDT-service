"""Read argparse metadata without importing or executing example scripts."""
import ast,os
from functools import lru_cache
from .config import EXAMPLES_ROOT,CARLA_PYTHON

META={
 'no_rendering_mode.py':('地图与驾驶','二维地图可视化','道路、标线与 actor 图层；支持缩放、平移及驾驶','builtin'),
 'manual_control.py':('地图与驾驶','键盘手动驾驶','WASD、相机、车灯、遥测与天气控制','builtin'),
 'automatic_control.py':('地图与驾驶','自动导航 Agent','Basic / Behavior / ConstantVelocity 导航','builtin'),
 'generate_traffic.py':('交通环境','背景交通生成','车辆、行人、Traffic Manager 与随机种子','native'),
 'dynamic_weather.py':('交通环境','动态天气','连续变化太阳、云层和降雨','native'),
 'vehicle_gallery.py':('地图与驾驶','车辆蓝图库','生成车辆并切换观察视角','native'),
 'tutorial.py':('地图与驾驶','基础场景教程','生成车辆、自动驾驶与相机采集','native'),
 'client_bounding_boxes.py':('感知与传感器','客户端包围盒','简单驾驶与包围盒投影','native'),
 'bounding_boxes.py':('感知与传感器','二维 / 三维包围盒','可视化并记录图像和标注','native'),
 'visualize_multiple_sensors.py':('感知与传感器','多传感器窗口','多相机、LiDAR 与语义 LiDAR','native'),
 'open3d_lidar.py':('感知与传感器','Open3D 点云','独立原生点云窗口，需 Open3D','native'),
 'lidar_to_camera.py':('感知与传感器','LiDAR 相机投影','点云与 RGB 融合及图像保存','native'),
 'draw_skeleton.py':('感知与传感器','行人骨架','行人骨架三维投影与显示','native'),
 'tutorial_gbuffer.py':('感知与传感器','GBuffer 渲染通道','相机颜色、深度、法线等纹理采集','native'),
 'synchronous_mode.py':('同步与记录','同步模式','同步时钟与传感器取帧示例','native'),
 'sensor_synchronization.py':('同步与记录','传感器帧同步','队列收集与帧号一致性','native'),
 'start_recording.py':('同步与记录','CARLA 场景记录','记录仿真，同时生成测试车辆','native'),
 'start_replaying.py':('同步与记录','CARLA 场景回放','时间区间、倍速与跟随相机','native'),
 'show_recorder_file_info.py':('同步与记录','记录文件信息','查询记录帧和事件','native'),
 'show_recorder_collisions.py':('同步与记录','碰撞事件查询','查询记录中的碰撞对象','native'),
 'show_recorder_actors_blocked.py':('同步与记录','受阻车辆查询','查找长时间受阻 actor','native'),
 'vehicle_physics.py':('高级扩展','车辆物理实验','力、冲量和车辆状态','native'),
 'get_component_test.py':('高级扩展','车辆部件检查','查询车辆部件世界变换','native'),
 'V2XDemo.py':('高级扩展','V2X 驾驶演示','驾驶与 V2X 消息接收','native'),
 'test_addsecondvx.py':('高级扩展','V2X 增车测试','本地小型测试入口，固定连接地址','native'),
 'manual_control_steeringwheel.py':('高级扩展','方向盘驾驶','需要方向盘和 wheel_config.ini','native'),
 'manual_control_carsim.py':('高级扩展','CarSim 动力学','需要 CarSim 许可、车辆配置与支持构建','native'),
 'manual_control_chrono.py':('高级扩展','Chrono 动力学','需要 Chrono 构建和车辆配置','native'),
 'invertedai_traffic.py':('高级扩展','InvertedAI 交通','需要 SDK、API 凭据和外部服务','native'),
 'carla_cosmos_gen.py':('高级扩展','Cosmos 数据生成','基于 CARLA 记录生成传感器控制数据','native'),
 'ros2/ros2_native.py':('高级扩展','ROS2 原生接口','需要 --ros2 服务启动与 ROS2/RViz 环境','native'),
 'rss/manual_control_rss.py':('高级扩展','RSS 安全驾驶','需要支持 RSS 的 CARLA 构建','native'),
 'nvidia/nurec/example_nurec_replay_save_images.py':('高级扩展','NVIDIA NuRec 回放','需要 NuRec 服务、模型和场景数据','native'),
 'nvidia/cosmos/client/carla_cosmos_gen.py':('高级扩展','NVIDIA Cosmos 管线','需要 Cosmos 配置与服务环境','native'),
}


@lru_cache(maxsize=1)
def catalog():
    out=[]
    for filename,(category,title,description,kind) in META.items():
        path=EXAMPLES_ROOT/filename;args=[];deps=[]
        if path.is_file():
            try:
                tree=ast.parse(path.read_text())
                for n in ast.walk(tree):
                    if isinstance(n,ast.Import):deps.extend(x.name.split('.')[0] for x in n.names)
                    if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='add_argument':
                        flags=[a.value for a in n.args if isinstance(a,ast.Constant) and isinstance(a.value,str) and a.value.startswith('-')]
                        if not flags:continue
                        kw={k.arg:k.value for k in n.keywords};flag=next((f for f in flags if f.startswith('--')),flags[0])
                        helpv=kw.get('help');default=kw.get('default');action=kw.get('action')
                        args.append(dict(flag=flag,flags=flags,help=helpv.value if isinstance(helpv,ast.Constant) and isinstance(helpv.value,str) else flag,
                            default=default.value if isinstance(default,ast.Constant) else None,
                            boolean=isinstance(action,ast.Constant) and action.value in ['store_true','store_false']))
            except (ValueError,SyntaxError):pass
        out.append(dict(id=filename,category=category,title=title,description=description,kind=kind,exists=path.is_file(),
            args=args,dependencies=sorted(set(deps)),version='0.9.16',presentation='网页原生' if kind=='builtin' else '本机原生窗口 / 文件 / 日志'))
    return out


def build_command(filename,args,server_version):
    item=next((x for x in catalog() if x['id']==filename),None)
    if not item or not item['exists']:raise ValueError('示例不存在或不在允许列表中')
    if not server_version.startswith('0.9.16'):raise ValueError('此示例为 0.9.16，当前 CARLA 版本不匹配；可使用网页原生适配功能')
    allowed={flag:a for a in item['args'] for flag in a['flags']};cmd=[os.environ.get('CARLADT_EXAMPLES_PYTHON',CARLA_PYTHON),str(EXAMPLES_ROOT/filename)]
    for key,value in args.items():
        if key not in allowed:raise ValueError('未声明的示例参数：'+key)
        if value in ['',None,False]:continue
        if allowed[key]['boolean']:
            if value is True:cmd.append(key)
            else:raise ValueError('布尔参数必须为 true / false')
        else:
            if isinstance(value,(dict,list)) or len(str(value))>500:raise ValueError('无效参数值')
            cmd.extend([key,str(value)])
    return cmd
