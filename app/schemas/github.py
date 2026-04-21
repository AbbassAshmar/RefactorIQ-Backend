from pydantic import BaseModel


class GithubRepositoryResponse(BaseModel):
    name: str
    owner: str
    full_name: str
    private: bool
    default_branch: str
    html_url: str


class GithubBranchResponse(BaseModel):
    name: str
    commit_sha: str
    protected: bool
