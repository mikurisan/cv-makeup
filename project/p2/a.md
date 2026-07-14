# 什么是 MinIO?

MinIO 是一款开源的, 高性能的**对象存储 (Object Storage)** 系统, 完全兼容 Amazon S3 API. 你可以把它理解为"可以自己部署在本地或私有云的 S3".

## 核心概念

对象存储与我们熟悉的文件系统 (File System) 和块存储 (Block Storage) 是三种不同的存储范式:

| 存储类型 | 数据组织 | 访问方式 | 典型场景 |
|---------|------|---------|---------|
| [块存储](./aa.md) | 裸磁盘块 | iSCSI/SCSI | 数据库/虚拟机磁盘 |
| [文件存储](./ab.md) | 目录树层级 | POSIX/NFS | 共享文件/家目录 |
| **对象存储** | 扁平的桶 + 对象 | HTP RESTful API | 海量非结构化数据/备份/数据湖 |

对象存储里没有真正的"目录层级", 一切都是 `bucket/key` 的键值结构. 例如 `s3://robot-data/2024/scene01/episode_001.bag`, 看起来像路径, 实际上 `2024/scene01/episode_001.bag` 只是一个对象的完整 key, 斜杠只是命名约定 (通过 prefix 前缀可以模拟目录遍历).

## MinIO 的关键特性

- **S3 兼容**: 这是它最大的价值. 代码里用 `boto3` 或 AWS SDK 写的逻辑, 几乎不用改就能在 MinIO 和 AWS S3 之间无缝切换. 本地开发用 MinIO, 生产上云用 S3, 这是非常常见的组合.
- **高性能**: 用 Go 编写, 针对高吞吐做了优化, 适合存储大文件 (你的 ROS bag 动辄几个 GB 甚至几十 GB, 正好契合).
- **纠删码 (Erasure Coding)**: 分布式部署时通过纠删码实现数据冗余和容错, 相比传统三副本, 在同等可靠性下节省存储空间.
- **轻量易部署**: 单个二进制文件就能起一个服务, Docker 一行命令即可跑起来, 这也是它在中小团队里流行的原因.

## 一个最简的使用示例

```python
# 使用官方 minio 客户端库操作对象存储
from minio import Minio

# 初始化客户端: endpoint 是 MinIO 服务地址
# access_key / secret_key 相当于账号密码
client = Minio(
    "localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False,  # 本地开发用 HTTP, 生产环境应启用 TLS 设为 True
)

# 创建一个 bucket (桶), 用于存放某个采集批次的数据
bucket_name = "robot-raw-data"
if not client.bucket_exists(bucket_name):
    client.make_bucket(bucket_name)

# 上传一个 ROS bag 文件
# object_name 就是对象的 key, 用 prefix 模拟"目录"做逻辑分区
client.fput_object(
    bucket_name=bucket_name,
    object_name="2024/scene01/episode_001.bag",  # key, 斜杠仅为命名约定
    file_path="/data/episode_001.bag",
)

# 下载 (ETL 流水线读取原始数据时的典型操作)
client.fget_object(
    bucket_name=bucket_name,
    object_name="2024/scene01/episode_001.bag",
    file_path="/tmp/episode_001.bag",
)
```

## 在你这个项目里, MinIO 承担什么角色?

结合你的项目描述, MinIO 是整个数据平台的**原始数据落地层**:

- 遥操 (遥控操作) 采集的多模态原始数据 (ROS bag/图像/点云等) 体积大、格式非结构化, 天然适合对象存储.
- 它和 MongoDB 是**分工关系**: MinIO 存"大块的原始数据 (数据本体)", MongoDB 存"描述这些数据的元信息 (metadata 索引)". 检索时先查 MongoDB 拿到对象的 key 和过滤条件, 再去 MinIO 取实际数据. 这是数据湖的经典设计模式.

面试官很可能会顺着这一点往下挖. 比如:
- "为什么选 MinIO 而不是直接用 NFS 或者数据库存文件?"
- "MinIO 和 S3 的关系是什么? 你们为什么不直接上 S3?"
- "对象存储不适合频繁修改, 你们的数据有更新场景吗? 怎么处理?"

需要我针对 MinIO 这个技术点, 整理一套面试官可能的追问 + 应答思路吗? 或者你想先把这三个技术组件 (MinIO / MongoDB / DVC) 的选型逻辑理清楚, 这块很容易被问到"为什么这么选".