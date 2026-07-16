# LMDrive 原生 CARLA 终端指令测试

该目录提供一个独立的 LMDrive 指令测试入口，不修改项目其他源码，不启动 Leaderboard/ScenarioRunner，也不加载 route XML。

运行链路为：

```text
终端符号（Turn-02-L）
  -> 官方英文模板
  -> LMDrive text_input
  -> LMDrive 原始预测航点
  -> 原 PID 数学逻辑
  -> carla.VehicleControl
```

测试器不会根据符号修改方向盘、油门或刹车。车辆没有按指令行驶时，该次结果就是模型失败，而不是由测试程序强制修正。

## 与 Leaderboard 版本的区别

- 使用原生 `carla.Client` 加载地图并生成车辆；
- 使用 `world.spawn_actor()` 直接挂载四路 RGB 相机和 LiDAR；
- 车速直接读取 ego vehicle velocity，并在 pygame 中显示 km/h；
- 直接加载 `vicuna_drive`、视觉编码器和 checkpoint；
- 模型输入只有相机、LiDAR、点数、车速和终端文本；
- 不实例化 `LMDriveAgent`、`AgentWrapper`、`CarlaDataProvider` 或 `RoutePlanner`；
- 使用测试目录内复制的官方 `instruction_dict.json` 静态文本字典，不依赖 Leaderboard 目录或运行框架。

当前配置使用 `memfuser_baseline_e1d3_return_feature` 和 LMDrive 默认的非 GRU 航点解码器。这两个分支不需要导航目标，因此原生运行时完全不创建该字段。启动时会检查模型分支；如果换成需要导航目标的模型，会直接报错，避免悄悄引入路线信息。

## 测试场景不是控制路线

`SPAWN_POINT_INDEX=auto` 会检查地图出生点前方最近的 junction，优先选择大约 25 米外且同时具有左转、直行和右转出口的测试场景。检查结果只用于确认指令在物理道路上可执行：

```text
Test scene only: next junction 24 m ahead; available actions: left, straight, right.
No action/path has been selected for LMDrive.
```

这些出口不会传给模型，也不会选择其中任何一条作为车辆路线。车辆具体驶向哪里完全由 LMDrive 预测航点决定。

## 启动

前置条件与已跑通的根目录 `run_lmdrive_ubuntu.sh` 相同：CARLA 0.9.10.1、项目 `.venv`、模型 checkpoint 和图形显示环境均可用。

在项目根目录执行：

```bash
bash instruction_test/run_instruction_test.sh
```

默认加载 `Town05`，初始指令为 `Other-03`，便于车辆运动前输入待测试指令：

```text
lmdrive> Turn-02-L
[navigation] Turn-02-L -> Please execute a left turn at the forthcoming intersection.
```

常用输入：

```text
Turn-02-L
Turn-02-R
Turn-02-S
Follow-01-L
Other-03
id 4
text Please turn left at the next intersection.
status
list turn
help
quit
```

官方 65 个 ID 和每个 ID 的 8 条英文模板均可输入。距离型模板和 `Other-05` 参数也由 `command_catalog.py` 填充。

## pygame 信息

界面显示：

- 当前终端符号及实际送入模型的英文 prompt；
- 当前时速（km/h）；
- LMDrive 原始油门、转向和刹车；
- 模型预测的前两个航点；
- 指令结束概率；
- 只读评估状态。

对无距离约束的 `Turn-01` 至 `Turn-04`，评估器记录车辆进入和驶出 junction 前后的 yaw 变化，显示：

```text
RAW model | waiting-junction:left
RAW model | in-junction:left
RAW pass | observed left (yaw -82 deg)
```

如果模型执行了相反方向，会显示 `RAW fail`。评估器只观察车辆，不修改控制。进入路口以后才输入指令时显示 `invalid-entered-late`，避免把无效时机误判为模型结果。距离型、环岛、变道及自由文本暂不自动评分，但仍会原样送入模型。

为了可重复比较左/直/右，建议每个指令重新启动一次测试，保持相同地图、出生点、天气和背景车辆配置。

## 场景配置

```bash
CARLA_TOWN=Town05 \
SPAWN_POINT_INDEX=auto \
BACKGROUND_VEHICLES=0 \
bash instruction_test/run_instruction_test.sh
```

固定出生点：

```bash
SPAWN_POINT_INDEX=12 bash instruction_test/run_instruction_test.sh
```

启动器会打印该出生点前方 junction 的可执行方向。如果待测方向不在列表中，应更换出生点；这表示场景不适合该指令，而不是需要添加控制路线。

## 配置变量

| 变量 | 默认值 | 作用 |
|---|---|---|
| `CARLA_TOWN` | `Town05` | 加载的 CARLA 地图 |
| `SPAWN_POINT_INDEX` | `auto` | 自动选择兼容路口场景，或指定整数编号 |
| `EGO_VEHICLE` | `vehicle.lincoln.mkz2017` | ego 车辆 blueprint |
| `BACKGROUND_VEHICLES` | `0` | 背景自动驾驶车辆数 |
| `CARLA_WEATHER` | `ClearNoon` | 天气预设 |
| `LMDRIVE_INITIAL_COMMAND` | `Other-03` | 初始终端指令 |
| `LMDRIVE_TEMPLATE_INDEX` | `0` | 官方模板编号 0–7 |
| `LMDRIVE_USE_NOTICE` | `0` | 是否将 notice 输入模型 |
| `LMDRIVE_SAVE_FRAMES` | `0` | 是否保存 pygame 帧 |
| `LMDRIVE_LLM_MODEL` | 原配置路径 | LLM 目录 |
| `LMDRIVE_VISION_CKPT` | 原配置路径 | 视觉编码器 checkpoint |
| `LMDRIVE_CHECKPOINT` | 原配置路径 | LMDrive checkpoint |

已有的 `CARLA_ROOT`、`PORT`、`TM_PORT`、`START_CARLA_SERVER`、`KEEP_CARLA_SERVER`、画质和窗口变量仍然适用。

## 文件说明

- `run_instruction_test.sh`：启动/连接并清理 CARLA Server；
- `standalone_client.py`：原生 CARLA Client、车辆、传感器同步和仿真循环；
- `native_lmdrive_runtime.py`：模型预处理、推理、原 PID 数学逻辑和 pygame；
- `terminal_commands.py`：线程安全的终端指令输入；
- `command_catalog.py`：65 个符号到官方模板的映射；
- `instruction_dict.json`：LMDrive 官方 65 个指令 ID 的静态模板副本；
- `junction_topology.py`：仅用于验证测试场景的局部路口出口检查；
- `raw_instruction_evaluator.py`：只读的转向结果判定；
- `interactive_lmdriver_config.py`：原生推理配置和 checkpoint 环境变量；
- `tests/`：无需 CARLA Server/GPU 的离线测试。
