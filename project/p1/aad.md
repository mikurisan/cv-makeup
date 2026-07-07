# State 和 Key 的概念及关系

## 1 什么是 State?

### 1. 定义
**State (状态)** 是 Flink 在**流式计算过程中需要记住的中间数据**, 用于支持有状态的计算逻辑.

### 2. 形象理解

想象你在统计每个用户今天的订单总金额:

```
用户A下单 100元 → 累加器: 100
用户A下单 200元 → 累加器: 300  ← 这个"累加器"就是 State
用户B下单 500元 → 累加器: 500
```

**没有 State 的话**, 每次来新数据你都不知道之前累加到多少了.

**有 State**, Flink 会帮你记住 "用户A当前累加了300元", 下次再来订单直接在300基础上累加.

## 2 什么是 Key?

### 1. 定义
**Key (键)** 是用来**对数据流进行分组的标识**, 通常是业务维度字段, 如 `user_id`、`order_id`、`product_id`.

### 2. 为什么需要 Key?

因为流式数据是**乱序**的, 不同用户的数据会混在一起:

```
原始流:
user_001 订单100元
user_002 订单200元
user_001 订单300元  ← 同一个用户的数据分散在不同位置
user_003 订单500元
```

通过 `keyBy(user_id)` 后, **Flink 会把相同 Key 的数据路由到同一个算子实例处理**:

```
keyBy(user_id) 后:

分区1: user_001 的所有订单 → 累加器存 user_001 的状态
分区2: user_002 的所有订单 → 累加器存 user_002 的状态
分区3: user_003 的所有订单 → 累加器存 user_003 的状态
```

## 3 State 和 Key 的关系

### 核心关系: **State 是按 Key 隔离存储的**

```
┌──────────────────────────────────────────┐
│              Keyed State                 │
│                                          │
│  Key: user_001  →  State: Sum = 300      │
│  Key: user_002  →  State: Sum = 200      │
│  Key: user_003  →  State: Sum = 500      │
└──────────────────────────────────────────┘
```

每个 Key 有自己独立的 State, 互不干扰.

### 代码示例

```java
// 按用户ID分组
DataStream<Order> orders = ...;
KeyedStream<Order, String> keyedOrders = orders.keyBy(order -> order.getUserId());

// 使用 ValueState 记住每个用户的累加金额
keyedOrders
    .process(new KeyedProcessFunction<String, Order, String>() {
      
        // State 定义: 每个 Key 有自己独立的累加器
        private ValueState<Double> totalAmountState;
      
        @Override
        public void open(Configuration parameters) {
            // 注册 State (Flink 会自动按 Key 隔离)
            ValueStateDescriptor<Double> descriptor = 
                new ValueStateDescriptor<>("totalAmount", Double.class);
            totalAmountState = getRuntimeContext().getState(descriptor);
        }
      
        @Override
        public void processElement(Order order, Context ctx, Collector<String> out) throws Exception {
            // 读取当前 Key 的 State (比如 user_001 的累加器)
            Double currentTotal = totalAmountState.value();
            if (currentTotal == null) {
                currentTotal = 0.0;
            }
          
            // 累加新订单金额
            currentTotal += order.getAmount();
          
            // 更新当前 Key 的 State
            totalAmountState.update(currentTotal);
          
            out.collect("用户 " + order.getUserId() + " 累计金额: " + currentTotal);
        }
    });
```

**关键点**:

- `keyBy()` 后, Flink 自动把相同 Key 的数据路由到同一个算子实例

- `ValueState` 会为每个 Key 维护独立的值

- `user_001` 的 State 和 `user_002` 的 State **完全隔离**, 互不影响

## 4 分布式环境下的 State 分片

回到你的疑问: **"按 Key 分片存到不同 TaskManager"** 是什么意思?

### 1. 单机视角

假设只有 1 个 TaskManager, 所有 Key 的 State 都存在这台机器:

```
TaskManager-1 (内存/RocksDB):
├── Key: user_001 → State: 300元
├── Key: user_002 → State: 200元
└── Key: user_003 → State: 500元
```

### 2. 分布式视角 (并行度 = 3)

当设置并行度为 3 时, Flink 会启动 3 个算子实例, 分散到不同 TaskManager:

```
TaskManager-1:
├── 算子实例-1 处理 Key: user_001, user_004, user_007, ...
└── State: 
    ├── user_001 → 300元
    └── user_004 → 150元

TaskManager-2:
├── 算子实例-2 处理 Key: user_002, user_005, user_008, ...
└── State:
    ├── user_002 → 200元
    └── user_005 → 600元

TaskManager-3:
├── 算子实例-3 处理 Key: user_003, user_006, user_009, ...
└── State:
    ├── user_003 → 500元
    └── user_006 → 800元
```

**分片规则**: Flink 根据 `Key.hashCode() % 并行度` 决定 Key 路由到哪个实例.

**关键点**:

- 每个 TaskManager 只存储**部分 Key 的 State**

- 总 State 大小 = 所有 TaskManager 的 State 之和

- 这就是为什么 Flink 能处理 TB 级状态——**State 被分散到整个集群**

## 5 State 的两大类型

| 类型 | 是否需要 Key | 使用场景 |
|------|------------|---------|
| **Keyed State** | ✅ 必须先 `keyBy()` | 用户累加金额/UV 统计/窗口聚合 (最常用) |
| **Operator State** | ❌ 不需要 | Kafka Offset 管理/Source 并行实例状态 |

### Keyed State 常见类型

```java
// 1. ValueState: 存单个值
ValueState<Double> totalAmount;

// 2. ListState: 存列表 (比如最近10笔订单)
ListState<Order> recentOrders;

// 3. MapState: 存 Map (比如用户各品类消费金额)
MapState<String, Double> categoryAmountMap;

// 4. ReducingState: 自动累加
ReducingState<Long> count;

// 5. AggregatingState: 自定义聚合
AggregatingState<Order, Double> avgAmount;
```

## 6 面试官可能的追问

| 追问 | 建议回答方向 |
|------|------------|
| State 存在哪里? | **MemoryStateBackend** (堆内存) / **FsStateBackend** (内存 + HDFS) / **RocksDBStateBackend** (磁盘, 支持 TB 级) |
| State 太大怎么办? | 用 RocksDB + 增量 Checkpoint + TTL 清理过期状态 |
| 如果 Key 分布不均匀咋办? | 数据倾斜, 需要加盐或两阶段聚合 |
| State 怎么保证不丢失? | Checkpoint 周期性持久化 State 到 HDFS/S3 |
| 没有 `keyBy()` 能用 State 吗? | 可以用 Operator State, 但不能按 Key 隔离 |

## 8 总结一句话

> **State 是"记住的数据", Key 是"谁的数据", State 按 Key 隔离存储, 分散到不同 TaskManager, 实现分布式状态管理.**

需要我继续深入讲解 **RocksDB State Backend** 或 **Checkpoint 机制** 吗?这两个是 State 管理的底层实现.