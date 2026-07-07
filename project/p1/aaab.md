# Flink Slot 详解

## 1 Slot 是什么?

**Slot** = TaskManager 上的一块**资源隔离单元**(内存隔离 + 线程隔离), 是 Flink **资源调度的最小单位**.

> 一个 TaskManager 默认有 **1 个 CPU + 若干内存**, 通过配置可划分为 **多个 Slot**(如 `taskmanager.numberOfTaskSlots: 4` 表示划分为 4 份).

```
TaskManager (Machine 3, assume 4 cores / 4GB memory)
┌─────────────────────────────────────────┐
│ Slot 1   │ Slot 2   │ Slot 3   │ Slot 4 │
│ 1 core / │ 1 core / │ 1 core / │ 1 core │
│ 1 GB     │ 1 GB     │ 1 GB     │ 1 GB   │
└─────────────────────────────────────────┘
```

每个 Slot **可运行一个完整的 Pipeline**, 但不一定是一个算子 (关键点, 见下面 "Slot 共享").

## 2 Slot vs Task vs Subtask

这几个概念非常容易混淆, 务必区分:

| 概念 | 含义 | 举例 |
|------|------|------|
| **TaskManager (TM)** | 一台 JVM 进程 (一台机器或容器) | 一个 TM = 一个进程 |
| **Slot** | TM 内的一块隔离资源 (线程+内存) | 一个 TM 可有 4 个 Slot |
| **Task** | 一个算子(Operator)被执行起来的实例 | Source 算子, Map 算子 |
| **Subtask** | 算子的并行实例 (第 N 个并行度) | Source 并行度=2, 就有 2 个 Source Subtask |
| **Operator Chain** | 多个算子链在一起 | Source → Map → Filter 被链成一条 |

> 简单理解: **Slot 是"槽位", 用来装 Operator Chain; Subtask 是"实例", 真正运行在 Slot 里**。

## 3 Slot 共享机制 (核心特性)

**默认行为**: Flink 允许 **同一个 Slot 中运行多个算子组成的 Pipeline**, 只要这些算子来自**同一个作业**且上下游并行度相同.

```
作业并行度 = 2:
Source(并行度2) → Map(并行度2) → KeyBy → Sink(并行度2)

❌ 你以为的 Slot 占用(每个算子占一个 Slot):
Slot1: Source-1    Slot2: Source-2    ... 需要 6 个 Slot
Slot3: Map-1       Slot4: Map-2
Slot5: Sink-1      Slot6: Sink-2

✅ 实际 Slot 占用(Slot Sharing,一个 Slot 装一条 Pipeline):
Slot1: Source-1 → Map-1            Slot2: Source-2 → Map-2
需要 2 个 Slot, 节省 3 倍资源
```

**好处**:

- ✅ 资源利用率高 (同一个 Slot 内的算子可以共享内存, 数据)

- ✅ 减少 TM 间网络传输 (Source → Map 在同一个 TM 内部走内存,不开 RPC)

**坏处**:

- ❌ 一个 Slot 挂了,整 条 Pipeline 都要重启(故障爆炸半径大)

- ❌ 难以做细粒度的资源隔离 (关键算子不能单独多分配资源)

## 4 Slot 隔离级别

| 隔离项 | 隔离方式 | 说明 |
|--------|----------|------|
| **CPU** | **不隔离** (基于线程抢占) | Slot 仅是"逻辑分组", CPU 共享 TM 的所有核 |
| **内存** | **隔离** (Managed Memory) | 每个 Slot 分配独立的 Managed Memory (用于 RocksDB, Batch 排序等) |
| **网络 Buffer** | **共享池** | 所有 Slot 共享 TM 的网络 buffer pool |

> ⚠️ 重要面试点:**Slot 不做 CPU 隔离!** 所以"4 个 Slot = 4 核"是个误区, 真正约束是**内存**.

## 5 Slot 与并行度(Parallelism)的关系

| 关系 | 说明 |
|------|------|
| **并行度 = 需要的 Slot 数上限** | 一个作业最多同时占用的 Slot 数 = max(各算子并行度) |
| **Slot 数 ≥ 并行度 即可运行** | Slot 多于并行度 = 资源浪费, 运行无问题 |
| **Slot 数 < 并行度 → 启动失败** | 资源不足, 作业卡在 `SCHEDULED` 状态 |

**示例**:

- 作业最大并行度 = 4

- 集群 Slot 总数 = 6 ✅ 可启动 (占用 4 个, 剩 2 个空闲)

- 集群 Slot 总数 = 3 ❌ 启动失败, JobManager 报错

## 6 关键配置

```yaml
# flink-conf.yaml
taskmanager.numberOfTaskSlots: 4      # 每个 TM 的 Slot 数(默认 1)
parallelism.default: 1                  # 默认并行度
cluster.evenly-spread-out-slots: true  # Slot 是否均匀分布在 TM 上(防止热点)
```

## 7 面试回答模板

> "Slot 是 TaskManager 内的一块资源隔离单元,主要做**内存隔离**(CPU 不隔离),它是 Flink 调度的最小单位。一个 Slot 可以运行由多个算子链成的完整 Pipeline,这就是 Slot Sharing 机制,它的好处是提高资源利用率、减少 TM 间网络传输,但代价是故障半径变大。"


如果需要,我可以接着讲 **Slot 与 K8s 资源的关系**、**Slot Sharing 实战配置**,或 **Slot 不足时的诊断方法**。