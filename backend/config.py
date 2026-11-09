"""Validated session configuration. Pending changes apply at the next run."""
import os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator

ROOT = Path(__file__).resolve().parents[1]
ALGORITHM_ROOT = Path(os.environ.get('CARLADT_ALGORITHM_ROOT', '/home/liumeng/deepseek_workspace/carla-projects/dt_dynamic_nav'))
EXAMPLES_ROOT = Path(os.environ.get('CARLADT_EXAMPLES_ROOT', '/home/liumeng/deepseek_workspace/carla-0.9.16/PythonAPI/examples'))
CARLA_PYTHON = os.environ.get('CARLADT_CARLA_PYTHON', '/home/liumeng/miniconda3/envs/carla/bin/python')
RUNTIME = ROOT/'runtime'


class ConsoleConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)
    mode: Literal['virtual', 'physical', 'synchronized'] = 'virtual'
    algorithm: Literal['navigation'] = 'navigation'
    speed_kmh: float = Field(default=21.6, ge=0, le=100)
    dt: float = Field(default=.05, ge=.02, le=.1)
    min_gap: float = Field(default=.8, ge=.3, le=5)
    return_speed_kmh: float = Field(default=8., ge=2, le=20)
    arrival_distance: float = Field(default=.5, ge=.1, le=2)
    record_telemetry: bool = False
    record_video: bool = False

    @field_validator('mode')
    @classmethod
    def only_available_transport(cls,value):
        if value!='virtual':raise ValueError('真实物理车尚未通过 ROS 接入，当前仅支持控制 CARLA 虚拟车')
        return value


class ActorConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(max_length=60)
    role: Literal['ego', 'obstacle'] = 'obstacle'
    blueprint: str = Field(default='vehicle.tesla.model3', pattern=r'^vehicle\.[\w.]+$')
    x: float = Field(ge=-100000, le=100000)
    y: float = Field(ge=-100000, le=100000)
    z: float = Field(default=.5, ge=-1000, le=10000)
    yaw: float = Field(default=90, ge=-360, le=360)
    goal_x: float = Field(default=-1.75, ge=-100000, le=100000)
    goal_yaw: float = Field(default=90, ge=-360, le=360)
    goal_y: float = Field(default=15., ge=-100000, le=100000)
    speed_kmh: float = Field(default=6., ge=0, le=100)
    behavior: Literal['route', 'constant', 'stationary'] = 'route'


DEFAULT_ACTORS = [
    ActorConfig(id='ego', role='ego', blueprint='vehicle.nissan.patrol_2021', x=-1.6, y=-150., goal_y=15, speed_kmh=21.6).model_dump(),
    ActorConfig(id='obstacle-1', x=48, y=-77.45, yaw=180.15, goal_yaw=180.15, goal_x=-35, goal_y=-77.45, speed_kmh=19.8).model_dump(),
    ActorConfig(id='obstacle-2', x=-1.75, y=-61.5, goal_y=60, speed_kmh=3.6).model_dump(),
]

PARAMETERS = [
    ('session', 'speed_kmh', '巡航速度', 'km/h', 0, 100),
    ('session', 'dt', '控制周期', 's', .02, .1),
    ('safety', 'min_gap', '归位安全间距', 'm', .3, 5),
    ('reset', 'return_speed_kmh', '导航归位速度', 'km/h', 2, 20),
    ('reset', 'arrival_distance', '归位距离阈值', 'm', .1, 2),
]
