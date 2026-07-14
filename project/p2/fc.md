# 什么是 mcap?

mcap (发音 "em-cap", 全称 **M**essage **C**apture) 是一种**开源的 / 面向流式记录的容器文件格式**, 专门用来存储带时间戳的/异构的/多路的消息流数据. 它由 Foxglove 团队主导开发, 现在已经成为 ROS2 官方推荐的 bag 存储后端之一.

你可以把它理解成: **专为机器人/自动驾驶这类"多传感器/高频/大数据量/需要时间对齐"场景设计的一种数据文件格式**. 一句话——它想解决的就是 ROS1 单一 `.bag` 格式和 ROS2 默认 sqlite3 后端在大规模场景下的痛点.

## 为什么会有 mcap? 它解决什么问题

在它出现之前, 机器人领域的数据存储比较割裂:

- ROS1 的 `.bag`: 只服务 ROS1 生态, 格式封闭, 跨语言/跨系统读取麻烦
- ROS2 默认 sqlite3: 事务型数据库, 不是为"顺序流式写入大数据"设计的, 高频高带宽场景下写入是瓶颈
- 自动驾驶公司常自己造轮子: 各家格式不通用

mcap 的设计目标就是做一个**通用的/高性能的/自描述的/可流式读写的**格式, 不绑定任何具体框架(虽然从 ROS 生态起家, 但它本身与 ROS 无关, 存protobuf/自定义二进制都行).

## mcap 的核心设计特性

这几点是它相比 sqlite3 的核心优势, 也是面试里你解释"为什么选 mcap"的技术依据:

**1. 面向流式追加写 (Append-only)**

数据是顺序追加写入的, 不像数据库有复杂的事务和随机写. 这让它在高频/大带宽录制时吞吐量很高, 不容易成为瓶颈或丢帧.

**2. Chunk 分块 + 索引**

数据被切成一个 chunk(块), 文件里还带有索引信息. 这带来两个好处:

- **快速 seek**: 回放或裁剪时, 想跳到某个时间点或只读某几个 topic, 靠索引直接定位, 不用从头扫全文件. 这对你 ETL 的"裁剪"操作是关键性能优势.
- **可分块压缩**: 每个 chunk 可以独立压缩.

**3. 内置压缩 (zstd / lz4)**

支持 chunk 级压缩. zstd 压缩率高, lz4 速度快. 对图像/点云这类大数据, 存储成本能显著下降, 而且是"读的时候按 chunk 解压", 不用整包解开.

**4. 自描述 (Self-describing)**

文件里内嵌了消息的 schema(数据结构定义). 意味着即使脱离原始的 ROS 环境、或者过了很久 msg 定义变了, 也能正确解析出数据. 这对**数据集长期归档**很重要——你项目里用 DVC 做数据集版本管理, 数据要长期可复现, 自描述这个特性正好契合.

**5. 框架/语言无关**

有 C++/Python/Go/Rust/Swift 等多语言读写库. 不绑定 ROS, 也不绑定某种序列化方式(CDR/protobuf/JSON 都能装).

## mcap 的文件结构(简化理解)

```
┌──────────────────────────────────────────────────┐
│ Header (magic number, format identifier)         │
├──────────────────────────────────────────────────┤
│ Schema records   (message structure defs,        │
│                   self-describing)               │
│ Channel records  (topic info, linked to schema)  │
├──────────────────────────────────────────────────┤
│ Chunk 1 [ Message, ... ] (compressible)          │
│ Chunk 2 [ Message, ... ] (compressible)          │
│ ...                                              │
├──────────────────────────────────────────────────┤
│ Index (chunk index, message index)               │
│ Statistics (total message count, time range, ...)│
│ Footer                                           │
└──────────────────────────────────────────────────┘
```

关键点: **索引和统计信息在文件尾部**, 读取时先读 footer 拿到索引, 就能快速随机访问任意 chunk. 这就是它 sek 快的原因.

## 在你项目里怎么落地(可写进面试话术)

结合你的 "ROS bag 标准化 ETL 流水线", mcap 至少在三个环节能体现你的技术判断:

- **采集端**: 用 mcap 后端录制, 高频多路数据不丢帧, 顺便 zstd 压缩降存储成本
- **ETL 流式解析**: 靠 mcap 的 chunk 索引, 按 topic /时间窗口顺序流式读取, 内存占用可控, 支持"裁剪"时快速定位区间
- **归档与复现**: 自描述特性保证数据集长期可读, 配合 DVC 版本管理, 保障数据可复现

## Python 读取示例(ETL 流式解析的核心)

```python
# mcap 官方提供 mcap 与 mcap-ros2-support 两个库
# mcap-ros2-support 能自动帮你把 CDR 二进制反序列化成 ROS2 消息对象
from mcap_ros2.reader import read_ros2_messages

# 流式迭代读取: 每次只吐一条消息, 不会把整个文件加载进内存
# 这正是处理大 bag(几十 GB)时"流式解析"的关键 — 内存占用恒定
for msg in read_ros2_messages("my_recording.mcap"):
    topic = msg.channel.topic          # topic 名, 如 /camera/image_raw
    timestamp = msg.log_time           # 记录时的时间戳(纳秒), 用于跨模态对齐
    ros_msg = msg.ros_msg              # 反序列化后的 ROS2 消息对象

    # 按 topic 做不同处理 (这里就是 ETL 里 transform 的分发逻辑)
    if topic == "/camera/image_raw":
        handle_image(ros_msg, timestamp)
    elif topic == "/joint_states":
        handle_joint_state(ros_msg, timestamp)


# 如果只想读某几个 topic 的某个时间段, 用底层 mcap 库 + 索引, 避免全量扫描
from mcap.reader import make_reader

with open("my_recording.mcap", "rb") as f:
    reader = make_reader(f)
    # topics 过滤 + 时间范围过滤, 底层靠索引直接定位, 不扫全文件
    for schema, channel, message in reader.iter_messages(
        topics=["/joint_states"],
        start_time=1_700_000_000_000_000,  # 纳秒时间戳
        end_time=1_700_000_010_000_000_000,
    ):
        # channel.topic / message.log_time / message.data(原始 CDR 字节)
        process(channel.topic, message.log_time, message.data)
```

一句话总结, 面试可以这么答:

> "mcap 是 Foxglove 主导的开源流式记录格式, 现在是 ROS2 推荐的 bag 后端. 它面向 append-only 的流式写入设计, 带 chunk 分块和索引, 支持 zstd 压缩和自描述 schema. 相比默认的 sqlite3, 它在高频大数据量场景下写入吞吐更高、不易丢帧, 靠索引能快速按 topic 和时间裁剪, 还便于数据集长期归档复现——这几点正好命中我们 ETL 流水线和 DVC 版本管理的需求."

要不要我接着帮你把 **"为什么选 mcap 而不是 sqlite3"** 这个技术选型, 打磨成一段能经得起面试官反复追问的完整问答? 面试官通常会顺着问:

1. "你们数据量多大, 为什么 sqlite3 会成为瓶颈, 有没有压测数据?"
2. "mcap 的chunk 大小怎么设置的, 压缩用 zstd 还是 lz4, 怎么权衡?"
3. "mcap 和 HDF5 都能存, 为什么采集用 mcap、训练格式用 HDF5?"

这几个问题如果没准备, 很容易在深挖时露怯. 你对项目里这部分的真实情况了解多少? 我可以据此帮你补齐细节.