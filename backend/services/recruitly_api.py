"""
Recruitly API read helpers for the intelligence backend.

This module provides a narrow, authenticated read layer for the first Recruitly
integration slice. The initial goal is to preview live entity shapes before we
commit to full canonical persistence.
"""

from __future__ import annotations

from typing import Any

import httpx


class RecruitlyApiError(RuntimeError):
    """
    Raised when the backend cannot complete a Recruitly API read safely.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        endpoint_url: str | None = None,
        response_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.endpoint_url = endpoint_url
        self.response_body = response_body

    def __str__(self) -> str:
        return self.message


def fetch_recruitly_candidates_preview(
    *,
    api_base_url: str,
    api_key: str,
    query: str | None = None,
    page: int = 0,
    size: int = 20,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch a bounded Recruitly candidate preview page.
    """

    return _fetch_recruitly_collection_preview(
        api_base_url=api_base_url,
        api_key=api_key,
        resource="candidates",
        query=query,
        page=page,
        size=size,
        timeout_seconds=timeout_seconds,
    )


def fetch_recruitly_companies_preview(
    *,
    api_base_url: str,
    api_key: str,
    query: str | None = None,
    page: int = 0,
    size: int = 20,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch a bounded Recruitly company preview page.
    """

    return _fetch_recruitly_collection_preview(
        api_base_url=api_base_url,
        api_key=api_key,
        resource="companies",
        query=query,
        page=page,
        size=size,
        timeout_seconds=timeout_seconds,
    )


def fetch_recruitly_contacts_preview(
    *,
    api_base_url: str,
    api_key: str,
    query: str | None = None,
    page: int = 0,
    size: int = 20,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch a bounded Recruitly contact preview page.
    """

    return _fetch_recruitly_collection_preview(
        api_base_url=api_base_url,
        api_key=api_key,
        resource="contacts",
        query=query,
        page=page,
        size=size,
        timeout_seconds=timeout_seconds,
    )


def fetch_recruitly_jobs_preview(
    *,
    api_base_url: str,
    api_key: str,
    query: str | None = None,
    page: int = 0,
    size: int = 20,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch a bounded Recruitly job preview page.
    """

    return _fetch_recruitly_collection_preview(
        api_base_url=api_base_url,
        api_key=api_key,
        resource="jobs",
        query=query,
        page=page,
        size=size,
        timeout_seconds=timeout_seconds,
    )


def fetch_recruitly_record_journal_preview(
    *,
    api_base_url: str,
    api_key: str,
    record_type: str,
    record_id: str,
    page: int = 0,
    size: int = 20,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch a bounded Recruitly journal/activity preview for one record.
    """

    normalized_record_type = record_type.strip().lower()
    normalized_record_id = record_id.strip()
    if normalized_record_type == "":
        raise ValueError("Recruitly record type cannot be blank.")
    if normalized_record_id == "":
        raise ValueError("Recruitly record id cannot be blank.")

    payload = _get_recruitly_json(
        api_base_url=api_base_url,
        api_key=api_key,
        endpoint_path=f"/api/{normalized_record_type}/{normalized_record_id}/journal",
        params={
            "page": int(page),
            "size": _clamp_preview_size(size),
        },
        timeout_seconds=timeout_seconds,
    )
    data = payload.get("data")
    rows = data if isinstance(data, list) else []

    return {
        "record_type": normalized_record_type,
        "record_id": normalized_record_id,
        "page": int(page),
        "size": _clamp_preview_size(size),
        "item_count": len(rows),
        "total_count": _extract_total_count(payload),
        "data": rows,
        "raw_payload": payload,
    }


def _fetch_recruitly_collection_preview(
    *,
    api_base_url: str,
    api_key: str,
    resource: str,
    query: str | None,
    page: int,
    size: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    normalized_query = (query or "").strip()
    params: dict[str, Any] = {
        "page": int(page),
        "size": _clamp_preview_size(size),
    }
    if normalized_query != "":
        params["search"] = normalized_query

    payload = _get_recruitly_json(
        api_base_url=api_base_url,
        api_key=api_key,
        endpoint_path=f"/api/{resource}",
        params=params,
        timeout_seconds=timeout_seconds,
    )

    data = payload.get("data")
    rows = data if isinstance(data, list) else []

    return {
        "resource": resource,
        "query": normalized_query or None,
        "page": int(page),
        "size": _clamp_preview_size(size),
        "item_count": len(rows),
        "total_count": _extract_total_count(payload),
        "data": rows,
        "raw_payload": payload,
    }


def _get_recruitly_json(
    *,
    api_base_url: str,
    api_key: str,
    endpoint_path: str,
    params: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    normalized_base_url = api_base_url.strip().rstrip("/")
    if normalized_base_url == "":
        raise ValueError("Recruitly API base URL cannot be empty.")

    normalized_api_key = api_key.strip()
    if normalized_api_key == "":
        raise ValueError("Recruitly API key cannot be empty.")

    endpoint_url = f"{normalized_base_url}{endpoint_path}"
    request_params = {
        **params,
        "apiKey": normalized_api_key,
    }

    try:
        response = httpx.get(
            endpoint_url,
            params=request_params,
            headers={"Accept": "application/json"},
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise RecruitlyApiError(
            "Recruitly API request failed before a response was returned.",
            endpoint_url=endpoint_url,
        ) from exc

    response_body: dict[str, Any] | None = None
    try:
        decoded_json = response.json()
        if isinstance(decoded_json, dict):
            response_body = decoded_json
    except ValueError:
        response_body = None

    if response.status_code >= 400:
        raise RecruitlyApiError(
            "Recruitly API request returned an error response.",
            status_code=response.status_code,
            endpoint_url=endpoint_url,
            response_body=response_body,
        )

    if response_body is None:
        raise RecruitlyApiError(
            "Recruitly API response was not a JSON object.",
            status_code=response.status_code,
            endpoint_url=endpoint_url,
        )

    return response_body


def _extract_total_count(payload: dict[str, Any]) -> int | None:
    for key in (
        "total",
        "totalCount",
        "totalElements",
        "count",
    ):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    pagination = payload.get("pagination")
    if isinstance(pagination, dict):
        for key in ("total", "totalCount", "totalElements"):
            value = pagination.get(key)
            if isinstance(value, int):
                return value
    return None


def _clamp_preview_size(size: int) -> int:
    return max(1, min(int(size), 100))


__all__ = [
    "RecruitlyApiError",
    "fetch_recruitly_candidates_preview",
    "fetch_recruitly_companies_preview",
    "fetch_recruitly_contacts_preview",
    "fetch_recruitly_jobs_preview",
    "fetch_recruitly_record_journal_preview",
]
