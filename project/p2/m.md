# 什么是端到端完整性校验?

在你这个项目里, "端到端完整性校验"指的是: **保证数据从采集端(ROS2 bag 落盘) 经过整条 ETL 流水线, 一直到最终输出的训练数据集(LeRobot/HDF5), 全程数据没有丢失 / 没有损坏 / 没有错配**. "端到端"就是覆盖从**源头到终点的每一个环节**, 而不是只在某一步做检查.

换句话说: 你怎么向下游(训练模型的算法同学)证明——**"我交付给你的这份数据集, 和当初机器人采集时录下来的, 是完整一致/可信可用的"**?

## 为什么这件事在你的项目里特别重要

具身机器人训练数据有个特点: **数据错了但看起来是对的**, 危害极大. 如果一帧图像和对应的动作指令错位了(时间戳没对齐), 模型学到的就是错误的因果关系, 但流水线不会报错, 数据集也照样能导出. 这种"静默错误"(silent corruption)最可怕. 所以需要在多个环节主动校验.

## 端到端要校验哪些"完整性"

我把它拆成几个层次, 面试时这样分层讲会显得很有工程思维:

### 1. 数据量完整性 (有没有丢)

最基础的一层——**输入的消息数 == 输出的样本数(或符合预期的裁剪比例)**.

- 从 bag 的 `metadata.yaml` 读到每个 topic 的原始消息数
- ETL 处理后, 统计实际写入训练集的帧数
- 校验: 是否有非预期的丢帧? 裁剪后的帧数是否等于 `预期区间帧数`?

### 2. 数据内容完整性 (有没有坏 / 传输是否损坏)

用**校验和(checksum)** 保证文件内容在传输/存储过程中没有被破坏.

- 原始 bag 上传 MinIO 时计算 MD5/SHA256, 存到 MongoDB
- 后续读取时重新计算比对, 防止网络传输截断 / 磁盘坏块
- 最终 HDF5 文件导出后也算一个 hash 存档, 交付时可复核

### 3. 时序对齐完整性 (有没有错配)

这是多模态数据的**核心校验点**, 呼应你简历里的"异频时间戳对齐".

- 检查各模态时间戳是否单调递增(有没有乱序)
- 检查对齐后, 同一样本内各模态的时间戳偏差是否在容忍阈值内(比如 图像和关节状态偏差 < 10ms)
- 检查有没有"时间空洞"(某段时间某个 topic 突然断流)

### 4. Schema / 结构完整性 (格式对不对)

- 图像分辨率 / 通道数是否符合预期
- 关节维度(自由度)数量是否一致
- HDF5 里的 dataset key / shape / dtype 是否符合 LeRobot 规范

## 落地实现思路(体现工程能力)

一个务实的做法是: **在流水线每个关键节点埋"校验点", 生成一份可追溯的质检报告(manifest)**.

```python
import hashlib

def compute_file_checksum(file_path: str, chunk_size: int = 8 * 1024 * 1024) -> str:
    """
    分块计算大文件的 SHA256 校验和.
    ROS bag / HDF5 动辄几 GB, 不能一次读进内存, 必须流式分块.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        # 用 iter + 固定 chunk 循环读, 边读边更新 hash, 内存占用恒定
        for chunk in iter(lambda: f.read(chunk_size), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def validate_frame_count(expected: int, actual: int, topic: str) -> dict:
    """
    数据量完整性校验: 对比预期帧数与实际输出帧数.
    返回结构化结果, 汇总进质检报告, 而不是直接 raise ——
    让流水线能"标记问题样本并继续", 而非整批中断.
    """
    passed = expected == actual
    return {
        "check": "frame_count",
        "topic": topic,
        "expected": expected,
        "actual": actual,
        "loss_rate": round((expected - actual) / expected, 4) if expected else 0,
        "passed": passed,
    }


def validate_timestamp_alignment(
    ts_a: list[float], ts_b: list[float], threshold_ms: float = 10.0
) -> dict:
    """
    时序对齐完整性校验: 检查两个模态对齐后的时间戳偏差是否超阈值.
    ts_a / ts_b 是已经配对好的两路时间戳(单位: 秒).
    """
    max_diff_ms = max(abs(a - b) for a, b in zip(ts_a, ts_b)) * 1000
    return {
        "check": "timestamp_alignment",
        "max_diff_ms": round(max_diff_ms, 2),
        "threshold_ms": threshold_ms,
        "passed": max_diff_ms <= threshold_ms,
    }
```

最后把所有校验结果汇总成一份 **质检报告(manifest.json)**, 连同数据集一起入库/交付:

```json
{
  "dataset_id": "pick_place_20240601_001",
  "source_bag_sha256": "a1b2c3...",
  "output_hdf5_sha256": "d4e5f6...",
  "checks": [
    {"check": "frame_count", "topic": "/camera/image_raw", "passed": true},
    {"check": "timestamp_alignment", "max_diff_ms": 6.3, "passed": true}
  ],
  "overall_passed": true
}
```

## 一句话总结(面试话术)

> "端到端完整性校验就是保证数据从采集落盘, 经过 ETL 处理, 到最终导出训练集的全链路里, 数据不丢/不坏/不错配. 我们分了四层来做: 数据量层面对比输入输出帧数防丢帧; 内容层面用 SHA256 校验和防传输/存储损坏; 时序层面校验多模态对齐偏差是否在阈值内防错配; 结构层面校验 shape/dtype 符合训练格式规范. 每个环节的结果汇总成一份 manifest 质检报告随数据集交付, 保证数据可追溯、可信任."

这个点面试官很可能会**继续深挖**, 我预判几个追问, 你想先准备哪个:

1. "你说的丢帧, **具体是怎么发现和定位**的? 丢了怎么办, 能补吗?"
2. "校验和(checksum)你选 **MD5 还是 SHA256, 为什么**? 大文件计算慢怎么优化?"
3. "时间戳对齐偏差**阈值 10ms 是怎么定的**? 拍脑袋还是有依据?"
4. "如果一批数据校验**失败了, 你的流水线是中断还是继续**? 失败样本怎么处理?"
