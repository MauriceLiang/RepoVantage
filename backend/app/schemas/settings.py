from pydantic import Field

from backend.app.schemas.common import DTO


class GitHubTokenRequest(DTO):
    token: str = Field(min_length=1, max_length=500)


class GitHubTokenStatusResponse(DTO):
    configured: bool
    managed_by_environment: bool = False
