# 什么是 ROS2 bag?

ROS2 bag 是 **ROS2 里用来记录和回放话题(topic)数据的工具和文件格式**. 简单说, 它就是 ROS2 世界里的"录像机"——把机器人运行时各个话题上流过的消息, 连同精确时间戳一起录下来, 之后可以原样回放, 用于调试/数据采集和离线分析.

在你这个具身机器人项目里, 遥操采集下来的多模态原始数据, 落盘时的载体基本就是 ROS2 bag 文件. 它是你 ETL 流水线的**输入源**.

## ros1 bag vs ros2 bag 的关键区别

这是面试官爱考的点, 因为很多人只用过 ROS1. 差异主要在存储机制:

| 维度 | ROS1 (`.bag`) | ROS2 (默认 `.db3` + `metadata.yaml`) |
|------|--------------|-----------|
| 存储格式 | 单一自定义二进制格式 | 默认 [SQLite3](./fa.md) 数据库, 可插拔(支持 mcap 等) |
| 文件结构 | 一个 `.bag` 文件 | 一个目录: 存储文件 + `metadata.yaml` 元信息 |
| 序列化 | ROS1 msg 序列化 | [CDR (DDS 标准序列化)](./fb.md) |
| 存储后端 | 固定 | **插件化**, 可选 sqlite3 / [mcap](./fc.md) |
| 命令 | `rosbag record/play` | `ros2 bag record/play/info` |

## ROS2 bag 的物理结构

录一个 bag 出来, 拿到的是一个**目录**, 不是单个文件:

```
my_recording/
├── metadata.yaml         # 元信息: 话题列表、消息类型、消息数量、时间范围、存储格式等
└── my_recording_0.db3     # 实际数据(SQLite), 大文件会自动分片 _0, _1, _2...
```

[`metadata.yaml`](./fd.md) 这个文件对你的项目很关键——它记录了 bag 里有哪些 topic / 每个 topic 的消息类型 / 总消息数 / 起止时间戳. 你做 MongoDB 元信息索引时, 很多字段其实可以直接从这里抽取.

## 存储后端: 为什么工业界越来越用 mcap 而不是默认的 sqlite3

这是能体现你"技术选型有思考"的加分点. 默认的 sqlite3 后端在**大规模/高频/大数据量**场景下有明显短板:

**sqlite3 的问题**

- 写入是事务型数据库, 高频高带宽写入(多路相机流)时容易成为瓶颈, 甚至丢帧
- 随机读设计, 对"顺序流式读取"这种回放/ETL 场景不友好
- 不适合流式追加写, 大文件性能下降

**mcap 的优势** (mcap 是 Foxglove 主推, 现已成为 ROS2 推荐格式)

- 面向流式读写设计, 顺序写入性能高, 适合高频大数据量录制
- 内置分块(chunk)+ 索引, 支持按时间/topic 快速 seek, 回放和裁剪时不用全量扫描
- 自带压缩(zstd/lz4), 存储成本更低
- 自描述格式, schema 内嵌, 跨语言跨版本读取更稳

结合你的项目, 你完全可以在简历/面试里这样表述技术决策:

> "采集端我们从默认 sqlite3 后端切换到 mcap. 原因是多路相机+高频关节状态的总写入带宽较大, sqlite3 在压测中出现写入瓶颈和偶发丢帧; mcap 的流式写入 + chunk 索引更适配我们后续 ETL 的顺序流式解析和按 topic 裁剪, 同时 zstd 压缩帮我们把原始数据存储成本降了约 XX%."

## 常用命令(面试可能让你手写)

```bash
# 录制指定话题 (-o 指定输出目录, -s 指定存储后端)
ros2 bag record -o my_recording -s mcap /camera/image_raw /joint_states

# 录制所有话题
ros2 bag record -a

# 查看 bag 元信息(topic 列表、消息数、时长)
ros2 bag info my_recording

# 回放
ros2 bag play my_recording

# 按倍速回放
ros2 bag play my_recording --rate 2.0
```

一句话总结, 面试里可以这么开场:

> "ROS2 bag 是 ROS2 的数据记录/回放工具. 和 ROS1 单文件不同, 它默认用 SQLite3 存储/CDR 序列化, 并且存储后端是插件化的. 我们项目在采集端选用了 mcap 后端而非默认 sqlite3, 因为它在高频大数据量场景下的流式写入性能和索引能力更适合我们的 ETL 处理."

需要我接着展开哪块? 比较值得深挖的方向:

1. **如何用 Python 流式读取 ROS2 bag**(`rosbag2_py` API), 这直接关系到你 ETL 流水线"流式解析"怎么实现
2. **CDR 序列化**是什么, 为什么 ROS2 换成了它
3. bag 录制时**丢帧/时间戳漂移**问题怎么排查和解决(面试深挖真实性时常问)