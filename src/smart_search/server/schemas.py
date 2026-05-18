"""Pydantic schemas for the cloud server API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class ToolResponse(BaseModel):
    """Uniform response wrapper for all tool endpoints."""

    ok: bool = True
    error_type: str = ""
    error: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    platform: str = ""
    model: str = ""
    extra_sources: int = 0
    validation: str = ""
    fallback: str = ""
    providers: str = "auto"


# ---------------------------------------------------------------------------
# Fetch URL
# ---------------------------------------------------------------------------

class FetchUrlRequest(BaseModel):
    url: str


# ---------------------------------------------------------------------------
# Map Site
# ---------------------------------------------------------------------------

class MapSiteRequest(BaseModel):
    url: str
    instructions: str = ""
    max_depth: int = 1
    max_breadth: int = 20
    limit: int = 50
    timeout: int = 150


# ---------------------------------------------------------------------------
# Docs Search
# ---------------------------------------------------------------------------

class DocsSearchRequest(BaseModel):
    query: str
    library_id: str = ""
    name: str = ""


# ---------------------------------------------------------------------------
# Web Search
# ---------------------------------------------------------------------------

class WebSearchRequest(BaseModel):
    query: str
    count: int = 10
    provider: str = "auto"  # auto / exa / zhipu


# ---------------------------------------------------------------------------
# Deep Plan
# ---------------------------------------------------------------------------

class DeepPlanRequest(BaseModel):
    query: str = Field(..., alias="topic")
    budget: str = Field("standard", alias="depth")
    evidence_dir: str = ""

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

class DoctorRequest(BaseModel):
    """Doctor takes no body, but we keep a placeholder for consistency."""

    pass
