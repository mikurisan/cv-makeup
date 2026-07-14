# 用代码对比就一目了然

核心区别在于: **要不要一个"独立运行的数据库服务进程"**. 我用 Python 连接数据库的代码来对比, 你一看就懂.

## MySQL/PostgreSQL: 需要先启动服务器, 再"连接"过去

**第一步: 得先有一个数据库服务在跑**

```bash
# 你必须先在某台机器上安装并启动数据库服务(守护进程 daemon)
# 比如 PostgreSQL:
sudo systemctl start postgresql     # 启动服务, 它会一直在后台运行

# 服务启动后, 会监听一个网络端口(PostgreSQL 默认 5432, MySQL 默认 3306)
# 你可以用命令确认它真的在跑、在监听端口:
ss -tlnp | grep 5432
```

**第二步: 你的程序通过网络地址 + 账号密码"连接"这个服务**

```python
import psycopg2  # PostgreSQL 的客户端库

# 注意这里连接需要一大堆参数: 主机、端口、账号、密码、库名
# 因为你是在通过网络(哪怕是本机 localhost)去访问一个独立的服务进程
conn = psycopg2.connect(
    host="localhost",   # 数据库服务在哪台机器
    port=5432,          # 服务监听的端口
    user="admin",       # 账号
    password="secret",  # 密码
    dbname="mydb"       # 连接到哪个库
)

cur = conn.cursor()
cur.execute("SELECT * FROM users")
print(cur.fetchall())
conn.close()
```

关键点: 你的 Python 程序是**客户端(Client)**, 数据库服务是**服务端(Server)**. 两个是**独立的进程**, 甚至可以在两台不同的机器上. 它们之间靠**网络协议**通信. 这就是所谓的 **C/S (Client/Server) 架构**.

如果数据库服务没启动, 你的 `connect()` 直接报错:`Connection refused`(连接被拒绝)——因为根本没人在那个端口上应答.

## SQLite3: 没有服务器, 直接"打开一个文件"

```python
import sqlite3  # Python 标准库自带, 装都不用装

# 看这里: 没有 host, 没有 port, 没有 user, 没有 password
# 只有一个"文件路径"! 因为数据库就是这个文件本身
conn = sqlite3.connect("mydata.db")   # 打开(或创建)一个数据库文件

cur = conn.cursor()
cur.execute("SELECT * FROM users")
print(cur.fetchall())
conn.close()
```

关键点: 这里根本**没有"服务进程"这个东西**. `sqlite3` 这个库的代码, 在你调用它的时候, 直接**在你自己的 Python 进程内部**运行, 直接去读写 `mydata.db` 这个文件. 数据库引擎和你的程序是**同一个进程**, 没有网络, 没有连接握手.

## 一张图理解"进程"层面的差别

**MySQL/PostgreSQL (C/S 架构):**

```
┌──────────────────┐        Network       ┌──────────────────────────┐
│ Your Python App  │  ←──────────────→    │ Database Server Process  │
│ (Client Process) │   TCP: 5432 / 3306   │ (standalone; handles     │
│                  │                      │  disk read/write)        │
└──────────────────┘                      └──────────────────────────┘
    Process A                                      Process B
```

**SQLite3 (嵌入式):**

```
┌──────────────────────────────────────┐
│           Your Python App            │
│  ┌─────────────────────────────────┐ │
│  │ sqlite3 library                 │─┼──→  mydata.db (disk file)
│  │ (code embedded in your process) │ │
│  └─────────────────────────────────┘ │
└──────────────────────────────────────┘
          Just one Process A
```

## 用一个生活化的比喻

- **MySQL/PostgreSQL 像"去银行办业务"**: 银行(数据库服务)得先开门营业(启动服务), 你(程序)得走过去、报账号密码(连接认证), 隔着柜台(网络)让柜员帮你存取钱. 好处是柜台能同时应付很多人(高并发), 数据统一由银行管理.

- **SQLite3 像"自己家里的保险箱"**: 没有营业时间, 没有柜员, 你直接走过去打开箱子(打开文件)拿东西. 快 / 简单 / 零门槛, 但一次基本上只适合你一个人操作(写操作串行).

## 回到你的项目, 这个差别意味着什么

这正好解释了为什么 ROS2 bag 选 SQLite3 而不是 PostgreSQL:

- 机器人采集数据是在**本地单机**上录制, 录完就是一个 `.db3` 文件, 拷走就能带走整份数据. 如果用 PostgreSQL, 你还得在采集机上装个数据库服务 / 配好账号——对一个"录数据"的场景太重了.
- 采集是**单进程写入**, 不需要"多客户端并发访问"这种服务端能力, SQLite 的嵌入式模式刚好够用又轻便.

反过来, 你项目里的 **MongoDB** 就是 C/S 架构(需要启动 mongod 服务 / 通过连接串访问). 为什么它要用服务端模式? 因为它承担的是**全局的、要被多个使用者/服务并发检索的元信息索引**——这种"多方共享、并发查询"的场景, 就必须要服务端架构了.

这一对比本身就是个很好的面试素材: **同一个项目里, 本地单机顺序写用嵌入式(SQLite/bag), 全局共享并发查用服务端(MongoDB), 存原始大文件用对象存储(MinIO)——三种存储各司其职**, 能体现你对存储选型的判断力.

需要的话, 我可以接着演示: 用 Python 的 `sqlite3` 直接打开一个 ROS2 bag 的 `.db3` 文件, 把里面的消息读出来. 那个例子能把"数据库就是个文件"这件事讲得更实.