# 什么是 HDF5 训练格式?

HDF5 (Hierarchical Data Format version 5) 是一种 **面向大规模科学数据的二进制文件格式**. 名字里的关键词是 "Hierarchical"(层次化)——它可以在**一个文件内**用类似文件系统目录树的结构, 组织存放海量的多维数组数据, 并附带元信息.

在你这个具身机器人项目里, "HDF5 训练格式"指的是: 把 ETL 处理后/已经对齐好的多模态数据, 按照模仿学习(Imitation Learning)训练所需的结构, 打包成 `.hdf5` 文件, 作为下游策略模型训练的**直接输入**.

## HDF5 的核心概念(面试常考三件套)

HDF5 内部就三个核心抽象, 类比文件系统很好记:

| HDF5 概念 | 类比 | 说明 |
|-----------|------|------|
| **Group** | 文件夹 | 用来分层组织数据, 可以嵌套 |
| **Dataset** | 文件 | 实际存储的多维数组(N-dimensional array) |
| **Attribute** | 文件的标签/属性 | 挂在 Group 或 Dataset 上的元信息(如采样率/传感器型号) |

一个典型的机器人 episode(一条演示轨迹)在 HDF5 里的结构大概长这样:

```
episode_0.hdf5
├── /observations                # Group: 观测
│   ├── /images
│   │   ├── /cam_high      [T, H, W, 3]   # Dataset: 头部相机图像序列
│   │   ├── /cam_left_wrist[T, H, W, 3]   # 左手腕相机
│   │   └── /cam_right_wrist[T,H, W, 3]   # 右手腕相机
│   ├── /qpos              [T, 14]        # 关节位置(如双臂各7自由度)
│   └── /qvel              [T, 14]        # 关节速度
├── /action                [T, 14]        # Dataset: 动作序列(遥操指令)
└── (attributes)
    ├── sim = False                # 属性: 是否仿真数据
    └── compress = True
```

其中 `T` 是这条轨迹的时间步长度. 注意所有模态的第一维都是 `T` 且已对齐——**这正是你 ETL 里"异频时间戳对齐"的产出结果**. 这是一个很自然的追问衔接点.

## 为什么机器人/具身领域偏爱 HDF5

这部分能体现你"选型有依据". HDF5 之所以是 ACT / ALOHA 等经典模仿学习工作的默认格式, 原因很实在:

1. **天然适配多模态异构数据**: 图像是 4维数组, 关节状态是 2 维数组, 动作是 2 维数组——HDF5 能把不同形状、不同类型的 dataset 装进同一个文件, 结构清晰.

2. **支持切片读取(partial I/O)**: 训练时经常只需要读某条轨迹的第 100~120 帧, HDF5 可以只从磁盘读这一小块, 不用把整个文件加载进内存. 对动辄几个 GB 的图像数据集非常关键.

3. **内置压缩与分块(chunking)**: 支持 gzip/lzf 压缩, 图像数据压缩后体积大幅下降; chunk 机制让切片读取更高效.

4. **自描述 + 跨语言**: 元信息内嵌, C/C++/Python/MATLAB 都能读, `h5py` 在 Python 生态里是事实标准.

## HDF5 vs LeRobot 格式(你简历里两个都写了)

你简历里写的是"输出 LeRobot/HDF5 训练格式", 面试官很可能问它们的区别和你为什么两个都做. 简单对比:

| 维度 | HDF5 | LeRobot (基于 parquet + 视频) |
|------|------|------------------------------|
| 定位 | 单 episode 打包, 经典模仿学习(ACT/ALOHA) | HuggingFace 推出的标准化机器人数据集格式 |
| 图像存储 | 数组或压缩帧存在文件内 | **视频编码(mp4)** 存图像, 数值存 parquet |
| 存储效率 | 图像用图像压缩, 一般 | 视频编码, 大数据集下**体积小很多** |
| 生态 | 传统/通用/稳定 | 新, 和 HuggingFace/`lerobot` 库深度集成, 社区活跃 |
| 随机访问 | chunk 切片 | parquet 列存 + 视频关键帧索引 |

你可以这样表述这个双输出的设计决策:

> "我们同时支持两种输出格式是为了兼容不同的下游需求: HDF5 面向团队里基于 ACT/ALOHA 这类经典模仿学习 pipeline 的同学, 拿来即用; LeRobot 格式则是为了对接 HuggingFace 生态和更新的 VLA 类模型训练, 而且它用视频编码存图像, 大规模数据集下存储成本明显更低. ETL 后端做成可插拔的 writer, 同一份对齐后的中间数据可以导出成任意一种格式."

## Python 里怎么写一个 HDF5 训练样本

给你一段核心实现, 帮你理解落地细节, 面试也可能让你手写:

```python
import h5py
import numpy as np

def save_episode_to_hdf5(output_path: str, data: dict):
    """
    将 ETL 对齐后的一条轨迹(episode)写入 HDF5 训练格式.

    :param output_path: 输出文件路径, 如 episode_0.hdf5
    :param data: 已完成时间戳对齐的多模态数据, 各模态第一维长度均为 T
    """
    T = data["action"].shape[0]  # 轨迹时间步长度

    # 'w' 模式创建新文件; 用 with 保证文件句柄正确关闭
    with h5py.File(output_path, "w") as f:
        # 挂在根节点上的属性(Attribute), 记录这条轨迹的元信息
        f.attrs["sim"] = False          # 标记非仿真数据
        f.attrs["episode_len"] = T      # 轨迹长度, 便于下游校验

        # ---- 观测部分: 创建 observations 这个 Group ----
        obs_group = f.create_group("observations")

        # 关节位置 qpos: shape [T, 14], 数据量小, 直接存, 不压缩
        obs_group.create_dataset("qpos", data=data["qpos"])

        # 图像子 Group
        image_group = obs_group.create_group("images")
        for cam_name, frames in data["images"].items():
            # frames: [T, H, W, 3] 的 uint8 图像序列
            image_group.create_dataset(
                cam_name,
                data=frames,
                dtype="uint8",
                # chunks: 按"单帧"分块, 训练时可只读某几帧, 不用加载全部
                chunks=(1, *frames.shape[1:]),
                # 对图像启用 gzip 压缩, 显著降低磁盘占用
                compression="gzip",
                compression_opts=4,  # 压缩等级, 4 是速度/体积的折中
            )

        # ---- 动作部分: action 作为顶层 Dataset ----
        # shape [T, 14], 训练时作为监督标签
        f.create_dataset("action", data=data["action"])


# 读取时的切片示例: 只加载第 100~120 帧的头部相机图像
def read_slice(path: str):
    with h5py.File(path, "r") as f:
        # 注意: 这里的切片是"惰性读取", 只有被索引的这一小块才真正从磁盘加载
        clip = f["observations/images/cam_high"][100:120]  # -> [20, H, W, 3]
        return clip
```

关键点注解:
- **`chunks` 参数**是性能核心. 按帧分块后, 切片读取只触碰需要的块, 避免全量解压.
- **`compression`** 让图像数据集体积可控, 但压缩等级越高写入越慢, 生产中一般取中间值.
- **切片是惰性的**: `f[...][100:120]` 只读那 20 帧, 这是 HDF5 相比"一个 numpy .npy 存整条轨迹"的最大优势.


一句话总结, 面试可以这么答:

> "HDF5 是一种层次化的二进制科学数据格式, 用 Group/Dataset/Attribute 三层抽象在单文件内组织多维数组和元信息. 在我们项目里, 它是 ETL 的一种输出训练格式——把对齐后的多模态数据(多路相机图像/关节状态/动作)按 observations/action 的结构打包成一条 episode. 选它是因为它天然适配异构多维数组、支持切片惰性读取和分块压缩, 也是 ACT/ALOHA 这类模仿学习工作的标准输入格式."

想继续的话, 这几个是紧密相关、面试官会顺藤摸瓜的点:

1. **HDF5 的 chunk 和压缩具体怎么调优**, 大数据集训练时 I/O 瓶颈怎么解决
2. **多进程/多 worker 读 HDF5 的坑**(`h5py` 在 PyTorch DataLoader `num_workers>0` 时的经典问题)
3. 从 ROS2 bag 到 HDF5 的**完整 ETL 数据流**是怎么串起来的

要不要我帮你把其中一个补成能写进简历, 又扛得住追问的细节?