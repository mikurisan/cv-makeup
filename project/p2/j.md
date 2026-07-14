# 什么是 LeRobot 训练格式?

LeRobot 训练格式, 准确说是 **`LeRobotDataset`**, 是 Hugging Face 开源的机器人学习框架 [LeRobot](https://github.com/huggingface/lerobot) 定义的一套**标准化机器人数据集格式**. 它专门为**模仿学习(Imitation Learning)和具身智能策略训练**设计, 目标是把各种机器人采集的异构数据, 统一成一种规整的、能直接喂给策略模型(如 ACT/Diffusion Policy/π0 等)训练的结构.

在你的项目里, ETL 流水线的**输出目标之一**就是它——把 ROS2 bag 里杂乱的多模态原始数据, 转换成 LeRobotDataset 这种"训练即用"的格式.

## 核心设计思想: 把数据拆成两层

LeRobot 格式最关键的设计, 是把不同性质的数据分开存储, 各用最合适的载体:

| 数据类型 | 存储方式 | 原因 |
|---------|------|------|
| 低维数值数据(关节状态、动作、夹爪等) | **Parquet** 列式存储 | 数值密集, 列存查询/加载高效 |
| 高维视觉数据(相机图像流) | **MP4 视频** (编码后) | 图像序列用视频编码, 存储比逐帧存图小一个量级 |
| 数据集元信息(schema / 统计量 / fps 等) | **JSON** 文件 | 描述数据集结构和归一化统计 |

这个"数值走 Parquet / 图像走 MP4"的拆分是它的精髓. 你在面试里能讲清楚这一点, 就说明你真正理解了这个格式而不是只会调 API.

## 目录结构长什么样

一个典型的 LeRobotDataset (v2.0+) 目录:

```
my_dataset/
├── meta/
│   ├── info.json          # 数据集核心元信息: fps、总帧数、总episode数、各特征的shape和dtype
│   ├── stats.json         # 每个特征的统计量(mean/std/min/max), 用于训练时归一化
│   ├── episodes.jsonl     # 每个episode的信息(长度、任务描述等)
│   └── tasks.jsonl        # 任务定义(自然语言指令)
├── data/
│   └── chunk-000/
│       ├── episode_000000.parquet   # 一条轨迹的低维数据(state/action/timestamp...)
│       ├── episode_000001.parquet
│       └── ...
└── videos/
    └── chunk-000/
        ├── observation.images.wrist/    # 手腕相机
        │   ├── episode_000000.mp4
        │   └── ...
        └── observation.images.top/      # 顶部相机
            └── episode_000000.mp4
```

## 几个必须理解的核心概念

**episode(轨迹/回合)**

一次完整的任务演示就是一个 episode. 比如"抓起杯子放到盘子里"这个完整动作序列 = 一条 episode. 训练数据就是由成百上千条 episode 组成的.

**frame(帧)**

episode 里的一个时间步. 每一帧包含那一时刻的观测(observation)和动作(action).

**feature(特征)与命名约定**

LeRobot 用带命名空间的 key 组织数据, 这套约定很重要:

- `observation.state` — 本体状态(关节角度等), 模型的观测输入
- `observation.images.<camera_name>` — 各路相机图像
- `action` — 动作/指令, 训练时的标签
- `timestamp` — 时间戳
- `episode_index` / `frame_index` — 定位用的索引

## 每一帧数据的样子(概念上)

```python
# 从 LeRobotDataset 取出的一帧, 大致是这样一个 dict
{
    "observation.state": tensor([j1, j2, .., j7, gripper]),   # 本体状态向量
    "observation.images.top": tensor(shape=[3, H, W]),          # 顶部相机图像
    "observation.images.wrist": tensor(shape=[3, H, W]),        # 手腕相机图像
    "action": tensor([a1, a2, ..., a7, grip_cmd]),              # 该时刻的动作(标签)
    "timestamp": 1.234,
    "episode_index": 0,
    "frame_index": 37,
}
```

策略模型学的就是: **给定 observation → 预测出 action** 这个映射.

## 为什么选 LeRobot 格式(技术选型的价值)

面试官问"为什么不用你自己定义的 HDF5, 非要转成 LeRobot", 你可以这样答:

- **生态兼容**: LeRobot 框架里的 SOTA 策略算法(ACT / Diffusion Policy / π0 / SmolVLA 等)都直接吃这个格式, 转成它就能零成本复用整套训练/评测 pipeline, 不用自己写 dataloader.
- **可分享/可复现**: 天然对接 Hugging Face Hub, 一行 `push_to_hub` 就能共享数据集, 团队协作和复现成本低.
- **存储高效**: 图像走视频编码, 相比 HDF5逐帧存图, 磁盘和加载带宽都省很多.
- **自带归一化统计**: `stats.json` 里的 mean/std 训练时直接用, 不用每次重算.

## LeRobot 格式 vs HDF5(你简历里两个都写了)

这是个很可能被追问的对比点——你简历里"输出 LeRobot/HDF5 训练格式"两个都提了, 一定要能说清区别:

| 维度 | HDF5 | LeRobotDataset |
|------|------|----------------|
| 本质 | 通用科学数据存储格式 | 专为机器人学习设计的数据集规范 |
| 图像存储 | 通常逐帧存 array, 体积大 | MP4 视频编码, 体积小 |
| 生态 | 通用, 需自己写 dataloader | 直接对接 LeRobot 训练框架 |
| 典型来源 | ALOHA/ACT 早期就用 HDF5 | HF 推的新一代标准 |
| 适用场景 | 单机 / 自定义训练脚本 | 标准化 / 共享 / 复用 SOTA 算法 |

你可以这样组织表述, 显得有工程判断:

> "我们 ETL 同时支持两种输出: HDF5 是为了兼容团队里早期基于 ALOHA/ACT 那套自定义训练脚本的存量流程; LeRobot 格式是为了对接新的 SOTA 策略训练和数据共享. 转换器做成可插拔的 writer, 根据下游训练需求选择输出格式."

一句话总结, 面试可以这么开场:

> "LeRobot 格式指的是 Hugging Face LeRobot 框架的 `LeRobotDataset`, 是面向模仿学习的标准化机器人数据集格式. 它的核心设计是把低维数值数据用 Parquet 列存 / 高维图像用 MP4 视频编码分开存, 再配JSON 元信息和归一化统计. 我ETL 流水线的一个输出目标就是它, 好处是能直接复用 LeRobot 里 ACT、Diffusion Policy 这些 SOTA 策略的训练 pipeline."

⚠️ 一个提醒: LeRobot 还在快速迭代, 格式从 v1 → v2 → v2.1 有过调整(比如 v2 才引入按 episode 分 chunk 和视频存储). 面试前建议你确认下项目里实际用的是哪个版本, 版本细节被追问时不至于露怯.

接下来想深挖哪块?

1. **ROS2 bag → LeRobotDataset 的转换代码**具体怎么写(这是你 ETL 的核心, 面试极可能让你讲实现)
2. **异频时间戳对齐**在转换成 LeRobot 帧时怎么处理(每一帧要求各模态对齐, 这里有真东西可讲)
3. 图像转 **MP4 编码**时的坑(帧率 / 编码器选择 / 无损 vs 有损对训练的影响)