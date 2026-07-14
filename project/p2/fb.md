# 什么是 CDR (DDS 标准序列化)?

CDR 全称 **Common Data Representation(通用数据表示)**, 是 **OMG(对象管理组织)** 定义的一种**二进制序列化标准**. 它是 DDS 通信中间件传输数据时使用的编码格式, 而 ROS2 底层通信正是构建在 DDS 之上, 所以 ROS2 里每一条消息在网络传输和存进 bag 时, 默认都是用 CDR 编码的.

先把几个概念的关系理清楚:

```
ROS2 (应用层)
  └── rmw (ROS Middleware 抽象层, 屏蔽底层实现)
        └── DDS (通信中间件, 如 Fast-DS / Cyclone DS)
              └── CDR (DS 规定的数据序列化格式)  ← 消息在这里变成字节流
```

## 什么是"序列化", 为什么需要它

**序列化(serialization)** 就是把内存里的结构化对象(比如一个 `JointState` 消息, 里面有数组/浮点数/字符串)转换成一段**连续的字节流**, 以便通过网络传输或写入文件. 反过来把字节流还原成对象, 叫**反序列化(deserialization)**.

需要它的原因: 内存里的对象是带指针/带内存布局的, 不能直接扔到网线上或存进磁盘. 必须先"压平"成一串确定的字节.

## CDR 的核心特点

**1. 二进制格式, 不是文本**

不像 JSON/XML 那种可读文本, CDR 是紧凑的二进制. 优点是体积小、编解码快, 适合机器人这种高频实时通信. 缺点是不可读, 需要 schema(消息定义)才能解析.

**2. 字节对齐(alignment)**

这是 CDR 一个很有特点的地方, 也是面试深挖点. CDR 会按数据类型做**内存对齐填充**: 比如一个 4 字节的 `int32` 必须放在 4 的倍数的偏移位置, 不够就填充(padding)空字节. 这样做是为了让接收端能高效读取(CPU 读对齐内存更快), 代价是会有一些填充字节的空间浪费.

**3. 字节序(endianness)标记**

CDR 数据流开头有几个字节, 标明这段数据是大端(big-endian)还是小端(little-endian). 因为不同 CPU 架构字节序不同, 接收端要靠这个标记正确解析. ROS2 里这段头信息就是常说的 **encapsulation header**(封装头).

**4. 依赖 IDL / 消息定义**

CDR 本身不携带字段名等 schema 信息(和自描述的格式如 mcap 内嵌 schema 不同). 收发双方必须约定好同一份消息定义(ROS2 里就是 `.msg` 文件, 底层对应 OMG 的 IDL). 这也是为什么 ROS2 消息类型不匹配时会直接报错或解析出乱码.

## 一段字节流长什么样(直观感受)

假设有个简单消息 `int32 x; int8 y; int32 z;`, CDR 编码后大致是:

```
[encapsulation header 4字节]   # 字节序标记 + 保留位
[x: 4字节]                     # int32, 偏移0对齐
[y: 1字节]                     # int8
[padding: 3字节]  ← 填充!       # 为了让下一个int32对齐到4的倍数
[z: 4字节]                     # int32
```

那3 个填充字节就是 CDR 对齐机制的体现. 面试官如果问"为什么 CDR 的字节数比字段实际大小之和要多", 答案就是对齐填充.

## 结合你的项目: 为什么这跟 ETL 有关

在你的 ROS2 bag ETL 流水线里, 从 bag(sqlite3/mcap)读出来的每条消息, **磁盘上存的就是 CDR 字节流**. 你要处理它有两条路:

**线 A: 反序列化成对象再处理**
用 `rclpy.serialization.deserialize_message` 把 CDR 字节流还原成 ROS2 消息对象, 拿到具体字段(图像/关节角度), 再做裁剪 / 对齐 / 转 HDF5.

```python
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

# bag 里读出来的是 (topic, 原始CDR字节流, 时间戳)
msg_type = get_message('sensor_msgs/msg/JointState')  # 根据类型字符串拿到消息类
# 把 CDR 字节流反序列化成可操作的对象
msg = deserialize_message(raw_cdr_bytes, msg_type)
print(msg.position)  # 现在可以访问具体字段了
```

**路线 B: 只搬运不解析(topic 重映射/裁剪场景)**
如果只是做 topic 重命名、时间段裁剪, 不需要看消息内容, 就可以**直接透传 CDR 字节流**, 不反序列化. 这样能省掉大量编解码开销, 大幅提升 ETL 吞吐.

这就是一个很好的工程优化点, 面试里可以这样讲:

> "做 topic 重映射和时间裁剪时, 我们发现没必要反序列化——消息内容不用改, 只改元信息. 所以我们直接以原始 CDR 字节流为单位搬运, 跳过 deserialize/serialize, 单条处理开销从 X 降到 X, 整体流水线吞吐提升了约 X 倍. 只有真正要转格式(LeRobot/HDF5)、要做时间戳对齐取值时才反序列化."

这个点很能体现你对底层序列化机制的理解, 而不是只会调 API.

一句话总结, 面试里可以这么说:

> "CDR 是 OMG 定的二进制序列化标准, DDS 用它来编码传输数据, ROS2 基于 DS 所以消息默认都是 CDR 格式. 它的特点是紧凑二进制、带字节序标记、按类型做对齐填充, 并且不自带 schema, 需要收发双方共享消息定义. 我们的 bag 里存的就是 CDR 字节流, ETL 里根据是否需要改内容, 分别选择反序列化处理或直接透传字节流来优化吞吐."

想继续的话, 相关且高频的深挖方向:

1. **rmw / DS 抽象层**: 为什么 ROS2 要搞这层, Fast-DDS 和 Cyclone DDS 怎么选
2. **CDR 的对齐机制**对大数据量(如图像)的实际影响, 以及序列化的性能瓶颈怎么定位
3. ROS2 里 **QoS(服务质量)** 策略, 和数据可靠性/丢帧强相关, 采集场景常被问