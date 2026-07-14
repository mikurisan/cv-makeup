[Flink](./a.md) + StarRocks 实时统一数仓架构

- 多源数据实时入仓设计: 库表 Flink CDC, API 自定义 SourceFunction 轮询, 文件 FileSource 批处理, checkpoint 端到端可重放

- 主导 DWD/DWS/ADS 分层维度模型重构, Aggregate Key + 物化视图预计算核心
  指标, 高频查询 P99 从 5s 降至 1s

- 设计 QueryGateway 查询服务: 连接池动态扩缩 + 结果缓存 + 限流 + RBAC, 
  支撑日均 100W+ 次调用, 可用性 99.9%