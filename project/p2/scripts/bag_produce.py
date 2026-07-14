# 安装: pip install rosbags numpy
import numpy as np
from pathlib import Path
from rosbags.rosbag2 import Writer
from rosbags.typesys import Stores, get_typestore

typestore = get_typestore(Stores.ROS2_HUMBLE)


def gen_timestamps(freq_hz, duration_s, jitter_ratio=0.05):
    """生成带抖动的时间戳序列(纳秒), 用于复现真实传感器的采样不确定性."""
    period_ns = int(1e9 / freq_hz)
    n = int(duration_s * freq_hz)
    jitter = np.random.uniform(-period_ns * jitter_ratio,
                               period_ns * jitter_ratio, size=n)
    base = np.arange(n) * period_ns
    ts = (base + jitter).astype(np.int64)
    return np.sort(ts)


def make_header(typestore, stamp_ns, frame_id):
    """构造 std_msgs/Header, stamp 就是 ETL 对齐要读的采集时刻."""
    Time = typestore.types['builtin_interfaces/msg/Time']
    Header = typestore.types['std_msgs/msg/Header']
    return Header(
        stamp=Time(sec=stamp_ns // 10**9,
                   nanosec=stamp_ns % 10**9),
        frame_id=frame_id,
    )


def build_mini_bag(out_dir='mini_aloha_bag', duration_s=5.0):
    JointState = typestore.types['sensor_msgs/msg/JointState']
    Image = typestore.types['sensor_msgs/msg/Image']
    Float64MultiArray = typestore.types['std_msgs/msg/Float64MultiArray']

    with Writer(Path(out_dir)) as writer:
        # ---- 1. 注册 connection (变量名统一用 conn_ 前缀) ----
        conn_cam = writer.add_connection('/camera_head/image',
                                         Image.__msgtype__, typestore=typestore)
        conn_joint = writer.add_connection('/joint_states',
                                           JointState.__msgtype__, typestore=typestore)
        conn_action = writer.add_connection('/action',
                                            Float64MultiArray.__msgtype__, typestore=typestore)

        # ---- 2. 相机 30Hz ----
        for ts in gen_timestamps(freq_hz=30, duration_s=duration_s):
            img = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
            msg = Image(
                header=make_header(typestore, ts, 'cam_head'),
                height=64, width=64,
                encoding='rgb8',
                is_bigendian=0,
                step=64 * 3,
                data=img.flatten(),
            )
            writer.write(conn_cam, ts, typestore.serialize_cdr(msg, Image.__msgtype__))

        # ---- 3. 关节 100Hz (注意补上循环变量 i) ----
        joint_names = [f'joint_{i}' for i in range(7)]
        for k, ts in enumerate(gen_timestamps(freq_hz=100, duration_s=duration_s)):
            t = k / 100.0
            positions = [0.5 * np.sin(2 * np.pi * 0.2 * t + i) for i in range(7)]
            msg = JointState(
                header=make_header(typestore, ts, 'base'),
                name=joint_names,
                position=np.array(positions, dtype=np.float64),
                velocity=np.array([], dtype=np.float64),
                effort=np.array([], dtype=np.float64),
            )
            writer.write(conn_joint, ts, typestore.serialize_cdr(msg, JointState.__msgtype__))

        # ---- 4. 动作 20Hz ----
        for k, ts in enumerate(gen_timestamps(freq_hz=20, duration_s=duration_s)):
            t = k / 20.0
            action = [0.5 * np.sin(2 * np.pi * 0.2 * t + i) for i in range(7)]
            msg = Float64MultiArray(
                layout=typestore.types['std_msgs/msg/MultiArrayLayout'](dim=[], data_offset=0),
                data=np.array(action, dtype=np.float64),
            )
            writer.write(conn_action, ts, typestore.serialize_cdr(msg, Float64MultiArray.__msgtype__))

    print(f'✅ mini bag 已生成: {out_dir}')


if __name__ == '__main__':
    np.random.seed(42)
    build_mini_bag()