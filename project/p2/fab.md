# 什么是 BLOB?

BLOB 是 **Binary Large Object(二进制大对象)** 的缩写, 指的是数据库里用来**存储任意二进制数据**的一种字段类型. 它不关心里面装的是什么, 只把数据当成一串原始字节(bytes)原样存进去、原样取出来.

对比一下你熟悉的其他字段类型就好理解了:

| 字段类型 | 存什么 | 举例 |
|---------|------|------|
| INTEGER | 整数 | `42` |
| TEXT / VARCHAR | 文本字符串 | `"/camera/image_raw"` |
| REAL / FLOAT | 浮点数 | `3.14` |
| **BLOB** | **原始二进制字节** | 一张图片 / 一段序列化后的消息 / 一个文件 |

关键点: TEXT 存的是**有编码含义的字符**(会按 UTF-8 之类去解释), 而 BLOB 存的是**没有编码含义的裸字节**, 数据库不去解读它, 存进去是什么样, 取出来就是什么样. 图像 / 音频 / 序列化数据这类二进制内容, 如果当文本存会被编码破坏, 所以必须用 BLOB.

## 在 ROS2 bag 里 BLOB 装的是什么

回到你上一轮看到的那张表:

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER,
    timestamp INTEGER,
    data BLOB              -- 这里就是 BLOB
);
```

这个 `data` 字段里存的, 是一条 ROS2 消息**经过 CDR 序列化后的二进制字节流**.

理解这个链条很关键, 面试能答到这一层会显得很扎实:

```
内存里的结构化消息 (比如 sensor_msgs/Image 对象)
        │  序列化 (serialize, ROS2 用 CDR)
        ▼
   一串二进制字节 (bytes)
        │  存进数据库
        ▼
   messages 表的 data 字段 (BLOB)
```

读的时候就是反过来: 从 BLOB 取出字节 → 反序列化(deserialize) → 还原成结构化消息对象. 你ETL 流水线的"流式解析"本质就是在做这一步——把 BLOB 里的裸字节按对应消息类型解回来.

## 用 Python 直观感受一下

```python
import sqlite3
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import Image  # 假设这个 topic 是图像

conn = sqlite3.connect("my_recording_0.db3")
cursor = conn.cursor()

# 查出某个 topic 的消息, data 就是 BLOB, 在 Python 里表现为 bytes 类型
cursor.execute("SELECT timestamp, data FROM messages WHERE topic_id = 1")

for timestamp, data in cursor.fetchall():
    # data 此时是 bytes, 一堆裸字节, 直接 print 是乱码, 因为它不是文本
    print(type(data))              # <class 'bytes'>

    # 关键: 必须用消息类型去反序列化, 才能还原成可用的结构化对象
    msg = deserialize_message(data, Image)
    print(timestamp, msg.width, msg.height)  # 现在能拿到图像的宽高等字段了

conn.close()
```

这段代码就体现了 BLOB 的本质: **数据库层面它只是 `bytes`, 数据库不知道也不关心它是图像还是点云; 只有拿到"消息类型"这把钥匙去反序列化, 才能赋予它结构和含义.**

## 为什么"用 BLOB 存大二进制"是个性能话题

上一轮提到 SQLite3 用 BLOB 存图像 / 点云这类大数据效率一般, 原因值得补一句, 面试深挖时用得上:

- **数据库不为大二进制优化**: 关系库擅长结构化的行列数据和索引查询, 你没法对 BLOB 内容建索引 / 做条件查询(它就是一坨字节). 一张 1080p 图像可能几 MB, 高频存进去, 数据库文件迅速膨胀, B-tree 维护成本上升.
- **读写要经过数据库层**: 每次存取都走 SQLite 的事务和页管理, 相比直接写文件多了一层开销.
- **对比 mcap**: mcap 把这些二进制消息按 chunk 分块 + 压缩存储, 顺序读写, 就是专门针对"大量二进制消息流"设计的, 所以更高效.

所以一个通用的工程经验是: **小的结构化元信息放数据库(可检索), 大的二进制原始数据放对象存储或专用格式文件**. 这恰好对应你项目的架构——MongoDB 存可检索的元信息索引, MinIO 存大的原始数据文件. 你这套设计其实暗含了"数据库不适合直接堆大 BLOB"这个判断, 面试时可以主动点出来.

一句话总结:

> "BLOB 就是数据库里存原始二进制字节的字段类型, 数据库不解释它的内容. ROS2 bag 的 messages 表里, data 字段就是 BLOB, 存的是 CDR 序列化后的消息字节流, 读取时需要用对应消息类型反序列化才能还原成结构化数据."

要不要接着聊:

1. **序列化 / 反序列化 (CDR)** 到底做了什么, 为什么消息要先序列化才能存
2. 为什么"大二进制放对象存储(MinIO)、元信息放数据库"是通用架构原则——这个能直接串起你整个项目的存储设计逻辑
3. Python 里 `bytes` 和 `str` 的区别(和 BLOB vs TEXT 是一个道理)