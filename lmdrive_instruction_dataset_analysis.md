# LMDrive Instruction 数据解析

本文档记录对 `data/LMDrive` 中非传感器数据部分的解析结果，主要包括：

- `dataset_index.txt`
- `navigation_instruction_list.txt`
- `notice_instruction_list.json`
- 便于阅读和直接加载的 `data/LMDrive/instruction_dict.json`
- 本地参考仓库中的 `refer/LMDrive/leaderboard/leaderboard/envs/instruction_dict.json`
- LMDrive 论文 Appendix D: Instruction Details

统计时间为 2026-07-15。当前未下载约 2 TB 的 `data/` 传感器文件，因此本文不验证图像、LiDAR、测量值等逐帧数据。

## 1. 总体结论

LMDrive 官方定义了 56 种基础 instruction：

- 16 种 Follow 指令；
- 25 种 Turn 指令；
- 5 种 Others 指令；
- 10 种 Notice 指令。

此外，instruction 字典包含 9 种连续转向指令，因此字典实际包含 65 个 instruction ID。已直接解析本地文件 `refer/LMDrive/leaderboard/leaderboard/envs/instruction_dict.json`，确认每个 ID 均有 8 种英文表达模板，共计 520 条模板。下文表格中的英文列取该 ID 的第一条模板作为代表，训练时会从对应的 8 条模板中随机选择。

本地下载的数据实际出现了 55 个 ID：

- 46 个导航 instruction ID；
- 9 个 notice instruction ID；
- 未出现连续转向 ID 25–33；
- 未出现前车突然停车 notice ID 52。

## 2. Instruction ID 定义

### 2.1 Turn 指令

| ID | 符号名称 | 语义 | 字典代表模板 |
|---:|---|---|---|
| 0 | `Turn-01-L` | 前方左转 | `Proceed ahead and make a left turn.` |
| 1 | `Turn-01-R` | 前方右转 | `Proceed ahead and make a right turn.` |
| 2 | `Turn-01-L-dis` | 行驶 `[x]` 米后左转 | `After [x] meters, execute a left turn.` |
| 3 | `Turn-01-R-dis` | 行驶 `[x]` 米后右转 | `After [x] meters, execute a right turn.` |
| 4 | `Turn-02-L` | 在下一个普通路口左转 | `Please execute a left turn at the forthcoming intersection.` |
| 5 | `Turn-02-R` | 在下一个普通路口右转 | `Please execute a right turn at the upcoming intersection.` |
| 6 | `Turn-02-S` | 在下一个普通路口直行 | `Please proceed straight at the next intersection.` |
| 7 | `Turn-02-L-dis` | 行驶 `[x]` 米后在路口左转 | `After traveling [x] meters, you are directed to make a left turn at the intersection.` |
| 8 | `Turn-02-R-dis` | 行驶 `[x]` 米后在路口右转 | `After advancing [x] meters, you are directed to make a right turn at the intersection.` |
| 9 | `Turn-02-S-dis` | 行驶 `[x]` 米后在路口直行 | `After covering a distance of [x] meters, please continue straight at the intersection.` |
| 10 | `Turn-03-L` | 在下一个交通信号灯处左转 | `Please execute a left turn at the subsequent traffic signal.` |
| 11 | `Turn-03-R` | 在下一个交通信号灯处右转 | `Please execute a right turn upon reaching the upcoming traffic signal.` |
| 12 | `Turn-03-S` | 在下一个交通信号灯处直行 | `Please maintain your course straight at the next traffic signal.` |
| 13 | `Turn-03-L-dis` | 行驶 `[x]` 米后在交通信号灯处左转 | `Upon traversing [x] meters, execute a left turn at the traffic signal.` |
| 14 | `Turn-03-R-dis` | 行驶 `[x]` 米后在交通信号灯处右转 | `After covering a distance of [x] meters, execute a right turn at the traffic signal.` |
| 15 | `Turn-03-S-dis` | 行驶 `[x]` 米后在交通信号灯处直行 | `After traveling [x] meters, maintain your course straight at the traffic signal.` |
| 16 | `Turn-04-L` | 在下一个 T 型路口左转 | `At the ensuing T-intersection, make a left turn.` |
| 17 | `Turn-04-R` | 在下一个 T 型路口右转 | `At the forthcoming T-intersection, execute a right turn.` |
| 18 | `Turn-04-S` | 在下一个 T 型路口直行 | `At the upcoming T-intersection, proceed straight.` |
| 19 | `Turn-04-L-dis` | 行驶 `[x]` 米后在 T 型路口左转 | `In another [x] meters, you'll be turning left at the T-junction, alright?` |
| 20 | `Turn-04-R-dis` | 行驶 `[x]` 米后在 T 型路口右转 | `After [x] meters, you'll want to turn right at the T-junction, okay?` |
| 21 | `Turn-04-S-dis` | 行驶 `[x]` 米后在 T 型路口直行 | `After advancing [x] meters, continue straight at the T-intersection.` |
| 22 | `Turn-05-1` | 从环岛第一出口驶出 | `Depart at the first exit on the roundabout.` |
| 23 | `Turn-05-2` | 从环岛第二出口驶出 | `Depart at the second exit on the roundabout.` |
| 24 | `Turn-05-3` | 从环岛第三出口驶出 | `Depart at the third exit on the roundabout.` |

### 2.2 连续转向指令

ID 25–33 描述当前路口和下一个路口的连续动作。它们存在于官方 `instruction_dict.json`，但没有出现在当前下载的 `navigation_instruction_list.txt` 中。

| ID | 当前路口 | 下一个路口 | 字典代表模板 |
|---:|---|---|---|
| 25 | 左转 | 左转 | `After making a left turn at the current intersection, make a left turn at the next intersection.` |
| 26 | 左转 | 右转 | `After making a left turn at the current intersection, make a right turn at the next intersection.` |
| 27 | 左转 | 直行 | `After making a left turn at the current intersection, continue straight at the next intersection.` |
| 28 | 右转 | 左转 | `After making a right turn at the current intersection, make a left turn at the next intersection.` |
| 29 | 右转 | 右转 | `After making a right turn at the current intersection, make a right turn at the next intersection.` |
| 30 | 右转 | 直行 | `After making a right turn at the current intersection, continue straight at the next intersection.` |
| 31 | 直行 | 左转 | `After proceeding straight through the current intersection, make a left turn at the next intersection.` |
| 32 | 直行 | 右转 | `After proceeding straight through the current intersection, make a right turn at the next intersection.` |
| 33 | 直行 | 直行 | `After proceeding straight through the current intersection, continue straight at the next intersection.` |

### 2.3 Follow 指令

| ID | 符号名称 | 语义 | 字典代表模板 |
|---:|---|---|---|
| 34 | `Follow-01-L` | 向左变道 | `Transition to the left lane for travel.` |
| 35 | `Follow-01-R` | 向右变道 | `Transition to the right lane for travel.` |
| 36 | `Follow-01-L-dis` | 行驶 `[x]` 米后向左变道 | `After [x] meters, transition to the left lane for travel.` |
| 37 | `Follow-01-R-dis` | 行驶 `[x]` 米后向右变道 | `After [x] meters, transition to the right lane for travel.` |
| 38 | `Follow-02-s1` | 沿当前道路继续行驶 | `Proceed along this route.` |
| 39 | `Follow-02-s2` | 沿高速公路继续行驶 | `Proceed along the highway.` |
| 40 | `Follow-02-s1-dis` | 沿当前道路继续行驶 `[x]` 米 | `Proceed along this route for [x] meters.` |
| 41 | `Follow-02-s2-dis` | 沿高速公路继续行驶 `[x]` 米 | `Proceed along the highway for [x] meters.` |
| 42 | `Follow-03-s1` | 保持当前行驶方向 | `Maintain your current course.` |
| 43 | `Follow-03-s2` | 保持当前方向直至下一个路口 | `Maintain your current course until the upcoming intersection.` |
| 44 | `Follow-03-s1-dis` | 保持当前方向行驶 `[x]` 米 | `Maintain your current course for [x] meters.` |
| 45 | `Follow-03-s2-dis` | 保持当前方向，并按字典给出的距离约束行驶至下一路口 | `Maintain your current course until the upcoming intersection for [x] meters.` |
| 46 | `Follow-04-L` | 向左侧移动，准备进入高速公路 | `Veering to the left, prepare to enter the highway.` |
| 47 | `Follow-04-R` | 向右侧移动，准备驶出高速公路 | `Veering to the right, prepare to exit the highway.` |
| 48 | `Follow-04-L-dis` | 行驶 `[x]` 米后向左侧驶出高速公路 | `In [x] meters, veer to the left, prepare to exit the highway.` |
| 49 | `Follow-04-R-dis` | 行驶 `[x]` 米后向右侧驶出高速公路 | `In [x] meters, veer to the right, prepare to exit the highway.` |

### 2.4 Notice 指令

| ID | 符号名称 | 语义 | 字典代表模板 |
|---:|---|---|---|
| 50 | `Notice-01` | 注意前方行人 | `Be mindful of pedestrians ahead.` |
| 51 | `Notice-02` | 注意前方自行车 | `Be mindful of the bicycle ahead.` |
| 52 | `Notice-03` | 注意前车突然停车 | `Be mindful of the vehicle performing an abrupt stop ahead.` |
| 53 | `Notice-04` | 注意左侧闯红灯车辆 | `Be mindful of the vehicle crossing on a red light to your left.` |
| 54 | `Notice-05` | 注意前方闯红灯车辆 | `Be mindful of the vehicle crossing on a red light ahead.` |
| 55 | `Notice-06` | 注意前方崎岖或不平路面 | `Be mindful of the rough road surface ahead.` |
| 56 | `Notice-07` | 注意前方隧道 | `Be mindful of the forthcoming tunnel.` |
| 57 | `Notice-08-R` | 前方为红灯 | `Be mindful of the red light ahead.` |
| 58 | `Notice-08-G` | 前方为绿灯 | `Be mindful of the green light ahead.` |
| 59 | `Notice-08-Y` | 前方为黄灯 | `Be mindful of the yellow light ahead.` |

当前下载的数据没有 ID 52。

### 2.5 Others 指令

| ID | 符号名称 | 语义 | 字典代表模板 |
|---:|---|---|---|
| 60 | `Other-01` | 开始驾驶 | `Please commence driving.` |
| 61 | `Other-02` | 立即减速 | `Please decelerate immediately.` |
| 62 | `Other-03` | 立即停车 | `Please halt your vehicle immediately.` |
| 63 | `Other-04` | 自由驾驶 | `You are permitted to drive freely.` |
| 64 | `Other-05` | 驶向给定相对导航点 | `Please proceed towards the navigation point; the following point is [x] meters ahead and [y] meters to your left/right.` |

ID 64 的模板大意为：导航点位于前方 `[x]` 米、左侧或右侧 `[y]` 米处。

## 3. Instruction 参数

`navigation_instruction_list.txt` 中的 `instruction_args` 用来填充自然语言模板中的变量。

当前项目的数据集实现按以下方式替换：

| 模板标记 | 参数位置 | 含义 |
|---|---:|---|
| `[x]` | 0 | 前向距离或行驶距离 |
| `left/right` | 1 | `left`、`right` 或 `straight` |
| `[y]` | 2 | 横向距离 |

普通距离型指令通常只有一个参数，例如：

```json
{
  "instruction": "Turn-03-S-dis",
  "instruction_id": 15,
  "instruction_args": [6]
}
```

ID 64 使用三个参数，例如：

```json
{
  "instruction": "Other-05",
  "instruction_id": 64,
  "instruction_args": [13, "left", 13]
}
```

本地数据中的距离范围具有以下特点：

- 普通转向、变道等距离参数通常为 2–20 米；
- Follow 类长距离参数可超过 20 米；
- `Follow-03-s1-dis` 的最大值达到 172 米；
- ID 64 的前向距离范围为 1–59 米，横向距离范围为 0–47 米。

### 3.1 模板是否真实参与训练

模板映射真实存在，并且被官方训练和在线评测代码实际调用，不是根据 `Turn-03-S-dis` 等符号名称推测出来的自然语言描述。

完整链路如下：

1. 数据解析阶段根据驾驶规则生成 clip，只在 `navigation_instruction_list.txt` 中保存符号名称、`instruction_id` 和 `instruction_args`；
2. 官方训练数据集初始化时读取 `leaderboard/leaderboard/envs/instruction_dict.json`；
3. 每次执行 `__getitem__` 时，根据 `instruction_id` 从对应的 8 条模板中随机选择一条；
4. 对包含参数的模板，设计上应使用 `instruction_args` 填充 `[x]`、`left/right` 和 `[y]`，但官方训练加载器在这一步存在下文所述的返回值未保存问题；
5. 最终自然语言通过 `text_input` 传入 LMDrive 模型。

官方数据解析代码写入 ID 和符号名称的位置为：

```python
result['instruction'] = rule
result['instruction_id'] = rule_id
```

官方训练数据集读取字典并选择模板的核心逻辑为：

```python
instruction_json = os.path.join(
    curr_dir,
    "../../../../",
    "leaderboard/leaderboard/envs",
    "instruction_dict.json",
)
INSTRUCTION_DICT = json.load(open(instruction_json))

instruction_text = np.random.choice(
    self.instruction_dict[str(info['instruction_id'])]
)
processed_data['text_input'] = instruction_text
```

因此，同一条索引记录在不同 epoch 或不同读取过程中，可以随机得到同一语义的不同英文表达。

以本地数据中的一条记录为例：

```text
instruction      = Turn-03-S-dis
instruction_id   = 15
instruction_args = [6]
```

ID 15 的一条真实字典模板为：

```text
After traveling [x] meters, maintain your course straight at the traffic signal.
```

正确填充参数后的文本应为：

```text
After traveling 6 meters, maintain your course straight at the traffic signal.
```

### 3.2 官方训练代码的参数替换问题

官方 `refer/LMDrive` 训练数据加载器虽然尝试替换模板参数，但没有保存 `str.replace()` 的返回值：

```python
if '[x]' in instruction_text:
    instruction_text.replace('[x]', str(info['instruction_args'][0]))
if 'left/right' in instruction_text:
    instruction_text.replace('left/right', str(info['instruction_args'][1]))
if '[y]' in instruction_text:
    instruction_text.replace('[y]', str(info['instruction_args'][2]))
```

Python 字符串不可变，`str.replace()` 会返回一个新字符串，不会原地修改原字符串。因此，官方训练加载器中的上述代码实际不会替换占位符。对前面的示例，官方训练代码实际送入模型的仍然是：

```text
After traveling [x] meters, maintain your course straight at the traffic signal.
```

该问题的影响范围为：

- 无参数的普通导航模板不受影响；
- notice instruction 当前均没有参数，因此不受影响；
- 包含 `[x]` 的距离型导航模板会保留 `[x]`；
- ID 64 可能保留 `[x]`、`[y]` 和 `left/right`；
- 这是官方训练数据加载器的实际行为，严格复现官方实现时需要意识到这一点。

官方在线评测 Planner 使用赋值或链式调用保存了替换结果，因此在线评测阶段的参数替换能够生效。例如：

```python
instruction_text = (
    random.choice(self.instruct_dict[str(self.prev_instruction_id)])
    .replace("[x]", str(int(abs(y_distance))))
    .replace("[y]", str(int(abs(x_distance))))
    .replace("left/right", navigation_direction)
)
```

当前迁移版数据集已经修复训练阶段的替换逻辑：

```python
for marker, index in replacements:
    if marker in text and index < len(arguments):
        text = text.replace(marker, str(arguments[index]))
```

因此需要区分两种行为：

| 实现 | 模板随机选择 | 参数替换 |
|---|---|---|
| 官方 `refer/LMDrive` 训练加载器 | 生效 | 因未保存返回值而失效 |
| 官方 Leaderboard Planner | 生效 | 生效 |
| 当前迁移版训练加载器 | 生效 | 已修复并生效 |

## 4. 本地数据统计

### 4.1 路线索引

`dataset_index.txt` 的统计结果为：

| 指标 | 数值 |
|---|---:|
| 路线记录数 | 15,001 |
| 唯一路线数 | 15,001 |
| 总帧数 | 5,445,586 |
| 单路线最少帧数 | 34 |
| 单路线最多帧数 | 13,170 |
| 单路线平均帧数 | 363.01 |
| Town 数量 | 8 |
| Weather ID 数量 | 21 |

Town 包括：1、2、3、4、5、6、7、10。Weather ID 范围为 0–20。

### 4.2 导航 instruction

`navigation_instruction_list.txt` 是 JSON Lines 格式，每一行表示一个 instruction clip。

| 指标 | 数值 |
|---|---:|
| 标注行数 | 168,590 |
| 覆盖路线数 | 14,977 |
| 不同 `route/start/end` clip 数 | 112,903 |
| JSON 解析错误 | 0 |
| 重复完整标注键 | 0 |

分类分布如下：

| 类别 | 数量 | 比例 |
|---|---:|---:|
| Turn | 60,111 | 35.66% |
| Follow | 80,452 | 47.72% |
| Others | 28,027 | 16.62% |
| 合计 | 168,590 | 100% |

`instruction_args` 长度分布：

| 参数数量 | 标注数 |
|---:|---:|
| 0 | 94,856 |
| 1 | 64,833 |
| 3 | 8,901 |

同一个物理 clip 可以具有多个 instruction 标注。例如，同一段直行 clip 可能同时被标注为沿道路继续、沿高速继续、保持当前方向及其距离版本。

### 4.3 Notice instruction

`notice_instruction_list.json` 是以路线为 key、notice 数组为 value 的 JSON 对象。

| 指标 | 数值 |
|---|---:|
| 包含 notice 的路线 | 13,031 |
| 原始 notice 数 | 464,192 |
| 去重后的 `route/frame/id` 数 | 393,549 |
| 所有 notice 参数数量 | 0 |
| 越界 `frame_id` | 0 |

各 ID 原始分布如下：

| ID | 类型 | 数量 | 比例 |
|---:|---|---:|---:|
| 50 | 行人 | 70,315 | 15.15% |
| 51 | 自行车 | 73,344 | 15.80% |
| 52 | 前车突然停车 | 0 | 0% |
| 53 | 左侧闯红灯车辆 | 71,072 | 15.31% |
| 54 | 前方闯红灯车辆 | 141,286 | 30.44% |
| 55 | 不平路面 | 70,315 | 15.15% |
| 56 | 隧道 | 30 | 0.01% |
| 57 | 红灯 | 17,784 | 3.83% |
| 58 | 绿灯 | 13,844 | 2.98% |
| 59 | 黄灯 | 6,202 | 1.34% |

## 5. Notice 重复数据

notice 文件中存在一个明确的数据特征：每个 ID 54 事件都完整出现了两次。

| 指标 | 数值 |
|---|---:|
| ID 54 原始数量 | 141,286 |
| ID 54 唯一数量 | 70,643 |
| 重复数量 | 70,643 |

其他 notice ID 没有相同形式的重复。全部 70,643 条重复都来自 ID 54。

当前数据集实现从时间窗口内的候选 notice 中直接随机采样，因此这些重复记录会使 ID 54 的抽样权重增加。与此同时，代码会以 75% 的概率丢弃 notice，只在约 25% 的有效窗口中插入 notice；这与论文中的 notice 使用率设置一致。

除非目标是严格复现官方训练数据分布，否则在后续数据清洗或重建索引时应明确决定是否保留该重复权重。

## 6. Misleading instruction

LMDrive 的 misleading instruction 不是一组独立 ID，也没有专门的文本类别。它通过在不合适的道路场景中选择已有 instruction 来生成，例如：

- 在单车道道路要求向左或向右变道；
- 在普通道路要求沿高速公路行驶；
- 在非环岛道路要求从环岛出口驶出；
- 在非路口位置要求立即左转或右转；
- 在禁止左转的 T 型路口要求左转；
- 在车辆转弯过程中要求变道。

当前 `navigation_instruction_list.txt` 中没有 `is_misleading` 字段。仅根据 `instruction_id` 无法判断某条标注是否 misleading，还需要结合道路拓扑、CARLA 地图或数据生成脚本判断。

## 7. 数据一致性

路线集合比较结果：

| 检查项 | 数量 |
|---|---:|
| Index 中没有导航标注的路线 | 26 |
| 导航标注中不在 Index 的路线 | 2 |
| Index 中没有 notice 的路线 | 1,977 |
| Notice 中不在 Index 的路线 | 7 |

对于同时存在于 Index 和标注文件中的路线，`route_frames` 均一致。少量不在 Index 中的记录主要是极短的 tiny route，或单帧异常路线。

导航与 notice 文件都通过 JSON 解析，未发现语法错误。所有 notice 的 `frame_id` 都满足：

```text
0 <= frame_id < route_frames
```

## 8. 训练资源位置与当前缺失项

### 8.1 `instruction_dict.json` 的权威源与可读副本

项目参考仓库中的原始单行 JSON 是本地权威源：

```text
refer/LMDrive/leaderboard/leaderboard/envs/instruction_dict.json
```

为了便于人工阅读，并允许数据集按照默认路径直接发现字典，项目同时保留一份标准缩进的等价副本：

```text
data/LMDrive/instruction_dict.json
```

两份文件已进行 JSON 对象级等价校验，内容均为 65 个 ID、每个 ID 8 条模板、共 520 条模板。可读副本只改变空白、换行和缩进，不改变 key、模板文本或数组顺序。

对该文件的直接解析结果为：

| 指标 | 数值 |
|---|---:|
| Instruction ID | 65 |
| 每个 ID 的模板数 | 8 |
| 模板总数 | 520 |
| 最小 ID | 0 |
| 最大 ID | 64 |

该文件负责把 `instruction_id` 转换为完整自然语言模板。它与官方仓库中的文件路径一致：

```text
leaderboard/leaderboard/envs/instruction_dict.json
```

官方链接：

<https://github.com/opendilab/LMDrive/blob/main/leaderboard/leaderboard/envs/instruction_dict.json>

当前数据集实现会优先读取显式传入的字典路径，否则尝试读取：

```text
<dataset_root>/instruction_dict.json
```

如果没有字典且未启用 notice，导航文本会回退成 `Turn-03-S` 之类的符号名称，而不是自然语言。如果启用了 notice，数据集初始化会直接报错。

由于 `data/LMDrive/instruction_dict.json` 已存在，当前数据集加载器在使用该目录作为 `DATASET_ROOT` 时可以自动发现字典。instruction fine-tuning 启动脚本仍要求显式传入 `INSTRUCTION_DICT_PATH`，可以直接指向可读副本：

```bash
DATASET_ROOT=/home/zhou/workspaces/lmdrive/data/LMDrive \
INSTRUCTION_DICT_PATH=/home/zhou/workspaces/lmdrive/data/LMDrive/instruction_dict.json \
bash instruction_finetuning/train_instruction.sh llava_v1_5_7b
```

从仓库根目录启动时也可以使用：

```bash
INSTRUCTION_DICT_PATH="$PWD/data/LMDrive/instruction_dict.json"
```

### 8.2 缺少传感器数据

当前只下载了索引和 instruction 标注，尚不能真正调用 `CarlaVoiceDataset.__getitem__`。模型训练还需要每条路线对应的：

- `rgb_full` 或四视角 RGB 图像；
- `lidar`；
- `lidar_odd`；
- `measurements_all.json`。

标注中的 `route_path` 是类似以下形式的相对路径：

```text
routes_town01_long_w12_08_13_03_12_20/
```

当前加载器会将它解释为：

```text
<dataset_root>/routes_town01_long_w12_08_13_03_12_20/
```

下载和解压传感器数据后，需要确认实际目录是否与该结构一致。如果数据实际位于 `data/Town01/...` 等子目录中，则需要整理软链接、修改 dataset root，或增加路径映射适配。

## 9. 参考资料

- LMDrive 数据卡：`data/LMDrive/README.md`
- 可读 instruction 字典：`data/LMDrive/instruction_dict.json`
- 本地 instruction 字典：`refer/LMDrive/leaderboard/leaderboard/envs/instruction_dict.json`
- LMDrive 官方仓库：<https://github.com/opendilab/LMDrive>
- 官方 instruction 字典：<https://github.com/opendilab/LMDrive/blob/main/leaderboard/leaderboard/envs/instruction_dict.json>
- LMDrive 论文：<https://arxiv.org/abs/2312.07488>
- 论文 Appendix D：<https://arxiv.org/html/2312.07488#A4>
- 本项目数据集实现：`lmdrive_lavis/datasets/datasets/carla_dataset_llm.py`
