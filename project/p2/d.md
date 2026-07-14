# 介绍一下 MongoDB

MongoDB 是一个**面向文档(Document-Oriented)的 NoSQL 数据库**. 它不用关系型数据库那套"表 + 行 + 列 + 固定 schema"的模型, 而是用**灵活的类 JSON 文档**来存数据. 在你这个项目里, 它承担的角色是"**元信息索引层**"——不存原始大文件(那是 MinIO 的活), 只存描述这些数据的结构化元信息, 支撑多维检索.

## 核心概念(对照关系型数据库理解)

| 关系型数据库(MySQL) | MongoDB | 说明 |
|---|---|---|
| Database | Database | 一样 |
| Table 表 | Collection 集合 | 集合内的文档结构可以不一样 |
| Row 行 | Document 文档 | 一条 BSON(二进制 JSON)记录 |
| Column 列 | Field 字段 | 字段可嵌套, 可以是数组 |
| JOIN 连接 | 嵌入 / `$lookup` | 优先嵌入, 尽量避免跨集合关联 |
| 主键 | `_id` | 默认自动生成 ObjectId |

关键区别在于: **文档可以嵌套**. 一个字段的值可以是数组, 也可以是另一个对象. 这让它天然适合存那种结构不规整/层级深的数据.

## 结合你的项目: 元信息文档长什么样

这是面试时最能体现"你真做过"的部分. 一个采集片段(episode)的元信息文档大概是这样:

```javascript
{
  "_id": ObjectId(".."),
  "episode_id": "ep_20240115_003",
  "task": "pick_and_place_cup",        // 任务/场景
  "robot": "aloha_v2",                 // 机器人本体型号
  "scene": {                // 嵌套对象: 场景配置
    "location": "lab_A",
    "lighting": "normal",
    "objects": ["red_cup", "table"]
  },
  "sensors": [                         // 数组: 传感器配置
    { "topic": "/cam_high/image_raw",  "type": "rgb",   "fps": 30,  "resolution": "1280x720" },
    { "topic": "/cam_wrist/image_raw", "type": "rgb",   "fps": 30 },
    { "topic": "/joint_states",        "type": "state", "fps": 1000 }
  ],
  "duration_sec": 42.5,
  "frame_count": 1275,
  "storage": {                // 指向 MinIO 的物理位置
    "bucket": "raw-bags",
    "object_key": "2024/01/15/ep_003.bag",
    "size_bytes": 2147483648
  },
  "quality": {                         // 质检结果(对应你的 Rerun 质检环节)
    "passed": true,
    "checks": { "timestamp_aligned": true, "no_frame_drop": true }
  },
  "dvc_version": "v1.3",               // 对应 DVC 版本管理
  "created_at": ISODate("2024-01-15T10:30:00Z")
}
```

看这个结构, 你就能顺理成章地讲清楚**为什么用 MongoDB 而不是 MySQL**:

1. **schema 灵活**: 不同机器人/不同任务的传感器配置差异很大(有的 3 路相机, 有的 5 路; 有的带力觉, 有的没有). 如果用 MySQL, 要么开一堆可空列, 要么建关联表 JOIN 得很痛苦. MongoDB 直接用嵌套数组表达, 加字段不用改表结构.
2. **多维检索**: 你简历写的"按场景与传感器配置多维检索", 用 MongoDB 的查询很自然, 后面会举例.
3. **迭代快**: 采集需求经常变(今天加个新传感器, 明天加个新任务类型), NoSQL 的无固定 schema 特性让元信息层能跟着快速演进.

## 检索能力: 面试可能让你现场写查询

"按场景与传感器配置多维检索" 具体怎么查, 你得能写出来:

```javascript
// 查询: lab_A 场景下, 带手腕相机, 且质检通过, 时长大于 30 秒的片段
db.episodes.find({
  "scene.location": "lab_A",                // 嵌套字段用点号访问
  "sensors.topic": "/cam_wrist/image_raw",    // 数组内匹配: 只要有一个元素满足即可
  "quality.passed": true,
  "duration_sec": { "$gt": 30 }               // 范围查询操作符
})
```

如果要做更复杂的统计(比如"每个任务有多少个合格片段"), 用**聚合管道(Aggregation Pipeline)**:

```javascript
db.episodes.aggregate([
  { $match: { "quality.passed": true },          // 先过滤
  { $group: {                                      // 再按task 分组统计
      _id: "$task",
      count: { $sum: 1 },
      total_frames: { $sum: "$frame_count" }
  },
  { $sort: { count: -1 } }
])
```

## 索引: 一定会被追问的性能点

面试官问"数据量大了检索慢怎么办", 答案就是**索引(Index)**. MongoDB 用 **B-tree** 索引, 原理和关系型数据库类似:

```javascript
// 为高频查询字段建索引
db.episodes.createIndex({ "scene.location": 1, "quality.passed": 1 })  // 复合索引
db.episodes.createIndex({ "sensors.topic": 1 })                        // 多键索引(数组字段)
db.episodes.createIndex({ "created_at": -1 })                          // 时间倒序
```

这里有个能体现深度的点——**复合索引的"最左前缀"原则**: 建了 `{location, passed}` 的复合索引, 单独查 `location` 能命中, 但单独查 `passed` 命不中. 顺序要按查询频率和区分度设计. 这是很容易被深挖的地方.

## MongoDB 的优势与坑(区分优缺点, 别只背优点)

**优势**
- schema 灵活, 适合结构多变 / 快速迭代的场景(正是你的项目)
- 水平扩展能力强(分片 Sharding)
- 读写高吞吐, 嵌套文档单次读取就能拿到完整信息, 少JOIN

**坑 / 缺点(面试官爱问, 答得出来才显真实)**
- **不擅长复杂多表关联**: `$lookup` 性能差, 设计时应该靠"嵌入"而非"关联". 如果你的数据关系高度规范化/强关联, MongoDB 反而不如关系型.
- **事务较弱**: 4.0 之后才支持多文档 ACID 事务, 但性能开销比关系型大. 强事务场景(如金融)不首选.
- **无固定 schema 是双刃剑**: 灵活的代价是数据一致性靠应用层保证, 容易出现"脏数据"(字段拼写不一致、类型不统一). 生产环境常用 **JSON Schema 校验** 或应用层(如 Pydantic / Mongoose)来兜底.
- **内存吃得多**: WiredTiger 引擎默认把大量数据缓存在内存, 工作集(working set)超过内存会明显掉性能.

一句话总结, 面试里可以这样开场:

> "MongoDB 是面向文档的 NoSQL 数据库, 用类 JSON 的灵活文档存数据. 在我的项目里它做元信息索引层, 因为不同机器人/不同任务的传感器配置差异很大, schema 灵活这一点正好契合, 我用嵌套数组存传感器配置, 配合复合索引和多键索引, 实现按场景/传感器多维检索. 原始大文件放 MinIO, MongoDB 只存指向它的元信息, 两者职责分离."

想继续的话, 我建议接着准备这几个高频追问:

1. **为什么元信息用 MongoDB, 而不是直接把这些信息也塞进关系型数据库或者文件名里?**
2. **MongoDB 和 MinIO 的数据怎么保证一致性?**(比如 MinIO 上传成功但 MongoDB 写入失败怎么办)
3. **索引怎么设计的、`explain` 怎么看执行计划**

你想先深入哪个? 或者你实际用 MongoDB 到什么程度(建过索引吗? 写过聚合吗?), 告诉我, 我帮你判断哪些细节需要补, 免得面试被问穿.