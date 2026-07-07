# “作业” (Job) 的含义

## 1 字面定义

在 Flink 中, **作业 (Job)** 是一个**完整的流式计算逻辑单元**, 从用户提交的那一刻起, 到结束或失败为止, 代表一次完整的计算任务.

类比:

- **作业 (Job)** = 一个完整的"任务工单"

- **JobGraph** = 工单的"执行说明书"

- **JobManager** = 调度这个工单的"项目经理"

- **TaskManager** = 实际干活的"工人"

## 2 具体含义

一个 **Job** 包含 3 部分:

| 组成部分 | 含义 |
|---------|------|
| **业务逻辑** | 用户写的转换代码 (map, filter, join ... / SQL / DataStream API) |
| **数据源** | Kafka, MySQL CDC, Socket 等 |
| **数据汇** | 输出到 Kafka, MySQL, ES 等 |

例如用户提交了一段 SQL:

```sql
SELECT user_id, COUNT(*) FROM orders GROUP BY user_id;
```
这段 SQL 被**解析, 优化, 生成执行计划**后, 就是一个 **Job**.

## 3 Job 的生命周期的 5 个状态

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ CREATED  │──►│ RUNNING  │──►│RESTARTING│──►│ RUNNING  │──►│ FINISHED │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
     │              │
     ▼              ▼
┌──────────┐   ┌──────────┐
│  FAILED  │   │CANCELLING│
└──────────┘   └──────────┘
```

可对应看 Web UI 的 `Jobs` 页面.

## 4 一个 Job = 一个 JobMaster

重要细节:

- **JobManager 进程** 是常驻的

- **JobMaster** 是**每个 Job 独有的** (一个 Flink 集群可同时跑多个 Job, 每个 Job 都有自己的 JobMaster)

```
JobManager (常驻进程)
   ├── JobMaster (Job A)
   ├── JobMaster (Job B)
   └── JobMaster (Job C)
```

## 5 Job vs JobGraph vs ExecutionGraph

| 层级 | 谁生成 | 内容 |
|------|--------|------|
| **StreamGraph** | Client 端 | [用户逻辑的初步 DAG](./aaaaa.md) |
| **JobGraph** | Client → JobManager | 优化后, 可序列化的执行计划 |
| **ExecutionGraph** | JobManager 内部 | 按并行度展开后, 可调度的执行实例 |

**Job** 一般指用户感知到的这个完整计算任务, 内部在 Flink 引擎中流转时是上述几个图的迭代。

---

## 6 面试回答模板

> "这里的'作业'就是用户提交的一个完整计算任务,比如一段 SQL、一个 DataStream 程序。它从数据源读取数据,经过一系列转换,最后输出到 Sink。一个作业从创建、调度、运行到结束,对应一套完整的状态流转,Flink 会为每个作业分配一个独立的 JobMaster 来管理它的调度、Checkpoint 和故障恢复。"

---

如果需要,我可以再展开 **JobGraph → ExecutionGraph 的生成过程**,或者讲解**多作业同时运行**时 JobManager 的资源隔离策略。