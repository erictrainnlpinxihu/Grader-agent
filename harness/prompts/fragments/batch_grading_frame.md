批量批改框架：按 shard_size=20 切片，M1 单线程串行 + checkpoint 断点续批。每个分片独立初批，lead 横向校准只建议 ±1 分。连续 3 个分片失败整批 paused。
