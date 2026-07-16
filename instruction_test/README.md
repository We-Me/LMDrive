# LMDrive 无路线终端指令测试

这个目录提供独立的交互测试入口，不修改 LMDrive、Leaderboard 或 ScenarioRunner 的现有源码，也不加载 route XML。测试只做以下事情：

1. 启动或连接 CARLA Server；
2. 加载指定地图；
3. 在一个出生点生成 ego 车辆，可选生成背景交通车辆；
4. 挂载原 LMDrive 的相机、LiDAR、IMU、GNSS 和速度传感器；
5. 加载原 LMDrive 模型并打开 pygame；
6. 将终端输入的 `Turn-02-L` 等指令送入模型，由原 PID 控制器控制车辆。

`Turn-02-L` 不会被转换成固定方向盘角度。它会映射为官方 ID 4 的自然语言模板（默认第 0 条：`Please execute a left turn at the forthcoming intersection.`），再送入 LMDrive 的 `text_input`；最终油门、刹车和转向仍来自模型预测航点及原 PID 控制器。

## 为什么不需要路线

原 `LMDriveAgent` 通过 Leaderboard 运行时会强制读取 `_global_plan` 并构造 `target_point`，但当前项目实际使用的 `memfuser_baseline_e1d3_return_feature` 分支并不消费 `target_point`，LMDrive 语言航点解码器中的目标点相加也被注释为 `x_in = x # + target_point`。因此本工具只为接口提供固定的中性 `[0, 0]`，不创建、不跟随也不评分路线；测试会一直运行到输入 `quit` 或按 `Ctrl+C`。

## 启动

前置条件与已经跑通的根目录 `run_lmdrive_ubuntu.sh` 相同：

- `${CARLA_ROOT}` 指向 CARLA 0.9.10.1；
- 根目录 `.venv` 和模型 checkpoint 可用；
- Linux 有可用图形显示环境，pygame 和 CARLA 窗口能够打开。

在项目根目录执行：

```bash
bash instruction_test/run_instruction_test.sh
```

默认加载 `Town05`。`SPAWN_POINT_INDEX=auto` 会在地图出生点中寻找一个约 25 米后进入路口的位置，这样可以直接测试转向指令。初始化完成后终端出现：

```text
lmdrive>
```

初始指令是 `Other-03`（立即停车），便于在车辆运动前输入测试指令：

```text
lmdrive> Turn-02-L
[navigation] Turn-02-L -> Please execute a left turn at the forthcoming intersection.
```

常用输入：

```text
Turn-02-L
Turn-02-R
Turn-02-S
Turn-02-L-dis 20
Follow-01-L
Other-05 30 left 5
id 4
text Please turn left at the next intersection.
start
stop
free
status
list turn
help
quit
```

官方字典的 65 个 ID 均可使用；`list` 显示完整符号及参数。`template 0` 到 `template 7` 可切换每个 ID 的 8 种官方英文表达。重复输入同一个符号也会清空旧视觉历史，将其作为一段新指令执行。

## 地图、出生点和车辆

这些配置只负责初始化场景，不会生成路线：

```bash
CARLA_TOWN=Town03 \
SPAWN_POINT_INDEX=auto \
EGO_VEHICLE=vehicle.lincoln.mkz2017 \
BACKGROUND_VEHICLES=20 \
bash instruction_test/run_instruction_test.sh
```

如果要固定出生点，设置其整数编号；工具会打印选中点的坐标和前方路口估计距离：

```bash
SPAWN_POINT_INDEX=12 bash instruction_test/run_instruction_test.sh
```

## Notice 指令

输入 `Notice-01` 或 `notice Notice-01` 会设置 notice。原配置默认 `agent_use_notice=False`，此时 notice 只显示在 pygame 中。要把 notice 同时送入模型：

```bash
LMDRIVE_USE_NOTICE=1 bash instruction_test/run_instruction_test.sh
```

清除 notice：

```text
notice clear
```

## 配置变量

| 变量 | 默认值 | 作用 |
|---|---|---|
| `CARLA_TOWN` | `Town05` | 加载的 CARLA 地图 |
| `SPAWN_POINT_INDEX` | `auto` | 自动选择路口前出生点，或指定整数编号 |
| `EGO_VEHICLE` | `vehicle.lincoln.mkz2017` | ego 车辆 blueprint |
| `BACKGROUND_VEHICLES` | `0` | 背景自动驾驶车辆数 |
| `CARLA_WEATHER` | `ClearNoon` | CARLA 天气预设 |
| `LMDRIVE_INITIAL_COMMAND` | `Other-03` | 初始指令 |
| `LMDRIVE_TEMPLATE_INDEX` | `0` | 官方模板编号，范围 0–7 |
| `LMDRIVE_USE_NOTICE` | `0` | 是否将 notice 输入模型 |
| `LMDRIVE_SAVE_FRAMES` | `0` | 是否保存 pygame 每帧截图 |
| `LMDRIVE_LLM_MODEL` | 原配置值 | 覆盖 LLM 目录 |
| `LMDRIVE_VISION_CKPT` | 原配置值 | 覆盖视觉编码器 checkpoint |
| `LMDRIVE_CHECKPOINT` | 原配置值 | 覆盖 LMDrive checkpoint |

根启动器已有的 `CARLA_ROOT`、`PORT`、`TM_PORT`、`START_CARLA_SERVER`、`KEEP_CARLA_SERVER`、画质和窗口变量仍然适用。例如连接已启动的 CARLA：

```bash
START_CARLA_SERVER=0 \
KEEP_CARLA_SERVER=1 \
bash instruction_test/run_instruction_test.sh
```

日志及可选帧截图写入 `instruction_test/output/`。

## 文件说明

- `run_instruction_test.sh`：配置 PythonAPI，并启动/清理 CARLA Server；
- `standalone_client.py`：无路线的地图、车辆、传感器和同步仿真循环；
- `interactive_lmdriver_agent.py`：中性目标点、终端 instruction 和 pygame 信息叠加；
- `interactive_lmdriver_config.py`：不改原配置的环境变量覆盖层；
- `command_catalog.py`：65 个官方符号到 ID/自然语言模板的解析；
- `tests/`：无需 CARLA/GPU 的映射与交互层测试。
