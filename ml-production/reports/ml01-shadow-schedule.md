# ML-01 前瞻影子任务安装记录

- 原始冻结预测、名单、协议、模型及 40 个完整起点快照的哈希已由 `scripts/ml01_shadow_outcome.py` 在每次运行前核验；原先 5 个 `coverage_uncertain` 仓库不进入采集或评分。
- 已安装本机用户 LaunchAgent：`~/Library/LaunchAgents/com.repovantage.ml01-shadow-20261207.plist`，服务名 `com.repovantage.ml01-shadow-20261207`。`launchctl print` 显示日历触发器为本机时间 **12 月 7 日 22:06**，加载后已执行一次并输出 `armed: target_end=2026-12-07T14:08:00+00:00`；加载退出码为 0。当前机器时区为 Asia/Shanghai；若届时更改系统时区，launchd 的本地日历时间会随之改变。
- 已冻结采集程序、GitHub 客户端、依赖锁与 Python 版本，见 `ml-production/scheduling/task_lock.json`；冻结后重新触发启动检查，日志再次显示 `armed`，`launchctl print` 显示 `runs=2`、`last exit code=0`、日历事件 `watching=1`。今后修改锁定文件需先审查并更新锁，不能静默更换影子实验口径。
- 同一程序已通过独立、一次性的用户 LaunchAgent 演练：2026-11-09 14:47:21 UTC 成功校验冻结输入并只读取得一个真实仓库的默认分支 SHA，进程退出码 0，未创建未来标签。证据：`ml-production/scheduling/rehearsal/rehearsal.json`。演练服务已卸载。
- 到期运行将先记录目标结束前后的分支 SHA，再检查与冻结起点的可见祖先关系和分页结果，逐仓库原子保存检查点。它只记录“结束时可见 SHA 上的 Commit 时间戳”，不声称能精确证明进入分支的时刻；缺失边界、分支更名、非祖先、分页不完整等均为未知。即使前后 SHA 一致，也不能排除未观察到的瞬时强推和恢复，因此自动输出仍为 `coverage_uncertain`，不得自动评分或发布。
- 失败写入 `dataprepare/MachineLearn/run/ml01-shadow-outcome-v3/last_failure.json`，尝试发送本机通知；launchd 对非零退出最多以 300 秒间隔重试，程序限制三次，到期仍失败需人工补救。日志在 `ml-production/scheduling/logs/ml01-shadow.{stdout,stderr}.log`。捕获完毕后以 `completed.json` 防止重复写入；启动前的 `run.lock` 防止并发。
- **条件和未验证项：**需要届时该用户登录会话、机器可运行、网络和 GitHub 凭据可用，且项目路径和虚拟环境保持可访问。休眠、关机、离线或启动延迟都可能错过边界，届时只记录真实延迟和未知状态，不补造标签。尚未实际到达未来时点，未来采集、标签和模型效果均未验证。macOS 的日历作业按月/日重复；完成后应由维护者卸载，避免次年重复触发。

查看任务：

```bash
launchctl print gui/$(id -u)/com.repovantage.ml01-shadow-20261207
```

完成后卸载（不会删除研究结果）：

```bash
launchctl bootout gui/$(id -u)/com.repovantage.ml01-shadow-20261207
rm ~/Library/LaunchAgents/com.repovantage.ml01-shadow-20261207.plist
```

若发生失败，先保存日志与 `last_failure.json`；在不覆盖已有检查点的情况下重新运行 `python -m scripts.ml01_shadow_outcome`。任何补采晚于目标边界都必须按实际证据标记未知，不得将其当作准时快照。
