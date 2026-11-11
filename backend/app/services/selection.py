"""同类候选的显式约束和加权比较；不生成机器学习结论。"""
import hashlib
import hmac
import json
import uuid

from sqlalchemy import select

from backend.app.core.clock import iso_z, parse_github_datetime
from backend.app.core.exceptions import AppError
from backend.app.analytics.course_ml_features import recent_commit_change
from backend.app.persistence.models import MaintenanceRun, Repository, RepositoryActivityEvent, RepositoryInsightRun, SelectionFeedback
from backend.app.services.insight_comparison import compare_insights


CRITERIA = {
    "commits_weekly_mean": ("commits", "commit", "event_at", "higher"),
    "issue_median_hours": ("issues", "issue", "closed_at", "lower"),
    "pr_median_hours": ("pulls", "pull_request", "merged_at", "lower"),
    "release_interval_days": ("releases", "release", "published_at", "lower"),
}


def selection_signature(body, result):
    payload = {"selection": body.model_dump(), "result": result}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _feedback_entry(record):
    snapshot = json.loads(record.snapshot_json)
    return {"feedback_id": record.feedback_id, "scenario": snapshot["selection"]["scenario"],
            "candidate_group": snapshot["selection"]["candidate_group"],
            "chosen_repository_id": snapshot["chosen_repository_id"], "chosen_repository_name": snapshot["chosen_repository_name"],
            "choice_kind": snapshot["choice_kind"], "reason": snapshot["reason"],
            "created_at": iso_z(record.created_at), "review_status": "pending"}


def create_feedback(session, body):
    result = selection_report(session, body.selection)
    if not hmac.compare_digest(selection_signature(body.selection, result), body.result_signature):
        raise AppError(409, "SELECTION_CHANGED", "比较依据已改变，请重新生成比较后再提交反馈")
    chosen = next((row for row in result["ranking"] if row["repository_id"] == body.chosen_repository_id), None)
    if result["status"] != "available" or chosen is None:
        raise AppError(409, "SELECTION_UNAVAILABLE", "只能对本次可比较的候选提交反馈")
    snapshot = {"selection": body.selection.model_dump(), "result": result, "result_signature": body.result_signature,
                "chosen_repository_id": body.chosen_repository_id, "chosen_repository_name": chosen["full_name"],
                "choice_kind": body.choice_kind, "reason": body.reason.strip(), "consent": "local-research-v1"}
    record = SelectionFeedback(feedback_id=str(uuid.uuid4()), snapshot_json=json.dumps(snapshot, ensure_ascii=False, allow_nan=False))
    session.add(record)
    session.commit()
    return _feedback_entry(record)


def list_feedback(session):
    records = session.scalars(select(SelectionFeedback).order_by(SelectionFeedback.created_at.desc(), SelectionFeedback.feedback_id.desc())).all()
    return [_feedback_entry(record) for record in records]


def delete_feedback(session, feedback_id):
    record = session.get(SelectionFeedback, feedback_id)
    if record is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "反馈不存在")
    session.delete(record)
    session.commit()


def _covered(session, run, metric, module, event_type, time_field):
    if metric.get("source_kind") in {"course_research_historical_snapshot", "maintenance_weekly_aggregation"}:
        maintenance_run = session.get(MaintenanceRun, metric.get("source_run_id"))
        return (module == "commits" and maintenance_run is not None and maintenance_run.status == "complete"
                and metric.get("quality") == "ready" and metric.get("value") is not None
                and metric.get("valid_samples", 0) > 0
                and metric.get("window_start") is not None and metric.get("window_end") is not None)
    if not run or not metric.get("comparable") or metric.get("value") is None:
        return False
    if module in {"issues", "pulls"} and metric.get("valid_samples", 0) < 10:
        return False
    lower, upper = (parse_github_datetime(metric.get(key)) for key in ("window_start", "window_end"))
    if not lower or not upper or lower >= upper:
        return False
    try:
        sources = json.loads(run.module_coverage_json)
    except (TypeError, ValueError) as exc:
        raise AppError(503, "INSIGHT_RUN_UNAVAILABLE", "分析运行的来源信息无法读取，请重新采集仓库数据") from exc
    source = sources.get(module) if isinstance(sources, dict) else None
    if not isinstance(source, dict) or source.get("coverage") != "complete":
        return False
    if source.get("limit_reached") or source.get("rejected_records", 0) or source.get("invalid_event_times", 0):
        return False
    interval = source.get("requested_interval")
    if interval is None:
        covered = run.window_start <= lower and upper <= run.window_end
    elif isinstance(interval, list) and len(interval) == 2 and all(isinstance(value, str) for value in interval):
        start, end = (parse_github_datetime(value) for value in interval)
        covered = start is not None and end is not None and start <= lower and upper <= end
    else:
        covered = False
    if not covered:
        return False
    column = getattr(RepositoryActivityEvent, time_field)
    updated_later = session.scalar(select(RepositoryActivityEvent.id).where(
        RepositoryActivityEvent.repository_id == run.repository_id,
        RepositoryActivityEvent.event_type == event_type,
        column >= lower, column < upper,
        RepositoryActivityEvent.last_seen_at > run.analyzed_at,
    ).limit(1))
    return updated_later is None


def selection_report(session, body):
    comparison = compare_insights(session, body.repository_ids, "same_period", body.window_days)
    from backend.app.services.maintenance import maintenance_observation
    maintenance_rows = []
    for row in comparison['repositories']:
        observation = maintenance_observation(session, row['repository_id'])
        maintenance_rows.append({'repository_id': row['repository_id'], 'full_name': row['full_name'],
                                 'sample_role': row.get('sample_role'),
                                 'course_snapshot': row.get('source_kind') == 'course_research_historical_snapshot',
                                 'pattern': observation['maintenance_pattern'],
                                 'recent_activity_change': recent_commit_change(observation['weeks']),
                                 'activity_trend': observation['activity_trend'],
                                 'activity_anomaly': observation['activity_anomaly']})
    available_windows = {(row['pattern']['history_start'], row['pattern']['as_of_utc']) for row in maintenance_rows
                         if row['pattern']['status'] in {'available', 'unclassified'} and row['pattern']['evidence']}
    valid_count = sum(row['pattern']['status'] in {'available', 'unclassified'} and bool(row['pattern']['evidence']) for row in maintenance_rows)
    common_window = None
    if valid_count >= 2 and len(available_windows) == 1:
        start, end = next(iter(available_windows))
        common_window = {'start': start, 'end': end}
    raw_weights = {name: value for name, value in body.weights.model_dump().items() if value > 0}
    total = sum(raw_weights.values())
    weights = {name: value / total for name, value in raw_weights.items()}
    result = {"status": "insufficient_data", "method": "rule_based", "scenario": body.scenario,
              "candidate_group": body.candidate_group, "comparison_basis": comparison["comparison_basis"],
              "weights": weights, "ranking": [], "excluded": [], "sensitivity": [],
              "maintenance": {'common_window': common_window, 'data_as_of': comparison.get('course_snapshot_as_of'), 'repositories': maintenance_rows},
              "notes": ["只比较使用者确认用途相近的候选；规则排序不是采用成功概率。",
                        "缺失、不满足硬约束或覆盖不足的候选不参与评分。",
                        "归一化分数随候选集合与权重变化；Release 使用单独的 365 天窗口。",
                        f"历史指标口径：{comparison['metric_version']}；ML 结果只作维护行为证据，不参与排序。"]}
    if comparison["comparison_basis"]["status"] != "comparable":
        result["notes"].append(comparison["comparison_basis"].get("reason") or "没有可比较的共同时间范围。")
        return result
    eligible = []
    languages = {value.casefold() for value in body.allowed_languages}
    licenses = {value.casefold() for value in body.allowed_licenses}
    for row in comparison["repositories"]:
        repository = session.get(Repository, row["repository_id"])
        run = session.get(RepositoryInsightRun, row["run_id"]) if row["run_id"] else None
        reasons = []
        if languages and (not repository.language or repository.language.casefold() not in languages):
            reasons.append("语言不满足约束或未知")
        if licenses and (not repository.license_spdx or repository.license_spdx.casefold() not in licenses):
            reasons.append("许可证不满足约束或未知")
        for metric_name in weights:
            module, event_type, time_field, _ = CRITERIA[metric_name]
            if not _covered(session, run, row["metrics"][metric_name], module, event_type, time_field):
                reasons.append(f"{metric_name} 覆盖不足或有效样本不足")
        if reasons:
            result["excluded"].append({"repository_id": repository.repository_id, "full_name": repository.full_name, "reasons": reasons})
        else:
            eligible.append((repository, run, row))
    if len(eligible) < 2:
        result["notes"].append("满足约束且数据可比的仓库不足两个。")
        return result
    bounds = {key: (min(row["metrics"][key]["value"] for _, _, row in eligible),
                    max(row["metrics"][key]["value"] for _, _, row in eligible)) for key in weights}
    for repository, run, row in eligible:
        evidence = {}
        for key, weight in weights.items():
            metric = row["metrics"][key]
            low, high = bounds[key]
            normalized = 0.5 if low == high else (metric["value"] - low) / (high - low)
            if CRITERIA[key][3] == "lower":
                normalized = 1 - normalized
            evidence[key] = {"value": metric["value"], "unit": metric["unit"], "normalized": normalized, "weight": weight,
                             "contribution": normalized * weight, "valid_samples": metric["valid_samples"],
                             "window_start": metric["window_start"], "window_end": metric["window_end"],
                             "source_run_id": metric.get("source_run_id") or (run.run_id if run else None),
                             "source_kind": metric.get("source_kind") or "online_event_analysis"}
        result["ranking"].append({"repository_id": repository.repository_id, "full_name": repository.full_name,
                                  "language": repository.language, "license_spdx": repository.license_spdx,
                                  "score": sum(item["contribution"] for item in evidence.values()), "evidence": evidence})
    result["ranking"].sort(key=lambda row: (-row["score"], row["full_name"].casefold()))
    for criterion in weights:
        changed = {key: value * (1.25 if key == criterion else 1.0) for key, value in raw_weights.items()}
        denominator = sum(changed.values())
        order = sorted(result["ranking"], key=lambda row: (-sum(row["evidence"][key]["normalized"] * value / denominator for key, value in changed.items()), row["full_name"].casefold()))
        result["sensitivity"].append({"criterion": criterion, "weight_multiplier": 1.25, "repository_ids": [row["repository_id"] for row in order]})
    result["status"] = "available"
    return result


def selection_markdown(result):
    def safe(value):
        return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\\", "\\\\").replace("|", "\\|").replace("[", "\\[").replace("]", "\\]").replace("`", "\\`").replace("\r", " ").replace("\n", " ")

    def explain_reason(code):
        labels = {
            "not_collected": "尚未采集维护活动数据",
            "short_history": "最近 8 个完整 UTC 周不足，无法判断实际变化",
            "insufficient_history": "尚无可观察的完整 UTC 周",
            "short_observation_window": "完整观察周不足 12 周",
            "incomplete_commits_coverage": "Commit 覆盖不完整，缺失周不作为零活动",
            "maintenance_page_budget_exceeded": "Commit 采集达到课程版页数预算，覆盖不完整",
            "low_activity_scope": "近期提交活动不足，不提供未来趋势预测",
            "partial_data": "数据覆盖不完整，暂不提供此项结果",
            "insufficient_data": "当前样本不足以生成此项结果",
            "model_unavailable": "模型不可用，只展示近期事实",
            "stale": "维护活动数据已过期",
            "source_integrity_mismatch": "维护活动来源校验不一致",
            "source_archive_unavailable": "维护活动来源归档不可用",
        }
        return labels.get(str(code), str(code or "当前没有足够证据"))

    basis = result["comparison_basis"]
    window = basis.get("shared_window") or {}
    lines = ["# 技术候选比较报告", "", f"- 场景：{safe(result['scenario'])}", f"- 同类候选：{safe(result['candidate_group'])}",
             f"- 方法：可解释规则，不是机器学习预测", f"- 共同观察窗口：{safe(window.get('start', '—'))} 至 {safe(window.get('end', '—'))}",
             f"- 结果状态：{safe(result['status'])}", "", "## 指标权重", ""]
    data_as_of = result['maintenance'].get('data_as_of')
    if data_as_of:
        lines.insert(6, f"- 课程仓库资料快照截至：{safe(data_as_of)}；周活动窗口仍按各指标行标示")
    lines.extend(f"- {safe(name)}：{weight:.3f}" for name, weight in result["weights"].items())
    lines.extend(["", "## 近期维护行为证据", "",
                  "本节分别呈现近期默认分支提交模式（M1）、最近 4 周实际变化（统计事实）、未来 4 周活动趋势预测（M2）、近期活动异常提示（MAD 规则）与数据口径。",
                  "M1 只描述采集时默认分支最近 12 周的 Commit 模式，不包含 PR、Issue 或社区总体活动判断。",
                  "最近 4 周实际变化是完整周 Commit 事实；未来 4 周活动趋势预测是独立的 M2 模型类别。两者不参与规则得分。"])
    for row in result['maintenance']['repositories']:
        pattern = row['pattern']
        evidence = pattern['evidence']
        if evidence:
            label = (pattern.get('display_name') or pattern.get('pattern_name')) if pattern['method'] == 'machine_learning' else '事实画像'
            recent_change = row.get('recent_activity_change') or {}
            trend = row.get('activity_trend') or {}
            anomaly = row.get('activity_anomaly') or {}
            if recent_change.get('status') == 'available':
                actual_change = (f"最近 4 周实际变化（统计事实）：{recent_change['trend']}（{recent_change['recent_4w_commits']} vs "
                                 f"{recent_change['previous_4w_commits']} Commit）；此前窗口 "
                                 f"{recent_change['previous_window_start_utc']} 至 {recent_change['previous_window_end_exclusive_utc']}；"
                                 f"最近窗口 {recent_change['recent_window_start_utc']} 至 {recent_change['recent_window_end_exclusive_utc']}。")
            else:
                actual_change = f"最近 4 周实际变化（统计事实）无法判定：{explain_reason(recent_change.get('reason_code') or recent_change.get('status'))}。"
            if trend.get('method') == 'machine_learning' and trend.get('status') == 'available':
                forecast = (f"未来 4 周活动趋势预测（M2）：{trend.get('trend')}（{trend.get('model_version')}）；预测窗口 "
                            f"{trend.get('evidence', {}).get('forecast_start_utc', '—')} 至 "
                            f"{trend.get('evidence', {}).get('forecast_end_exclusive_utc', '—')}。")
            else:
                forecast = (f"暂不提供未来 4 周活动趋势预测（M2）："
                            f"{explain_reason(trend.get('reason_code') or trend.get('status'))}。")
            anomaly_method = 'MAD 规则' if anomaly.get('method') == 'statistical_baseline' else 'MAD 规则未运行'
            if anomaly.get('method') == 'statistical_baseline' and anomaly.get('suspected'):
                direction = (anomaly.get('weeks') or [{}])[0].get('direction')
                anomaly_result = {'up': '疑似异常增加，待核查', 'down': '疑似异常减少，待核查'}.get(direction, '疑似异常偏离，待核查')
            elif anomaly.get('method') == 'statistical_baseline':
                anomaly_result = '未发现明显异常'
            else:
                anomaly_result = f"暂无法判断：{explain_reason(anomaly.get('reason_code') or anomaly.get('status'))}"
            raw_pr_coverage = pattern.get('coverage', {}).get('pull_requests_created', 'unknown')
            pr_coverage = {'complete': '完整', 'partial': '部分覆盖', 'partial_or_unavailable': '部分覆盖或不可用',
                           'not_collected': '未采集', 'unknown': '未知'}.get(raw_pr_coverage, raw_pr_coverage)
            pr_total = evidence.get('pr_created_total_12w') if raw_pr_coverage == 'complete' else None
            pr_note = (f"同期 PR 创建量为 {pr_total}（覆盖完整）；这不代表仓库没有 PR 或社区协作活动。"
                       if evidence.get('commit_total_12w') == 0 and isinstance(pr_total, int) and pr_total > 0
                       else f"PR 创建覆盖 {safe(pr_coverage)}" + (f"、数量 {pr_total}" if isinstance(pr_total, int) else ''))
            if evidence.get('commit_coverage') == 'partial':
                commit_fact = (f"Commit 覆盖不完整：已观察到 {safe(evidence.get('commit_observed_partial_lower_bound', 0))} 次（下限，"
                               f"{safe(evidence.get('commit_partial_weeks', 0))} 周覆盖不完整）；"
                               f"完整周事实 {safe(evidence.get('commits_in_complete_weeks', 0))} 次 / "
                               f"{safe(evidence.get('commit_complete_weeks', 0))} 周。")
            else:
                total = evidence.get('commit_total_12w', evidence.get('commit_total_window', '—'))
                active = evidence.get('commit_active_weeks_12w')
                complete_weeks = evidence.get('window_weeks', evidence.get('commit_observed_weeks', '—'))
                commit_period = '最近 12 周默认分支 Commit' if 'commit_total_12w' in evidence else '已观察完整周默认分支 Commit'
                active_fact = (f"活跃周 {active}/12；" if isinstance(active, int)
                               else f"完整周 {complete_weeks} 周；")
                commit_fact = f"{commit_period} {safe(total)}；{active_fact}"
            if evidence.get('commit_page_budget') is not None:
                commit_fact += (f"页数 {safe(evidence.get('commit_pages_fetched', '—'))}/"
                                f"{safe(evidence['commit_page_budget'])}、估算 GitHub 请求 "
                                f"{safe(evidence.get('github_request_estimate', '—'))} 次（不含传输重试）；")
            sample_label = {'train': '课程实验角色为训练组', 'test': '课程实验角色为测试组留出仓库'}.get(row.get('sample_role'))
            sample_note = f"课程研究数据：{sample_label}；" if sample_label else ''
            lines.append(f"- {safe(row['full_name'])}：{sample_note}近期默认分支提交模式（M1）{safe(label)}；"
                         f"{commit_fact}"
                         f"{safe(pr_note)}。{safe(actual_change)} {safe(forecast)}"
                         f"近期活动异常提示（{safe(anomaly_method)}）：{safe(anomaly_result)}；"
                         f"窗口 {safe(pattern.get('history_start') or '—')} — {safe(pattern.get('as_of_utc') or '—')}；来源 {safe(pattern.get('source_run_id') or '—')}。")
        else:
            recent_change = row.get('recent_activity_change') or {}
            trend = row.get('activity_trend') or {}
            pattern_reason = explain_reason(pattern.get('reason_code'))
            actual_reason = explain_reason(recent_change.get('reason_code') or recent_change.get('status'))
            forecast_reason = explain_reason(trend.get('reason_code') or trend.get('status'))
            lines.append(f"- {safe(row['full_name'])}：近期默认分支提交模式（M1）不可用：{safe(pattern_reason)}；"
                         f"最近 4 周实际变化（统计事实）无法判定：{safe(actual_reason)}；"
                         f"暂不提供未来 4 周活动趋势预测（M2）：{safe(forecast_reason)}。")
    lines.extend(["", "## 比较结果", ""])
    for index, row in enumerate(result["ranking"], 1):
        lines.extend([f"### {index}. {safe(row['full_name'])}", "", f"规则得分：{row['score']:.3f}；语言：{safe(row['language'] or '未知')}；许可证：{safe(row['license_spdx'] or '未知')}。", "",
                      "| 指标 | 观察值 | 贡献 | 有效样本 | 窗口 | 来源运行 |", "|---|---:|---:|---:|---|---|"])
        for name, evidence in row["evidence"].items():
            source_label = '课程研究历史快照' if evidence.get('source_kind') == 'course_research_historical_snapshot' else '在线事件分析'
            lines.append(f"| {safe(name)} | {evidence['value']:.3f} {safe(evidence['unit'])} | {evidence['contribution']:.3f} | {evidence['valid_samples']} 周 | {safe(evidence['window_start'])} — {safe(evidence['window_end'])} | {safe(source_label)} · {safe(evidence['source_run_id'] or '—')} |")
        lines.append("")
    if not result["ranking"]:
        lines.extend(["当前没有足够可比较的候选。", ""])
    if result["excluded"]:
        lines.extend(["## 未参与评分", ""])
        lines.extend(f"- {safe(row['full_name'])}：{safe('；'.join(row['reasons']))}" for row in result["excluded"])
        lines.append("")
    if result["sensitivity"]:
        names = {row["repository_id"]: row["full_name"] for row in result["ranking"]}
        lines.extend(["## 权重敏感性", ""])
        for item in result["sensitivity"]:
            order = " → ".join(safe(names[repository_id]) for repository_id in item["repository_ids"])
            lines.append(f"- {safe(item['criterion'])} 权重增加 25%：{order}")
        lines.append("")
    lines.extend(["## 数据口径与适用性说明", "",
                  "M1 与 M2 依据最近 12 个完整 UTC 周的默认分支 Commit；扩展到 24 周只增加事实背景，不改变模型窗口。",
                  "PR 创建覆盖独立展示；MAD 是统计规则提示，不是经标签验证的机器学习异常模型。未采集、覆盖不完整或样本不足时不将缺失周视作零。",
                  "", "## 技术选型辅助结论（规则与证据分别说明）", ""])
    if result["ranking"]:
        first = result["ranking"][0]
        lines.append(f"在当前场景、候选范围、硬约束和指标权重下，规则排序优先列出 {safe(first['full_name'])}（规则得分 {first['score']:.3f}）。")
        if first["evidence"]:
            reasons = "；".join(
                f"{safe(name)} {evidence['value']:.3f} {safe(evidence['unit'])}"
                for name, evidence in first["evidence"].items()
            )
            lines.append(f"该排序依据当前纳入评分的指标事实：{reasons}。")
    else:
        lines.append("当前没有足够可比较的候选，不能形成规则排序或技术选型方向。")
    lines.append("M1、M2 与 M3 只作为近期维护行为证据，不参与规则排名；本报告不表示功能适配、代码质量或采用成功率，仍需结合具体需求和许可证判断。")
    lines.append("")
    lines.extend(["## 限制", ""])
    lines.extend(f"- {safe(note)}" for note in result["notes"])
    return "\n".join(lines) + "\n"
