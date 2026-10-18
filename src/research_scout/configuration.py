"""Workspace and cache configuration kept separate from package source."""
from pathlib import Path
import os
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class WorkspaceConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: str = '1.0'
    cache_dir: str | None = None
    interest_queries: list[str] = Field(default_factory=lambda: ['all:Langevin'])
    interest_labels: list[str] = Field(default_factory=list)
    max_results: int = Field(default=10, ge=1, le=100)
    extraction_provider: Literal['http', 'codex'] = 'http'
    codex_binary: str = 'codex'
    codex_timeout: int = Field(default=900, ge=10, le=3600)
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key_env: str = 'SCOUT_API_KEY'


def default_workspace() -> Path:
    return Path(os.environ.get('SCOUT_WORKSPACE', '~/.local/share/research-scout')).expanduser()


def load_config(workspace: Path) -> WorkspaceConfig:
    path = workspace/'config.json'
    if not path.is_file():
        raise ValueError(f'Workspace not initialized: {workspace}; run scout init')
    return WorkspaceConfig.model_validate_json(path.read_text())


def cache_path(workspace: Path, config: WorkspaceConfig) -> Path:
    return Path(os.environ.get('SCOUT_CACHE', config.cache_dir or str(workspace/'sources'))).expanduser()


def extraction_provider(config: WorkspaceConfig):
    """Select an explicit model backend; no fixture or credential fallback."""
    if config.extraction_provider == 'codex':
        from research_scout.extraction import CodexExecProvider
        return CodexExecProvider(model=config.llm_model,binary=config.codex_binary,
                                 timeout=config.codex_timeout)
    from research_scout.extraction import OpenAICompatibleProvider
    return OpenAICompatibleProvider(model=config.llm_model,base_url=config.llm_base_url,
                                    api_key=os.environ.get(config.llm_api_key_env))
