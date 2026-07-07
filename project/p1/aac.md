# Flink 如何把 Job 拆成并行实例?

## 1 先理清核心概念 (自顶向下)

Flink 从"你写的代码"到"集群上真正跑的线程", 经历了**四层图结构的转换**:

```
你的代码 (DataStream API)
      ↓  ① 生成
StreamGraph        (逻辑视图, 最原始的算子 DAG)
      ↓  ② 优化: 算子链合并
JobGraph           (提交给 JobManager 的图)
      ↓  ③ 按并行度展开
ExecutionGraph     (物理执行图, 真正的并行实例在这里产生)
      ↓  ④ 调度到 Slot
Physical Execution (TaskManager 上运行的一个个 Task 线程)
```

**"拆成并行实例"这个动作, 发生在第 ③ 步: JobGraph → ExecutionGraph.**

## 2 拆分的核心依据: 并行度 (Parallelism)

### 1. 什么是并行度?

并行度 = **一个算子被拆成几个并行实例 (subtask) 同时运行**.

```java
// 一段简单的 Flink 代码
DataStream<String> source = env.addSource(kafkaSource).setParallelism(3);
DataStream<Event> parsed = source.map(new ParseFunction()).setParallelism(3);
DataStream<Result> result = parsed.keyBy(e -> e.userId)
                                  .window(...)
                                  .aggregate(...).setParallelism(2);
result.addSink(starRocksSink).setParallelism(2);
```

上面这段代码, 展开成并行实例后是这样:

```
   Source (parallelism=3)          Map (parallelism=3)
   ┌─────────┐                    ┌─────────┐
   │Source-0 │───────────────────►│  Map-0  │
   ├─────────┤                    ├─────────┤
   │Source-1 │───────────────────►│  Map-1  │
   ├─────────┤                    ├─────────┤
   │Source-2 │───────────────────►│  Map-2  │
   └─────────┘                    └─────────┘
                                        │
                              keyBy (数据重分区 shuffle)
                                        ↓
                         Aggregate (parallelism=2)    Sink (parallelism=2)
                         ┌───────────┐               ┌─────────┐
                         │Aggregate-0│──────────────►│ Sink-0  │
                         ├───────────┤               ├─────────┤
                         │Aggregate-1│──────────────►│ Sink-1  │
                         └───────────┘               └─────────┘
```

**每一个方块 (subtask), 就是一个"并行实例", 它是调度和执行的最小单位.**

### 2. 并行度从哪来? (优先级从高到低)

| 级别 | 设置方式 | 优先级 | 说明 |
|------|---------|--------|------|
| **算子级** | `.setParallelism(3)` | 最高 | 单个算子单独设置 |
| **执行环境级** | `env.setParallelism(4)` | 中 | 整个 Job 的默认值 |
| **提交级** | `flink run -p 8` | 中低 | 提交命令指定 |
| **配置文件级** | `parallelism.default: 2` | 最低 | 集群兜底默认值 |

> 面试要点: 记住这个**就近覆盖原则**——算子级 > 环境级 > 提交级 > 配置级.

## 3 拆分的两个关键机制

### 机制一: 算子链 (Operator Chain) —— 拆之前先"合"

在展开并行实例之前, Flink 会先做一个反直觉的优化: **把多个算子合并成一个 Task**, 目的是减少线程切换和网络序列化开销.

**满足以下条件的相邻算子会被 chain 在一起**:

1. 并行度相同

2. 数据传输是 **one-to-one (Forward)** 关系 (没有 keyBy/rebalance 等 shuffle)

3. 在同一个 SlotSharingGroup

```
未 chain 前 (StreamGraph 逻辑视图):
   Source → Map → Filter    (3 个算子)

chain 后 (JobGraph):
   [Source → Map → Filter]  (合并成 1 个 Task, 在一个线程里跑)
```

**为什么重要?** 上面例子里 Source、Map 并行度都是 3 且是 Forward 关系, 所以会 chain:

```
真正运行时其实是:
   [Source→Map]-0   (1个线程)
   [Source→Map]-1   (1个线程)
   [Source→Map]-2   (1个线程)
```

数据在 Source 和 Map 之间**不走网络, 直接方法调用**, 性能大幅提升.

### 机制二: 数据分发策略 —— 决定实例之间怎么连线

当上下游并行度不同, 或者遇到 `keyBy`, 就必须做**数据重分区 (Redistribution)**:

| 分发策略 | 触发场景 | 数据流向 |
|---------|---------|---------|
| **Forward** | 并行度相同且无 shuffle | 一对一, 可 chain |
| **Hash** | `keyBy()` | 按 key 的 hash 分到下游某个实例 |
| **Rebalance** | 并行度不同(默认) | 轮询均匀分发 |
| **Rescale** | 局部轮询 | 就近分发, 减少跨网络 |
| **Broadcast** | 广播 | 复制到下游所有实例 |
| **Global** | 全局 | 全发到下游第 0 个实例 |

上面例子里 `keyBy(userId)` 就是 **Hash 分发**: 相同 userId 的数据一定进同一个 Aggregate 实例, 这是保证聚合正确性的关键.

```
keyBy 的本质: key.hashCode() → murmurHash → 对 maxParallelism 取模 → 映射到下游 subtask

举例:
  userId="A" → hash → Aggregate-0
  userId="B" → hash → Aggregate-1
  userId="A" → hash → Aggregate-0  (相同 key 必到同一实例)
```

## 4 拆分后如何调度到机器上?

### Slot 共享 (Slot Sharing)

拆出来的 subtask 需要放进 TaskManager 的 **Slot** 里执行. Flink 默认开启 **Slot 共享**: **同一个 Job 中不同算子的 subtask 可以共享一个 Slot**.

```
一个 TaskManager 有 3 个 Slot, 上面的 Job 调度后:

   Slot-0: [Source→Map]-0  +  Aggregate-0  +  Sink-0
   Slot-1: [Source→Map]-1  +  Aggregate-1  +  Sink-1
   Slot-2: [Source→Map]-2
```

**好处**:

1. **所需 Slot 数 = 最大并行度** (这里是 3), 而不是所有算子并行度之和

2. **资源利用均衡**: 重算子(CPU密集)和轻算子(IO密集)混在一个 Slot, 削峰填谷

3. **减少数据跨网络传输**

> 面试高频问: **"一个 Job 需要多少 Slot?"** 

> 答: 默认 Slot 共享下, **等于 Job 中算子的最大并行度**.

## 5 完整流程串联 (一句话版本)

你写的算子先生成 StreamGraph, Flink 把符合条件的相邻算子 chain 成 JobGraph 里的一个 Task; 提交后 JobManager 根据每个算子的并行度, 把每个 Task 展开成 N 个并行 subtask 实例, 生成 ExecutionGraph; 最后按 Slot 共享规则, 把这些 subtask 分配到各 TaskManager 的 Slot 里, 变成一个个真正运行的线程. 实例之间通过 Forward/Hash/Rebalance 等策略传递数据.

## 6 可能的深挖追问

| 追问 | 回答方向 |
|------|---------|
| 并行度能超过 Slot 总数吗? | 不能, 会导致 Job 无法调度, 资源不足报错 |
| keyBy 之后数据倾斜怎么办? | 加盐打散 + 两阶段聚合 |
| Operator Chain 能手动断开吗? | 能, `.disableChaining()` 或 `.startNewChain()` |
| 为什么并行度建议设成 2 的幂次? | 与 maxParallelism (默认128) 取模更均匀, 便于 rescale |
| Source 并行度能大于 Kafka 分区数吗? | 能设但没意义, 多出的实例会空跑 |

需要我画一张**从代码到 ExecutionGraph 的完整转换图**, 或者深入讲**数据倾斜的加盐+两阶段聚合实战**吗?