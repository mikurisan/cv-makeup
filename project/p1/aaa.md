# JobManager 详解

## 1 核心定位

**JobManager** 是 Flink 集群的**协调者 (Coordinator)** 和**大脑**, 负责整个[作业](./aaaa.md)的生命周期管理. 它在一个 Flink 集群中通常**只有一个**(支持 HA 时可有多个备节点).

类比:
- **JobManager** ≈ 大脑 / 指挥官(只发号施令, 不亲自干活)
- **TaskManager** ≈ 工人(真正执行计算的节点)

## 2 核心职责

| 职责 | 说明 |
|------|------|
| **作业调度 (Scheduling)** | 将用户提交的 JobGraph 拆解成执行图, 分配到各 TaskManager 的 [Slot](./aaab.md) 上 |
| **资源管理 (Resource Management)** | [管理 TaskManager 上的 Slot 资源](./aaac.md), 决定谁能用/用多少 |
| **协调检查点 (Checkpoint Coordination)** | 周期性向所有 TaskManager 发起 [Checkpoint 屏障](./aaad.md), 收集 [ACK](./aaae.md) |
| **故障恢复 (Fault Recovery)** | TaskManager 失败时, 重新调度受影响的算子 |
| **REST / Web UI** | 提供 `:8081` 端口, 展示作业状态/指标/Savepoint 等 |
| **作业提交接收** | 接收 client 端提交的 Jar / SQL Job |

## 3 内部组件

```
JobManager
├── Dispatcher         ← 接收作业提交,启动 JobMaster
├── ResourceManager    ← 管理 TaskManager 的 Slot 资源(YARN/K8s/Standalone 适配层)
└── JobMaster          ← 单个作业的主控, 一个作业对应一个
    ├── Scheduler        ← 调度器 (决定算子在哪些 Slot 上执行)
    ├── CheckpointCoordinator ← 检查点协调
    └── RecoveryManager ← 状态后端恢复
```

> 注意: 在 **最小集群** 中, JobManager 和 ResourceManager 是合并的(Standalone 模式); 在 **YARN/K8s** 上, ResourceManager 是 YARN RM / K8s Scheduler.

## 4 HA (高可用)

JobManager 是**单点**, 所以生产环境必须配置 HA:

| 模式 | 实现 |
|------|------|
| Standalone HA | 基于 **ZooKeeper** 选举 Leader |
| YARN | YARN 自身负责重启 JobManager |
| K8s | 通过 **K8s Leader Election** 选举 |

状态信息(已完成 Checkpoint 的元数据)存储在 **ZooKeeper** 中, 确保主备切换后能续上.

## 5 面试高频问题

1. **JobManager 和 TaskManager 如何通信?**
   → 基于 **Akka** (Flink ≤ 1.15) 或 **Netty RPC** (Flink ≥ 1.16), 通过 `RpcEndpoint` 机制.

2. **作业提交到 JobManager 后, 发生了什么?**
   → Client → Dispatcher → 启动 JobMaster → Scheduler 申请 Slot → 部署算子.

3. **JobManager 挂了会怎样?**
   → 新 Leader 上位 → 从最近一次 Checkpoint 恢复 → 重启所有 Task.

4. **JobManager 内存里有什么?**
   → 主要存 **作业执行图**、**Checkpoint 元数据**、**累积的指标数据**; 不存用户业务状态(用户在 TM 的 StateBackend).

## 6 面试回答模板 (简洁版)

> "JobManager 是 Flink 的主控节点, 核心职责是**作业调度、资源管理、Checkpoint 协调和故障恢复**. 它本身不处理数据, 数据在 TaskManager 上流动. 生产中需要通过 ZooKeeper 或 K8s 实现 HA, 因为它挂了整个作业就停了. 内部主要包含 Dispatcher、ResourceManager 和 JobMaster 三个组件, 每个作业对应一个 JobMaster."

如果需要, 我可以接着讲解 **TaskManager**、**Slot 共享机制**, 或给出 JobManager 故障排查的真实案例.