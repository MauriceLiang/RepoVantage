# 数据质量与验收计划

ready=该指标查询范围与输入足够；partial=分页/异常数据不完整；missing=未采集；failed=端点错误且无记录；insufficient_samples=完整覆盖但样本不足。质量按模块独立，ready不是全历史完整。

每指标返回 metric_key/unit/window/quality.valid_samples/reason；耗时返回excluded_invalid_duration和missing_duration_rate；每run有版本、计算时间、任务、归档、来源与限制。归档失败披露复核能力下降，旧结果不删除。

验证阶段：基线 → 规范化/算法/幂等/安全回放 → 无损迁移副本演练 → Worker/API旧合同 → Vue图表/缺失/partial → 真实冷启动复核 → 390/768/1280/1440截图。详情读持久化结果，不同步解压。

基线：后端55项、前端15项，构建通过。当前原有本地变更仅.DS_Store。隔离分支codex/insights-v1。新功能验收和真实来源记录见04_delivery.md。
