# ACK (Acknowledgement) 在 Flink 中的含义

## 1 基础概念

**ACK = Acknowledgement (确认/应答)**

> 发出一方: "我做完了, 告诉你一声. "

> 接收一方: "收到."

## 2 在 Checkpoint 中的具体作用

```
CheckpointCoordinator (JobManager)
         │
         │  Send Barrier + Trigger Checkpoint
         ▼
    ┌─────────┐   ┌─────────┐   ┌─────────┐
    │ Source  │   │  Map    │   │ Window  │
    └────┬────┘   └────┬────┘   └────┬────┘
         │             │             │
         │ ACK Success │ ACK Success │ ACK Success
         ▼             ▼             ▼
    ┌──────────────────────────────────────┐
    │       CheckpointCoordinator          │
    │  Wait for all operators' ACKs.       │
    │  All must arrive to be considered ✓  │
    └──────────────────────────────────────┘
```

### 流程

| 步骤 | 动作 |
|------|------|
| 1 | CheckpointCoordinator 向所有 Source 注入 Barrier |
| 2 | 各算子完成本地快照 |
| 3 | **各算子发送 ACK** 给 CheckpointCoordinator |
| 4 | Coordinator 收齐所有 ACK → 标记 Checkpoint 成功 |


## 3 为什么需要 ACK?

防止**部分算子失败**却仍认为 Checkpoint 成功.

```
场景: Window 完成快照, 但 Source 超时未发送 ACK

结果: Coordinator 等待超时 → 判定 Checkpoint 失败 → 不保存
      → 下次恢复时不会用这个不完整的快照
```

## 4 其他 ACK 场景

| 场景 | ACK 来源 |
|------|---------|
| **Checkpoint** | TaskManager → JobManager |
| **Kafka 消费** | Consumer → Broker (确认消息已接收) |
| **网络通信** | 接收方 → 发送方 (确认数据包已到达) |
| **RPC 调用** | 服务端 → 客户端 (确认请求已处理) |

## 5 简洁回答

> "ACK 是确认消息, 表示'我已完成操作'. 在 Flink Checkpoint 中, 每个算子完成快照后向 JobManager 发送 ACK,只有全部算子都 ACK 了, Checkpoint 才算成功, 否则丢弃. ACK 机制保证了分布式环境下操作的完整性和一致性."