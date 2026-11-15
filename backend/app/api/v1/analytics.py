from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_session
from backend.app.api.helpers import envelope
from backend.app.schemas.analytics import ComparisonResponse, DataQualityResponse, OverviewResponse, StatisticsResponse
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.ml_evaluation import ModelDecisions, SelectionFeedback, SelectionFeedbackCreate, SelectionRequest, SelectionResult
from backend.app.schemas.repositories import ComparisonRequest, InsightsComparisonRequest
from backend.app.services.analytics import compare_repositories, data_quality, overview, research_statistics


router = APIRouter(tags=["analytics"])


@router.get("/overview", response_model=SuccessEnvelope[OverviewResponse])
def get_overview(request: Request, scope: Literal["research", "library"], dataset_id: str | None = None, language: str | None = None, session: Session = Depends(get_session)):
    return envelope(request, overview(session, scope, dataset_id, language))


@router.get("/research/statistics", response_model=SuccessEnvelope[StatisticsResponse])
def get_research_statistics(
    request: Request,
    dataset_id: str,
    language: str | None = None,
    group_by: Literal["language", "star_tier", "age_tier"] = "language",
    session: Session = Depends(get_session),
):
    return envelope(request, research_statistics(session, dataset_id, language, group_by))


@router.get("/research/data-quality", response_model=SuccessEnvelope[DataQualityResponse])
def get_data_quality(request: Request, dataset_id: str, analysis_mode: Literal["formal", "exploratory", "course"] = "formal", session: Session = Depends(get_session)):
    expected_type = "featured" if analysis_mode == "exploratory" else "research"
    return envelope(request, data_quality(session, dataset_id, expected_type))


@router.get("/research/dashboard")
def get_research_dashboard(request: Request, dataset_id: str = "course-research-300-v1", session: Session = Depends(get_session)):
    from backend.app.services.course_research_dataset import course_research_dashboard
    return envelope(request, course_research_dashboard(session, dataset_id))


@router.get("/research/atlas")
def get_research_atlas(request: Request, dataset_id: str = "course-research-300-v1", session: Session = Depends(get_session)):
    from backend.app.services.course_research_dataset import course_research_atlas
    return envelope(request, course_research_atlas(session, dataset_id))


@router.get("/selection/scenarios")
def get_selection_scenarios(request: Request, session: Session = Depends(get_session)):
    from backend.app.services.selection_v44 import list_scenarios
    return envelope(request, list_scenarios(session))


@router.get("/selection/references")
def get_selection_references(request: Request, session: Session = Depends(get_session)):
    from backend.app.services.selection_v44 import list_references
    return envelope(request, {"references": list_references(session)})


@router.get("/selection/scenarios/{slug}/viz")
def get_selection_scenario_viz(request: Request, slug: str, session: Session = Depends(get_session)):
    from backend.app.services.selection_v44 import get_scenario_viz
    result = get_scenario_viz(session, slug)
    if result is None:
        from backend.app.core.exceptions import AppError
        raise AppError(404, "RESOURCE_NOT_FOUND", "技术选型场景不存在")
    return envelope(request, result)


@router.get("/selection/scenarios/{slug}/candidates/{repository_id}")
def get_selection_candidate(request: Request, slug: str, repository_id: int, session: Session = Depends(get_session)):
    from backend.app.services.selection_v44 import get_candidate
    result = get_candidate(session, slug, repository_id)
    if result is None:
        from backend.app.core.exceptions import AppError
        raise AppError(404, "RESOURCE_NOT_FOUND", "当前场景中没有该候选仓库")
    return envelope(request, result)


@router.get("/selection/scenarios/{slug}/sensitivity")
def get_selection_sensitivity(request: Request, slug: str, session: Session = Depends(get_session)):
    from backend.app.services.selection_v44 import get_scenario
    scenario = get_scenario(session, slug)
    if scenario is None:
        from backend.app.core.exceptions import AppError
        raise AppError(404, "RESOURCE_NOT_FOUND", "技术选型场景不存在")
    return envelope(request, {"available": False, "reason": "当前快照不生成跨维度综合排名；没有用户明确选择且完整覆盖的权重集合。"})


@router.get("/selection/scenarios/{slug}")
def get_selection_scenario(request: Request, slug: str, session: Session = Depends(get_session)):
    from backend.app.services.selection_v44 import get_scenario
    result = get_scenario(session, slug)
    if result is None:
        from backend.app.core.exceptions import AppError
        raise AppError(404, "RESOURCE_NOT_FOUND", "技术选型场景不存在")
    return envelope(request, result)


@router.post("/comparisons", response_model=SuccessEnvelope[ComparisonResponse])
def compare(request: Request, body: ComparisonRequest, session: Session = Depends(get_session)):
    return envelope(request, compare_repositories(session, body.repository_ids, body.depth))


@router.post("/comparisons/insights")
def compare_activity_insights(request: Request, body: InsightsComparisonRequest, session: Session = Depends(get_session)):
    from backend.app.services.insight_comparison import compare_insights
    return envelope(request, compare_insights(session, body.repository_ids, body.mode, body.window_days))


@router.get("/models/status", response_model=SuccessEnvelope[ModelDecisions])
def get_model_status(request: Request):
    from backend.app.services.ml_evaluation import model_decisions
    return envelope(request, model_decisions())


@router.get("/models/monitoring")
def get_model_monitoring(request: Request):
    from backend.app.services.model_registry import monitoring
    return envelope(request, monitoring())


@router.post("/comparisons/selection", response_model=SuccessEnvelope[SelectionResult])
def compare_selection(request: Request, body: SelectionRequest, session: Session = Depends(get_session)):
    from backend.app.services.selection import selection_markdown, selection_report, selection_signature
    result = selection_report(session, body)
    result["result_signature"] = selection_signature(body, result)
    result["report_markdown"] = selection_markdown(result)
    return envelope(request, result)


@router.post("/reports/selection.md")
def export_selection(body: SelectionRequest, session: Session = Depends(get_session)):
    from backend.app.services.selection import selection_markdown, selection_report
    text = selection_markdown(selection_report(session, body))
    return Response(text, media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="repovantage-selection.md"'})


@router.get("/feedback/selection", response_model=SuccessEnvelope[list[SelectionFeedback]])
def get_selection_feedback(request: Request, session: Session = Depends(get_session)):
    from backend.app.services.selection import list_feedback
    return envelope(request, list_feedback(session))


@router.post("/feedback/selection", response_model=SuccessEnvelope[SelectionFeedback])
def add_selection_feedback(request: Request, body: SelectionFeedbackCreate, session: Session = Depends(get_session)):
    from backend.app.services.selection import create_feedback
    return envelope(request, create_feedback(session, body))


@router.delete("/feedback/selection/{feedback_id}", status_code=204)
def remove_selection_feedback(feedback_id: str, session: Session = Depends(get_session)):
    from backend.app.services.selection import delete_feedback
    delete_feedback(session, feedback_id)
    return Response(status_code=204)


@router.get("/research/insights")
def get_research_insights(request: Request, dataset_id: str, analysis_mode: Literal["formal", "exploratory", "course"] = "formal", session: Session = Depends(get_session)):
    from backend.app.services.insight_comparison import research_insights
    return envelope(request, research_insights(session, dataset_id, analysis_mode))
