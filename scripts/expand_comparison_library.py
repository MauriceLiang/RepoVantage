"""Add curated, comparable public GitHub repositories to the personal library."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from backend.app.core.clock import parse_github_datetime, utc_now
from backend.app.integrations.github.client import GitHubClient
from backend.app.persistence.db import SessionLocal
from backend.app.persistence.models import (
    Dataset,
    DatasetRepository,
    CollectionTask,
    Repository,
    RepositoryGroup,
    RepositoryGroupMember,
)
from backend.app.services.repositories import (
    LIBRARY_ID,
    make_task,
    repository_from_github,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "data/manifests/comparison-library-expansion-v1.json"
CLI_TOOLS_GROUP = "D1. 命令行文本与文件工具"
CLI_TOOLS_EXISTING = ("BurntSushi/ripgrep", "sharkdp/bat", "sharkdp/fd")

# Two new projects per existing category gives each of the 11 groups five choices.
# The added CLI-tools group also receives five members after two new projects.
CANDIDATES: tuple[tuple[str, str, int, str], ...] = (
    ("A1. Java 后端框架", "spring-projects/spring-framework", 1148753, "Java 应用基础框架"),
    ("A1. Java 后端框架", "dropwizard/dropwizard", 1272129, "Java REST 服务框架"),
    ("A2. Python Web 框架", "sanic-org/sanic", 59720190, "异步 Python Web 框架"),
    ("A2. Python Web 框架", "litestar-org/litestar", 435625572, "Python API 与 Web 框架"),
    ("A3. Go Web 框架", "go-chi/chi", 44344606, "Go HTTP 路由与 Web 框架"),
    ("A3. Go Web 框架", "zeromicro/go-zero", 285864199, "Go 微服务与 Web 框架"),
    ("A4. 前端 UI 框架", "angular/angular", 24195339, "前端应用框架"),
    ("A4. 前端 UI 框架", "solidjs/solid", 130884470, "响应式前端 UI 框架"),
    ("B1. AI Agent / 多智能体项目", "langchain-ai/langchain", 552661142, "大语言模型应用与 Agent 框架"),
    ("B1. AI Agent / 多智能体项目", "crewAIInc/crewAI", 710601088, "多智能体协作框架"),
    ("B2. 工作流自动化平台", "node-red/node-red", 12618379, "可视化事件流与自动化平台"),
    ("B2. 工作流自动化平台", "apache/airflow", 33884891, "工作流编排与调度平台"),
    ("B3. 日志、搜索与可观测性", "prometheus/prometheus", 6838921, "监控与时序数据平台"),
    ("B3. 日志、搜索与可观测性", "grafana/grafana", 15111821, "可观测性与数据可视化平台"),
    ("B4. 基础设施即代码（IaC）", "ansible/ansible", 3638964, "自动化配置管理与基础设施编排"),
    ("B4. 基础设施即代码（IaC）", "crossplane/crossplane", 147886080, "云基础设施控制平面"),
    ("C1. 代码编辑器 / IDE", "neovim/neovim", 16408992, "可扩展代码编辑器"),
    ("C1. 代码编辑器 / IDE", "helix-editor/helix", 268424739, "终端代码编辑器"),
    ("C2. 前端构建工具", "evanw/esbuild", 61137153, "JavaScript 与 CSS 构建工具"),
    ("C2. 前端构建工具", "rollup/rollup", 35640229, "JavaScript 模块打包工具"),
    ("C3. 终端与 SSH 客户端", "wezterm/wezterm", 120568143, "终端模拟器与 SSH 客户端"),
    ("C3. 终端与 SSH 客户端", "alacritty/alacritty", 51980455, "GPU 加速终端模拟器"),
    (CLI_TOOLS_GROUP, "dandavison/delta", 193526915, "Git 差异查看命令行工具"),
    (CLI_TOOLS_GROUP, "eza-community/eza", 671832156, "现代文件列表命令行工具"),
)


def _write_manifest(value: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{MANIFEST_PATH.name}.", dir=MANIFEST_PATH.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, MANIFEST_PATH)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _fetch_profiles() -> list[dict]:
    fetched = []
    with GitHubClient() as github:
        for group_name, full_name, expected_id, rationale in CANDIDATES:
            payload, _status, _etag = github.get_repository(full_name)
            if not isinstance(payload, dict):
                raise RuntimeError(f"GitHub returned no repository profile: {full_name}")
            if payload.get("id") != expected_id:
                raise RuntimeError(f"GitHub repository identity changed for {full_name}: {payload.get('id')}")
            if payload.get("private") is not False or payload.get("archived") is not False or payload.get("fork") is not False:
                raise RuntimeError(f"Candidate is not an active public upstream repository: {full_name}")
            if payload.get("full_name", "").casefold() != full_name.casefold():
                raise RuntimeError(f"GitHub resolved {full_name} to a different repository")
            pushed_at = parse_github_datetime(payload.get("pushed_at"))
            if pushed_at is None or pushed_at < utc_now() - timedelta(days=365):
                raise RuntimeError(f"Candidate has no recent push within the last year: {full_name}")
            fetched.append({
                "group": group_name,
                "full_name": full_name,
                "expected_repository_id": expected_id,
                "rationale": rationale,
                "payload": payload,
            })
    return fetched


def expand_library(*, queue_collection: bool) -> dict:
    fetched = _fetch_profiles()
    now = utc_now()
    created_groups = []
    queued_tasks = []
    inserted = []

    with SessionLocal() as session:
        library = session.get(Dataset, LIBRARY_ID)
        if library is None:
            raise RuntimeError(f"Missing personal library dataset: {LIBRARY_ID}")

        groups = {group.name: group for group in session.scalars(select(RepositoryGroup)).all()}
        group_names = sorted({candidate[0] for candidate in CANDIDATES})
        for name in group_names:
            if name not in groups:
                group = RepositoryGroup(name=name)
                session.add(group)
                session.flush()
                groups[name] = group
                created_groups.append(name)

        # These three existing repositories are a closer match to each other than
        # to terminal emulator / SSH-client projects.
        cli_existing_rows = session.scalars(
            select(Repository).where(Repository.full_name.in_(CLI_TOOLS_EXISTING))
        ).all()
        if {repo.full_name for repo in cli_existing_rows} != set(CLI_TOOLS_EXISTING):
            raise RuntimeError("Expected existing CLI-tool repositories were not found in the database")
        for repo in cli_existing_rows:
            membership = session.get(DatasetRepository, (LIBRARY_ID, repo.repository_id))
            if membership is None:
                raise RuntimeError(f"Existing CLI tool is not in the personal library: {repo.full_name}")
            if membership.selection_source is not None:
                membership.selection_source = None
                membership.added_at = now
            existing = session.get(RepositoryGroupMember, (groups[CLI_TOOLS_GROUP].id, repo.repository_id))
            if existing is None:
                session.add(RepositoryGroupMember(
                    group_id=groups[CLI_TOOLS_GROUP].id,
                    repository_id=repo.repository_id,
                    dataset_id=LIBRARY_ID,
                ))

        for item in fetched:
            payload = item["payload"]
            repo = repository_from_github(session, payload)
            session.flush()
            membership = session.get(DatasetRepository, (LIBRARY_ID, repo.repository_id))
            if membership is None:
                membership = DatasetRepository(dataset_id=LIBRARY_ID, repository_id=repo.repository_id)
                session.add(membership)
            elif membership.selection_source is not None:
                membership.selection_source = None
                membership.added_at = now
            session.flush()

            group = groups[item["group"]]
            assignments = session.scalars(select(RepositoryGroupMember).where(
                RepositoryGroupMember.dataset_id == LIBRARY_ID,
                RepositoryGroupMember.repository_id == repo.repository_id,
            )).all()
            other_groups = [member for member in assignments if member.group_id != group.id]
            if other_groups:
                names = [session.get(RepositoryGroup, member.group_id).name for member in other_groups]
                raise RuntimeError(f"Candidate already belongs to a different group: {repo.full_name}: {names}")
            if not any(member.group_id == group.id for member in assignments):
                session.add(RepositoryGroupMember(
                    group_id=group.id,
                    repository_id=repo.repository_id,
                    dataset_id=LIBRARY_ID,
                ))

            candidate_report = {
                "repository_id": repo.repository_id,
                "full_name": repo.full_name,
                "html_url": repo.html_url,
                "description": repo.description,
                "language": repo.language,
                "topics": payload.get("topics", []),
                "stars": payload.get("stargazers_count"),
                "forks": payload.get("forks_count"),
                "open_issues_count": payload.get("open_issues_count"),
                "created_at": payload.get("created_at"),
                "pushed_at": payload.get("pushed_at"),
                "archived": payload.get("archived"),
                "is_fork": payload.get("fork"),
                "group": item["group"],
                "selection_reason": item["rationale"],
                "tasks": [],
            }
            if queue_collection:
                window_task = _ensure_task(session, repo.repository_id, "window", window_days=90)
                maintenance_task = _ensure_task(session, repo.repository_id, "maintenance", lookback_weeks=12)
                for task, purpose in ((window_task, "90d-events"), (maintenance_task, "12w-maintenance")):
                    candidate_report["tasks"].append({"task_id": task.task_id, "purpose": purpose})
                    queued_tasks.append({"repository": repo.full_name, "task_id": task.task_id, "purpose": purpose})
            inserted.append(candidate_report)

        # Include full group membership in the manifest so its curation can be
        # inspected without opening the local SQLite database.
        session.flush()
        group_manifest = []
        for name in group_names:
            group = groups[name]
            members = session.scalars(
                select(Repository.full_name)
                .join(RepositoryGroupMember, RepositoryGroupMember.repository_id == Repository.repository_id)
                .where(RepositoryGroupMember.group_id == group.id, RepositoryGroupMember.dataset_id == LIBRARY_ID)
                .order_by(Repository.full_name)
            ).all()
            group_manifest.append({"name": name, "repository_count": len(members), "repositories": members})

        session.commit()

    manifest = {
        "schema_version": 1,
        "manifest_id": "comparison-library-expansion-v1",
        "captured_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "dataset_id": LIBRARY_ID,
        "selection_policy": {
            "public_only": True,
            "exclude_archived": True,
            "exclude_forks": True,
            "matching": "按同类用途分组；每组补充两个项目，支持 2–5 个仓库横向比较。",
            "activity_window_days": 90,
            "maintenance_window_weeks": 12,
            "event_page_cap_per_module": 15,
            "fixed_ml_research_datasets_modified": False,
        },
        "new_repository_count": len(inserted),
        "new_repositories": inserted,
        "groups": group_manifest,
        "created_groups": created_groups,
        "queued_task_count": len(queued_tasks),
        "queued_tasks": queued_tasks,
        "collection_note": "事件覆盖状态由采集任务逐模块记录；达到页数上限或接口限制时保留为 partial，不将缺失当作零。",
    }
    _write_manifest(manifest)
    return manifest


def _ensure_task(session, repository_id: int, scope_kind: str, *, window_days: int | None = None,
                 lookback_weeks: int | None = None) -> CollectionTask:
    recent_cutoff = utc_now() - timedelta(days=7)
    previous = session.scalar(
        select(CollectionTask)
        .where(
            CollectionTask.repository_id == repository_id,
            CollectionTask.depth == "deep",
            CollectionTask.scope_kind == scope_kind,
            CollectionTask.created_at >= recent_cutoff,
        )
        .order_by(CollectionTask.created_at.desc())
    )
    if previous is not None and previous.status in {"queued", "running", "succeeded", "partial"}:
        return previous
    if scope_kind == "window":
        return make_task(session, repository_id, "deep", scope_kind=scope_kind,
                         window_days=window_days or 90, progress_motion="forward")
    return make_task(
        session,
        repository_id,
        "deep",
        scope_kind=scope_kind,
        scope_json=json.dumps({"lookback_weeks": lookback_weeks or 12}, separators=(",", ":")),
        progress_motion="forward",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-queue", action="store_true", help="只更新仓库资料和分组，不创建采集任务")
    args = parser.parse_args()
    result = expand_library(queue_collection=not args.no_queue)
    print(json.dumps({
        "manifest": str(MANIFEST_PATH),
        "added_or_refreshed_repositories": result["new_repository_count"],
        "group_count": len(result["groups"]),
        "group_sizes": {group["name"]: group["repository_count"] for group in result["groups"]},
        "queued_task_count": result["queued_task_count"],
        "created_groups": result["created_groups"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
