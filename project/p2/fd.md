# metadata.yaml 详解

`metadata.yaml` 是 ROS2 bag 目录里的**元信息清单**. 录制结束时自动生成, 用一句话概括: 它描述了"这个 bag 里录了什么/录了多少/录了多久/怎么存的", 但**不包含实际消息数据本身**(数据在 `.db3` / `.mcap` 里).

对你的项目来说, 它非常重要——你做 MongoDB 元信息索引时, 大量字段可以直接从这里解析出来, 不用去读庞大的数据文件.

## 一个真实的例子

假设我们录了一段遥操采集数据, 包含一路手腕相机 / 关节状态 / 遥操动作指令:

```yaml
rosbag2_bagfile_information:
  version: 6                # bag 格式版本
  storage_identifier: mcap            # 存储后端: mcap / sqlite3
  duration:                # 录制总时长
    nanoseconds: 45320000000          # 45.32 秒
  starting_time:                # 起始时间戳 (Unix epoch, 纳秒)
    nanoseconds_since_epoch: 1710835200123456789
  message_count: 6821                 # 所有 topic 的消息总数
  # 实际数据文件列表 (大文件会自动分片)
  relative_file_paths:
    - grasp_demo_001_0.mcap
    - grasp_demo_001_1.mcap

  # 分片文件的详细信息
  files:
    - path: grasp_demo_001_0.mcap
      starting_time:
        nanoseconds_since_epoch: 1710835200123456789
      duration:
        nanoseconds: 3000000
      message_count: 4500
    - path: grasp_demo_001_1.mcap
      starting_time:
        nanoseconds_since_epoch: 1710835230123456789
      duration:
        nanoseconds: 15320000000
      message_count: 2321
  # 每个 topic 的元信息 (核心部分)
  topics_with_message_count:
    - topic_metadata:
        name: /camera/wrist/image_raw          # topic 名
        type: sensor_msgs/msg/Image            # 消息类型
        serialization_format: cdr              # 序列化格式
        offered_qos_profiles: "..."            # QoS 配置(见下文)
      message_count: 1360                       # 该 topic 消息数 -> ~30Hz
  
    - topic_metadata:
        name: /joint_states
        type: sensor_msgs/msg/JointState
        serialization_format: cdr
        offered_qos_profiles: "..."
      message_count: 4530                       # ~100Hz, 高频
  
    - topic_metadata:
        name: /teleop/action
        type: geometry_msgs/msg/PoseStamped
        serialization_format: cdr
        offered_qos_profiles: "..."
      message_count: 931

  compression_format: zstd            # 压缩算法
  compression_mode: FILE              # 压缩模式: FILE / MESSAGE / 空
```

## 字段逐个拆解

**顶层信息**

| 字段 | 含义 | 对你项目的用途 |
|------|------|------------|
| `version` | bag 格式版本号 | 判断兼容性, 不同版本字段略有差异 |
| `storage_identifier` | 存储后端 | 校验是否是你期望的 mcap |
| `duration` | 录制总时长(纳秒) | 索引字段, 用于按时长过滤/统计 |
| `starting_time` | 起始时间戳 | 索引字段, 按采集日期检索 |
| `message_count` | 总消息数 | 快速判断 bag 是否为空/异常 |
| `compression_format/mode` | 压缩方式 | 决定读取时怎么解压 |

**`topics_with_message_count`** — 这是最有价值的部分

每个 topic 记录了名字/消息类型/序列化格式和消息数量. 有两个实战用途:

1. **推算采样频率**: `message_count / duration`. 比如 `/joint_states` 是 `4530 / 45.32 ≈ 100Hz`, `/camera/wrist/image_raw` 是 `1360 / 45.32 ≈ 30Hz`. 这正好体现你简历里"多传感器异频"的客观事实——你可以拿这个数据说明各模态频率确实不同.

2. **质检的第一道关卡**: 你简历写了"规则化自动质检". 最基础的一条规则就是校验 metadata——比如"这条 bag 必须包含 `/camera/wrist/image_raw`、`/joint_states`、`/teleop/action` 三个 topic, 且各自消息数不能为 0". 不用读数据文件, 光看 metadata 就能筛掉一批残缺采集.

## 结合你项目的实战代码

用 Python 直接解析 metadata 做质检和索引, 这段逻辑可以放进你的 ETL 入口:

```python
import yaml
from pathlib import Path

def parse_bag_metadata(bag_dir: str) -> dict:
    """
    解析 ROS2 bag 的 metadata.yaml, 提取索引与质检所需的元信息.
    这一步不触碰庞大的数据文件, 是ETL 流水线的轻量入口.
    """
    meta_path = Path(bag_dir) / "metadata.yaml"
    with open(meta_path, "r") as f:
        # metadata.yaml 顶层 key 固定为 rosbag2_bagfile_information
        info = yaml.safe_load(f)["rosbag2_bagfile_information"]

    duration_s = info["duration"]["nanoseconds"] / 1e9

    # 提取每个 topic 的信息, 并顺手推算采样频率
    topics = {}
    for item in info["topics_with_message_count"]:
        meta = item["topic_metadata"]
        count = item["message_count"]
        topics[meta["name"]] = {
            "type": meta["type"],
            "message_count": count,
            # 频率 = 消息数 / 时长, 用于验证异频特性 & 质检
            "approx_hz": round(count / duration_s, 2) if duration_s > 0 else 0,
        }

    # 组织成可直接写入 MongoDB 的文档结构
    return {
        "storage": info["storage_identifier"],
        "duration_s": round(duration_s, 2),
        "start_time_ns": info["starting_time"]["nanoseconds_since_epoch"],
        "total_messages": info["message_count"],
        "topics": topics,
    }


# ---- 规则化质检: 只看 metadata 就能筛掉残缺采集 ----
REQUIRED_TOPICS = {
    "/camera/wrist/image_raw",
    "/joint_states",
    "/teleop/action",
}

def validate_bag(meta: dict) -> list[str]:
    """返回质检发现的问题列表, 空列表表示通过."""
    issues = []

    # 规则1: 必需 topic 是否齐全
    missing = REQUIRED_TOPICS - meta["topics"].keys()
    if missing:
        issues.append(f"缺失必需 topic: {missing}")

    # 规则2: 任一必需 topic 消息数为 0 视为采集失败
    for name in REQUIRED_TOPICS & meta["topics"].keys():
        if meta["topics"][name]["message_count"] == 0:
            issues.append(f"topic {name} 消息数为 0")

    # 规则3: 相机帧率异常(明显低于预期 30Hz, 可能丢帧)
    cam = meta["topics"].get("/camera/wrist/image_raw")
    if cam and cam["approx_hz"] < 25:
        issues.append(f"相机帧率异常: {cam['approx_hz']}Hz, 疑似丢帧")

    return issues
```

## 一个必须知道的坑

`metadata.yaml` 里的 `message_count` 只告诉你"有多少条消息", **但不保证消息之间时间戳是均匀的**. 比如相机标称 30Hz、metadata 算出来也是 30Hz, 但很可能中间某一秒卡顿只来了 5 帧、另一秒补了 55 帧, 平均下来仍是 30Hz.

所以 metadata 质检只能作为**第一道粗筛**. 真正的"丢帧/时间戳漂移"检测, 必须进到数据层, 逐条读消息时间戳算相邻间隔(Δt)的分布. 这一点面试官如果深挖质检, 很可能会问——你能主动点出这个 metadata 层面的局限, 反而是加分项, 说明你真的理解数据.

小结, 面试里可以这么说:

> "metadata.yaml 是 bag 的元信息清单, 记录了 topic 列表 / 消息类型 / 消息数 / 时长 / 存储后端和压缩方式, 但不含实际数据. 我在 ETL 入口先解析它做轻量质检和 MongoDB 索引——比如校验必需 topic 齐全 / 用消息数除时长反推各传感器频率. 不过它只反映平均值, 检测不了时间戳抖动, 精确的丢帧检测还得进数据层逐条算 Δt."

要不要接着看 **进数据层逐条读消息、检测时间戳漂移** 这块? 这块和你简历的"异频时间戳对齐 + 端到端完整性校验"直接挂钩, 是面试深挖真实性的高频靶点.