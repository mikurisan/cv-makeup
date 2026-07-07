# Flink 是什么?

## 1 核心定义

**Apache Flink** 是一个[**分布式**](./aa.md)、高性能、始终可用**的流处理框架, 同时也支持批处理, 核心定位是"**用流式计算统一数据处理范式**".

> 一句话总结: Flink = 分布式流计算引擎, 以"流"为核心, 批处理视为"有界流".

## 二、关键特性（面试高频考点）

### 1. 真正的流式引擎
| 对比维度 | Flink | Spark Streaming |
|---------|-------|-----------------|
| 处理模型 | **逐事件 (Event-by-Event)** | 微批 (Micro-batch) |
| 延迟 | 毫秒级 | 秒级 |
| 状态管理 | 内置 RocksDB 状态后端 | 需自行处理 |

### 2. 四大核心优势
- **Exactly-Once 语义**: 基于分布式快照算法 (Chandy-Lamport), 保证数据不丢不重
- **Event Time + Watermark**: 正确处理乱序事件, 是 Flink 区别于其他引擎的关键能力
- **Stateful 计算**: 内置状态后端 (Memory / RocksDB), 支持 TB 级状态
- **分层 API**: 
  ```
  SQL / Table API  →  DataStream API  →  ProcessFunction (最底层)
  (易用)              (灵活)              (极强, 可处理 Timer/State)
  ```

### 3. 运行时架构
```
Client → JobManager (Master) → TaskManager (Worker) × N
                              ↓
                         Checkpoint Coordinator
```
- **JobManager**: 调度、容错、协调
- **TaskManager**: 执行具体算子, 持有 State
- **Slot**: 资源隔离单元

## 三、为什么选择 Flink？（数仓场景视角）

结合你的项目经验, 回答这个问题时要**贴合业务场景**:

1. **CDC 实时入仓**: Flink CDC 基于 Debezium, 能捕获 MySQL Binlog 的增量变更, 比传统的 Sqoop/DataX 定时同步延迟低 100 倍
2. **分层建模需要状态**: DWS 层聚合指标依赖滚动窗口或状态, Flink 的 State + Timer 是天然解
3. **端到端 Exactly-Once**: 从 Source → Sink 写入 StarRocks, 配合两阶段提交, 保证数据零误差
4. **高吞吐低延迟**: 日均 100W+ 次查询对应的入仓流量通常 10W+ QPS, Flink 单集群可横向扩展

## 四、可能的追问与建议回答

| 面试官可能追问 | 建议回答思路 |
|--------------|------------|
| Flink 和 Spark 的区别? | 流模型本质不同 + 状态管理 + Event Time 支持 |
| 什么是 Checkpoint? | 分布式快照, 周期性将 State 持久化, 故障时从最近快照恢复 |
| 什么是 Watermark? | 衡量 Event Time 进度的机制, 解决乱序问题 |
| Flink 如何保证 Exactly-Once? | Checkpoint + 两阶段提交 + 幂等写入 |
| 为什么选 Flink CDC 而不是 Canal? | Flink CDC 集成度高, 支持全量+增量一体化, 减少组件 |

## 五、给你简历的补充建议

你简历中提到了 "**checkpoint 保障端到端可重放**", 这其实只是 Flink 容错的基础能力, 面试官大概率会深挖:

> ⚠️ **容易被挑战的点**: 
> - 你的 Checkpoint 间隔设多少？太大影响恢复时间, 太小影响吞吐
> - 用了哪种 State Backend？为何选 RocksDB？
> - **端到端 Exactly-Once** 还是 **At-Least-Once**？StarRocks Sink 怎么保证？

**建议补充**: 在简历或面试中说明 "**Checkpoint 间隔 60s + RocksDB State Backend + StarRocks 两阶段提交, 实现端到端 Exactly-Once**", 这样更具说服力.

---

需要我针对这个项目, 模拟一**面试官的连环追问**吗？我可以站在资深面试官角度, 对 "Flink CDC"、"分层建模"、"StarRocks 物化视图" 等点逐个深挖, 帮你提前准备.