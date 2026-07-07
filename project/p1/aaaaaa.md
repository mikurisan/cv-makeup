# 算子链 (Operator Chain) 详解

## 1 核心定义

**算子链** 是 Flink 的一个**性能优化机制**: 把多个**可以串在一起**的算子**合并成同一个 Task**, 让数据在**同一个线程里**通过**方法调用**(而不是网络传输)的方式流转.

**目的: 减少序列化、反序列化、网络传输开销。**

## 2 为什么需要算子链?

### 没有算子链的情况 (默认状态)

每个算子都是一个独立的 Task, Task 之间要走**网络**:

```
Source → [序列化] → 网络 → [反序列化] → Map → [序列化] → 网络 → [反序列化] → Filter
```

开销大, 延迟高.

### 有算子链的情况 (优化后)

多个算子合并成一个 Task, **数据在内存中直接传**:

```
[Source → Map → Filter]  ← 一个 Task, 一条线程, 方法调用传递数据
```

开销小, 延迟低.

## 3 合并条件 (可串条件)

算子能否串成一个链, Flink 有 **6 条规则**, 核心 3 条:

| 条件 | 说明 |
|------|------|
| ✅ **并行度相同** | 两个算子的并行度必须一致 |
| ✅ **one-to-one 关系** | `forward` 连接, 数据按分区一对一发送(如 `map→filter`) |
| ✅ **同一 Slot 共享组** | 默认同组, 可配置 `disableChaining()` 排除 |

**不满足任一条件就不能合并**, 例如:

- `keyBy` / `rebalance` / `broadcast` 都是 **redistributing**, 不能合并

- 并行度不一致,  不能合并

## 4 举个直观的例子

### 用户代码

```java
env.socketTextStream(...)
   .map(line -> line.split(","))     // 算子 A (并行度 2)
   .filter(arr -> arr.length == 3)   // 算子 B (并行度 2)
   .keyBy(arr -> arr[0])             // 算子 C (并行度 2)
   .sum(1)                           // 算子 D (并行度 2)
   .print();                         // 算子 E (并行度 2)
```

### 没合并时(5 个 Task)

```
Task1: Source
Task2: Map
Task3: Filter
Task4: KeyBy + Sum
Task5: Print
```

### 合并后(实际只有 3 个 Task)
```
Task1: [Source → Map → Filter]      ← 串成一条链(都是 one-to-one)
Task2: [KeyBy → Sum]                ← keyBy 是 hash,前后断开
Task3: [Print]
```

**注意:即便合并后, 数据流向依然是 `Task1 → Task2 → Task3`, 只是 Task1 内部 3 个算子在同一条线程.**

## 5 图示对比

### 合并前 (4 个 Task, 3 次网络传输)

```
[Source] ──net──► [Map] ──net──► [Filter] ──net──► [KeyBy]
  Task1              Task2           Task3            Task4
```

### 合并后 (2 个 Task, 1 次网络传输)

```
┌──────────────────┐               ┌──────────────────┐
│  Source          │               │   KeyBy          │
│  → Map           │ ─────net────► │   → ...          │
│  → Filter        │               │                  │
└──────────────────┘               └──────────────────┘
       Task1                            Task2
   同一线程方法调用                       同一线程方法调用
```

## 6 如何控制算子链?

Flink 提供 4 个 API 控制算子链, 常用于**性能调优或调试**:

| API | 作用 |
|-----|------|
| `operator.chain.start` 注释 / `startNewChain()` | 从这个算子开始**新起一条链** |
| `disableChaining()` | 这个算子**禁用链合并**, 单独一个 Task |
| `setChainingStrategy(ChainingStrategy.HEAD/NEVER/ALWAYS)` | 精细控制 |
| `env.disableOperatorChaining()` | **全局禁用**算子链 |

### 示例

```java
source.map(...).filter(...).startNewChain().keyBy(...);
```

## 7 面试高频追问

| 问题 | 回答要点 |
|------|---------|
| 算子链合并有什么好处? | 减少**序列化/反序列化**和**网络传输**开销, 提升吞吐, 降低延迟 |
| 什么情况下算子不能合并? | 并行度不一致 / 非 one-to-one(keyBy, rebalance) / 显式禁用 |
| 合并后 Slot 数会变少吗? | **会**!因为每个链是一个 Task, Task 数减少, Slot 占用减少 |
| 算子链和 Slot 共享是一回事吗? | **不是**. 算子链是**同一 Task** 内部, Slot 共享是**同一 Slot 跑多个 Task** |

## 8 面试回答模板

> "算子链是 Flink 把多个满足 one-to-one、并行度相同等条件的算子合并到同一个 Task 里执行的优化机制,目的是减少序列化反序列化和网络传输开销。KeyBy、rebalance 这些 redistribute 操作会断开链。可以通过 disableChaining、startNewChain 这些 API 精细控制。它和 Slot 共享不是一回事,前者是同一线程内的算子合并,后者是同一 Slot 跑多个独立 Task。"

如果需要, 我可以接着讲解 **Slot 共享机制**, **Task 与 Slot 的对应关系**, 或者给一个**算子链调优的真实案例**.