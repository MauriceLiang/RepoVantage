from fastapi import APIRouter, Request

from backend.app.api.helpers import envelope
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.settings import GitHubTokenRequest, GitHubTokenStatusResponse
from backend.app.services.github_token_settings import delete_github_token, get_github_token_status, save_github_token


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/github-token", response_model=SuccessEnvelope[GitHubTokenStatusResponse])
def get_github_token_settings(request: Request):
    return envelope(request, get_github_token_status())


@router.post("/github-token", response_model=SuccessEnvelope[GitHubTokenStatusResponse])
def update_github_token(payload: GitHubTokenRequest, request: Request):
    return envelope(request, save_github_token(payload.token))


@router.delete("/github-token", response_model=SuccessEnvelope[GitHubTokenStatusResponse])
def remove_github_token(request: Request):
    return envelope(request, delete_github_token())
