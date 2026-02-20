"""General-purpose GitHub API helpers (beyond OAuth)."""

from __future__ import annotations

import httpx


async def fetch_github_repos(access_token: str) -> list[dict]:
    """Return the list of repositories the authenticated user has access to."""
    repos: list[dict] = []
    url = "https://api.github.com/user/repos"
    params: dict[str, str | int] = {"per_page": 100, "page": 1}

    async with httpx.AsyncClient(timeout=30.0) as client:
        while url:
            resp = await client.get(
                url,
                params=params,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            resp.raise_for_status()
            repos.extend(resp.json())

            # Handle pagination via Link header
            next_link = resp.headers.get("link", "")
            if 'rel="next"' in next_link:
                # Extract the next URL from the Link header
                for part in next_link.split(","):
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip(" <>")
                        params = {}
                        break
            else:
                url = ""

    return repos


async def fetch_repo_branches(
    access_token: str, owner: str, repo: str
) -> list[dict]:
    """Return the branches for a given repository."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/branches",
            params={"per_page": 100},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        resp.raise_for_status()
        return resp.json()
