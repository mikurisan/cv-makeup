# Checkpoint 到底保存了什么?

我先用一句话回答核心, 再用结构化图表解释.

## 1 一句话回答

> **Checkpoint 保存的是"算子此刻的"状态 (State)", 而不是数据本身.**

已处理的数据/未来的数据**都不存**——只存**算子的记忆**.

## 2 什么是"算子的状态"?

先理解这个概念, 这才是关键.

### 例子: 累加器算子

```python
class Counter:
    def __init__(self):
        self.count = 0  # ← 这就是 State

    def process(self, data):
        self.count += 1
        print(f"已处理 {self.count} 条数据")
```

| 对象 | 内容 | 算不算 State? |
|------|------|--------------|
| `count = 100` | "我现在处理了 100 条" | ✅ **是 State** |
| 输入的 msg_1 ~ msg_100 | 原始数据 | ❌ 不是 State |
| 未来会来的 msg_101 | 还没来的数据 | ❌ 不是 State |
| 处理函数本身 | 代码逻辑 | ❌ 不是 State |

## 3 State 的常见类型

| 类型 | 示例 | 存储什么 |
|------|------|----------|
| **ValueState** | `count = 100` | 单个变量 |
| **ListState** | `[user_a, user_b, user_c]` | 一个列表 |
| **MapState** | `{user_001: 余额, user_002: 余额}` | KV 映射 |
| **Window 状态** | `[20.5, 21.0, 19.8, 20.2]` (5 分钟窗口内的数据) | 窗口内的累加值 |

## 4 Checkpoint 的本质

```
┌───────────────────────────────────────────────────────────┐
│           Output of a Single Checkpoint                   │
├───────────────────────────────────────────────────────────┤
│                                                           │
│   1. State Snapshot of Each Operator                      │
│      ├── Counter operator:    count = 100                 │
│      ├── Window operator:     [20.5, 21.0, 19.8]          │
│      └── Dedup operator:      { user_001, user_002 }      │
│                                                           │
│   2. Offset of Source Operator (Consumption Progress)     │
│      ├── Kafka Offset: partition 0 = 100, partition 1 = 50│
│      └── MySQL Binlog:  position = 12345                  │
│                                                           │
│   3. Metadata                                             │
│      ├── Job ID                                           │
│      ├── Checkpoint ID                                    │
│      └── Parallel Instance IDs of Each Operator           │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

**核心 3 点**:

1. **算子的 State** ← 最重要

2. **Source 进度 (Offset)** ← 用于恢复后继续消费

3. **元数据** ← 用于 JobManager 知道哪个 Checkpoint 对应哪个作业

## 五、对照原问题回答

### ❓ 已经处理了的数据?

**不存!** 它们已经**流过去了**, 任务本来就是无状态的(无状态时只需要记住进度).

```
msg_1, msg_2, msg_3, msg_4, msg_5  ← 镜头流过 ≠ 入库存档
                                   ← 只有"算子记下的东西"才存档
```

### ❓ 还没有处理的数据?

**不存!** 它们还在 Kafka 队列里(或数据库里), 源头就有, Flink**不重复存**.

```
[Kafka 里] msg_101, msg_102, msg_103 ...  ← 源头负责持久化, Flink 负责"消费到哪"
```

> 这是一个**关键设计**: 数据不存多份, 只存"处理到了哪里".

### ❓ 正在到来的数据?

**不存!** 因为 Checkpoint 是一个**瞬间切片**——在 Barrier 到达的那一刻, 只**冻结状态那一瞬**, 切片之外的**不归这次 Checkpoint 管**.

```
处理中:
  ✓ msg_1 (已处理)        ← 这个时刻前结束
  ✓ msg_2
  [📸 B1 Barrier 到达, 执行快照!]
  ? msg_3 (正在处理, 可能是部分处理)

只拍 [msg_1, msg_2 之后] 的那一刻, msg_3 还没完整处理 → 归下次 Checkpoint
```

## 6 故障恢复时怎么用 Checkpoint?

```
故障前:
   Kafka: msg_1 ~ msg_5000 已消费
   Counter: count = 5000
   Checkpoint 时: [count=2500, Kafka Offset=2500]

故障后从 Checkpoint 恢复:
   ↓ 把 count 还原为 2500
   ↓ 把 Kafka Offset 还原为 2500
   ↓ 重新从 msg_2501 开始消费
   ↓ 继续累加到 5000+

✅ 没丢数据  ✅ 没重复处理  ✅ 状态恢复
```

## 7 深挖: Source Offset 为什么这么重要?

**Source Offset 是 "状态恢复的锚点"**, 没有它, Checkpoint 是残缺的.

```
┌──────────────────────────────────────────────┐
│         A Complete Checkpoint                │
│                                              │
│   ┌──────────────────────────────────────┐   │
│   │ JobManager Side                      │   │
│   │  - Checkpoint ID: 100                │   │
│   │  - Positions of each Source instance:│   │
│   │    Source_1: Kafka part-0 = 5000     │   │
│   │    Source_2: Kafka part-1 = 3000     │   │
│   └──────────────────────────────────────┘   │
│                    ↓ Associated with         │
│   ┌──────────────────────────────────────┐   │
│   │ State of Each Operator               │   │
│   │  - Counter: count = 5000             │   │
│   │  - Window: sum = 10000, count = 500  │   │
│   └──────────────────────────────────────┘   │
│                                              │
└──────────────────────────────────────────────┘
```

恢复时:

1. 先告诉 Source "回到 part-0 offset 5000, part-1 offset 3000"

2. 再恢复各算子状态

3. 三者**对齐**, 才能算"同一时间点"

## 8 面试标准回答

> "Checkpoint 保存的不是数据本身, 而是**算子的状态快照**和**Source 的消费进度 (Offset)**. 具体来说包括三部分: 所有算子的 State(运行时变量)/Source 的 Offset(下次从哪开始消费), 以及作业的元数据. 数据本身存放在外部系统如 Kafka, Flink 不重复存储. 这样设计的好处是开销低/恢复快——只需要把状态恢复到某个时间点, 从对应的 Offset 继续消费就能保证不丢不重. 整个过程靠 Barrier 机制确保所有算子在一致的快照点被切断."

## 9 面试追问准备

| 追问 | 关键回答 |
|------|----------|
| State 大小有限制吗? | 受 TaskManager 内存 / 磁盘大小限制;RocksDB 写到本地磁盘 |
| Checkpoint 耗时太长怎么办? | 调大超时/开启 Unaligned/减少 StateSize |
| 两次 Checkpoint 之间挂了会丢数据吗? | 取决于语义:At-Least-Once 可能丢;Exactly-Once 不丢(需 Source 配合) |
| Source Offset 怎么存? | Kafka 的 Offset 由 Kafka 自带持久化;自 定义 Source 需自己实现 |

接下来想聊 **Barrier 对齐如何保证 Exactly-Once**,还是 **RocksDB 增量 Checkpoint 的原理**?