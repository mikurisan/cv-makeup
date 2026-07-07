# 详解 TaskManager 是什么

## 1 核心定义

**TaskManager (简称 TM)** 是 Flink 集群中真正**干活的工作进程 (Worker)**, 负责执行具体的计算任务/管理内存/维护状态/进行数据交换.

> 一句话: **JobManager 是"包工头"负责指挥, TaskManager 是"工人"负责实际搬砖.**

## 2 TaskManager 在架构中的位置

```
┌────────────────────────────────────────────────┐
│                Flink Cluster                   │
│                                                │
│   ┌─────────────────┐                          │
│   │   JobManager    │  Scheduling / Coord /    │
│   │   (Master)      │  Fault Tolerance         │
│   └────────┬────────┘                          │
│            │ Task Distribution / Heartbeat     │
│      ┌─────┴──────┬──────────────┐             │
│      ▼            ▼              ▼             │
│ ┌─────────┐ ┌─────────┐   ┌─────────┐          │
│ │   TM-1  │ │   TM-2  │   │   TM-3  │  Actual  │
│ │(Worker) │ │(Worker) │   │(Worker) │  Exec    │
│ └─────────┘ └─────────┘   └─────────┘          │
└────────────────────────────────────────────────┘
```

- **一个 Flink 集群 = 1 个 JobManager + N 个 TaskManager**

- TaskManager 越多, 集群算力越强 (横向扩展的基础) 

## 3 TaskManager 的内部结构

一个 TaskManager 本质是一个 **JVM 进程**, 内部关键组成:

```
┌──────────────────────────────────────────┐
│        TaskManager (JVM Process)         │
│                                          │
│  ┌────────┐ ┌────────┐ ┌────────┐        │
│  │ Slot 1 │ │ Slot 2 │ │ Slot 3 │  Slot 4│  ← Resource Slots
│  └────────┘ └────────┘ └────────┘        │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │   Memory (On-heap + Off-heap)      │  │
│  │   - Network Buffer (Data Exchange) │  │
│  │   - Managed Memory (RocksDB/Sort)  │  │
│  │   - Task Heap (User Code)          │  │
│  └────────────────────────────────────┘  │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │   Network (Netty, inter-TM comms)  │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

### 三个核心概念

#### 1. Slot (任务槽)

- TaskManager 划分资源的**最小单位**

- **1 个 Slot = 一份隔离的内存资源** (注意: Slot 只隔离内存,, 不隔离 CPU)

- 一个 TM 有几个 Slot, 就能同时跑几个并行任务

```
TaskManager (taskmanager.numberOfTaskSlots: 4)
   → 意味着这个 TM 能同时执行 4 个并行子任务
```

#### 2. Task 与 SubTask

- **Task**: 一个算子 (如 Map/KeyBy)

- **SubTask**: 算子的一个并行实例, 是 TaskManager 实际执行的单元

```
Map 算子 (并行度 3) 
   → 拆成 3 个 SubTask 
   → 分散到不同 TM 的 Slot 上执行
```

#### 3. Slot 共享 (Slot Sharing) 

Flink 默认允许**同一个 Job 的不同算子共享一个 Slot**:

```
Slot 1 可以同时放:  Source-1 → Map-1 → Sink-1   (一条完整的链) 
```

**好处**:

- 一个 Slot 跑完整的处理链, 减少数据跨网络传输

- 资源利用更均衡 (避免有的 Slot 忙死, 有的闲死) 

## 4 TaskManager 的核心职责

| 职责 | 说明 |
|------|------|
| **执行计算** | 运行 SubTask, 即你写的算子逻辑 |
| **内存管理** | 管理 Network Buffer、Managed Memory 等 |
| **状态维护** | 持有本节点负责的 State (存内存或 RocksDB) |
| **数据交换** | 通过 Netty 与其他 TM 进行数据 Shuffle |
| **Checkpoint** | 收到 Barrier 后, 把本地 State 持久化到 S3/HDFS |
| **心跳上报** | 定期向 JobManager 汇报存活状态和指标 |

## 5 TaskManager vs JobManager (对比记忆)

| 维度 | JobManager | TaskManager |
|------|-----------|-------------|
| 角色 | Master (大脑)  | Worker (工人)  |
| 数量 | 1 个 (HA 下多个备用)  | N 个 |
| 职责 | 调度、协调、容错 | 执行、计算、存状态 |
| 是否处理数据 | ❌ 不处理业务数据 | ✅ 真正处理数据 |
| 挂了的影响 | 整个 Job 停摆 (除非 HA)  | 该节点任务被重新调度 |

## 6 面试高频追问

| 追问 | 建议回答方向 |
|------|------------|
| **Slot 和并行度什么关系?** | 并行度 ≤ 总 Slot 数, 否则任务起不来 |
| **Slot 隔离 CPU 吗?** | ⚠️ 关键陷阱: 只隔离内存, 不隔离 CPU |
| **为什么要 Slot 共享?** | 提升资源利用率, 减少数据跨网络传输 |
| **一个 TM 挂了会怎样?** | JobManager 检测到心跳超时, 触发 failover, 从 Checkpoint 恢复 |
| **TM 内存怎么划分?** | 提 Framework/Task Heap、Managed Memory、Network Buffer |
| **给 TM 配几个 Slot 合理?** | 一般等于 CPU 核数, 结合负载调整 |

## 8 一个容易踩的坑 (加分项) 

> **面试官爱问: "TaskManager 的 Slot 数量是不是越多越好?"**

**标准答案**:
> "不是. Slot 只隔离内存不隔离 CPU, 如果 Slot 数远超 CPU 核数, 多个 SubTask 会争抢 CPU, 反而导致上下文切换开销大、吞吐下降. 我们一般把 Slot 数设成接近 CPU 核数, 比如 4 核机器配 4 个 Slot. 同时要结合 Managed Memory——Slot 越多, 每个 Slot 分到的 RocksDB 内存越少, 状态大的场景要特别注意."

需要我继续讲 **JobManager** 的内部机制, 还是深入 **TaskManager 的内存模型** (这块面试常问, 尤其是 OOM 排查)?