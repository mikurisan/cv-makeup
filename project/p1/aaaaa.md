# “用户逻辑的初步 DAG”详解

## 1 拆解三个关键词

| 关键词 | 含义 |
|--------|------|
| **用户逻辑** | 用户写的计算代码(比如 `map`、`filter`、`join`、SQL 语句) |
| **初步** | **未经优化**的版本,还保留了用户原本的写法结构 |
| **DAG** | Directed Acyclic Graph,**有向无环图** |

## 2 什么是 DAG?

DAG = 一张**由点和线组成**的图,有两个特点:

1. **有向 (Directed)**: 边有方向, 表示数据流向

2. **无环 (Acyclic)**: 不能形成回路(A → B → A 这种循环不允许)

```
     ┌──────┐        ┌──────┐        ┌──────┐
────►│Source│───────►│ Map  │───────►│ Sink │────►
     └──────┘        └──────┘        └──────┘
```

每个方框是一个**算子 (Operator)**, 箭头表示数据怎么流.

## 3 Flink 中 DAG 的演变过程

Flink 内部 DAG 一共经历 **3 个阶段**:

```
┌──────────────┐    ┌─────────────┐    ┌──────────────────┐
│ StreamGraph  │───►│  JobGraph   │───►│ ExecutionGraph   │
│ (Initial DAG)│    │(Optimized   │    │ (Parallelism-    │
│              │    │   DAG)      │    │  Expanded DAG)   │
└──────────────┘    └─────────────┘    └──────────────────┘
   Client side      Client → JM         JobManager
```

### 1 StreamGraph (用户逻辑的初步 DAG)

- **位置**:在用户提交的 **Client 端**生成

- **特点**:

  - 忠实反映用户写的代码结构

  - 还没做优化合并

  - 还没展开并行度

### 2 JobGraph(优化后的 DAG)

- 在 Client 端或 JobManager 中生成

- **做了什么优化**:

  - **算子链合并 (Operator Chain)**: 把多个算子合并成"链", 减少网络传输

  - 生成可序列化的执行计划

### 3 ExecutionGraph(并行度展开的 DAG)

- **位置**: 在 **JobManager 内部**生成

- **做了什么**:

  - 按并行度把每个算子**拆成多个并行实例**(Subtask)

  - 加上了状态, 中间结果等调度信息

## 4 举例说明

### 用户代码

```java
env.socketTextStream(...)
   .map(line -> line.split(","))     // 算子1
   .filter(arr -> arr.length == 3)   // 算子2
   .keyBy(arr -> arr[0])
   .sum(1)                           // 算子3
   .print();
```

### StreamGraph (初步 DAG)
```
Socket → Map → Filter → KeyBy/Sum → Print
```

**5 个节点**, 完全对应用户写的 5 行.

### JobGraph (优化后)
```
Socket → [Map→Filter→KeyBy/Sum] → Print
```
**可能被合并**:`Map` 和 `Filter` 串成一条链, 减少序列化/网络开销.

### ExecutionGraph(并行度展开)
假设 `Map` 并行度=2,`Sink` 并行度=2:

```
Socket-1 ──► Map-1 ──► KeyBy-1 ──► Sum-1 ──► Print-1
Socket-2 ──► Map-2 ──► KeyBy-2 ──► Sum-2 ──► Print-2
```

每个算子都被**实例化**成多个并行 subtask.

## 5 为什么要经历这三个阶段?

| 阶段 | 解决什么问题 |
|------|------------|
| StreamGraph | **保留用户语义**, 方便用户理解 |
| JobGraph | **优化性能** ([算子链](./aaaaaa.md), 网络 buffer 等) |
| ExecutionGraph | **可调度执行** (知道每个实例跑在哪个 Slot 上) |

## 6 面试回答模板

> "用户逻辑的初步 DAG 指的就是 StreamGraph,在 Client 端生成,忠实反映用户写的算子顺序,还没有经过优化合并,也没有按并行度展开。它是 Flink 作业从代码到执行要经历的第一个阶段,后面会依次转成 JobGraph 做算子链优化,再转成 ExecutionGraph 按并行度展开成可调度的执行实例。"

如果需要,我可以接着讲解**算子链合并的具体规则**,或者给出 **Flink Web UI 中看到的 JobGraph 视图**是怎样的。