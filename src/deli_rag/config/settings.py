from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbedderCfg(BaseModel):
    name: str
    dim: int
    max_tokens: int
    normalize: bool


class RerankerCfg(BaseModel):
    name: str
    top_k_in: int
    top_k_out: int
    min_score: float


class RetrievalCfg(BaseModel):
    dense_top_k: int
    keyword_top_k: int
    rrf_k: int
    final_top_k: int


class LLMEntry(BaseModel):
    id: str
    roles: list[str] = []
    verified: bool = True
    base_url: str | None = None


class LLMCfg(BaseModel):
    primary: LLMEntry
    fallback_1: LLMEntry
    fallback_2: LLMEntry
    ollama: LLMEntry | None = None  # <--- ADD THIS
    fallback_on: list[int | Literal["timeout"]]
    retry_backoff_s: list[int]


class BudgetsCfg(BaseModel):
    answer_max_tokens: int
    context_max_tokens: int
    agent_max_iterations: int
    latency_p95_budget_s: int


class ChunkingCfg(BaseModel):
    parent_max_tokens: int
    child_target_tokens: int
    child_max_tokens: int
    child_min_tokens: int
    overlap_tokens: int
    context_line_max_tokens: int


class AccessCfg(BaseModel):
    default_email_acl: Literal["public", "internal", "confidential"]
    levels: list[str]


class FreshnessCfg(BaseModel):
    stale_after_days: int
    downweight_factor: float

class CompressionCfg(BaseModel):
    dedup_by_hash: bool = True
    min_score: float = 0.005
    merge_adjacent: bool = True
    max_merged_tokens: int = 700
    max_total_tokens: int = 3000
    min_chunks_to_keep: int = 3
    max_chunks: int = 8

class AgentCfg(BaseModel):
    # model roles (kept for future phases; Phase 4 Message B doesn't use them yet)
    intent_model: str = "openai/gpt-oss-20b"
    generation_model: str = "openai/gpt-oss-20b"
    judge_model: str = "openai/gpt-oss-120b"
    max_evidence_blocks: int = 8
    max_answer_tokens: int = 500
    # loop controls
    max_iterations: int = 2
    min_confidence: float = 0.55
    broaden_factor: float = 2.0
    max_k: int = 24
    reroute_on_retry: bool = True
    latency_budget_s: float = 20.0

class AppConfig(BaseModel):
    version: int
    config_version: str
    embedder: EmbedderCfg
    reranker: RerankerCfg
    retrieval: RetrievalCfg
    llm: LLMCfg
    budgets: BudgetsCfg
    compression: CompressionCfg
    agent: AgentCfg                 # ← new
    chunking: ChunkingCfg
    access: AccessCfg
    freshness: FreshnessCfg

class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    groq_api_key: str = ""
    groq_models_endpoint: str = "https://api.groq.com/openai/v1/models"
    app_env: str = "dev"
    log_level: str = "INFO"
    config_path: Path = Field(default=Path("config/base.yaml"))
    inbox_path: Path = Field(default=Path("./inbox"))


@lru_cache
def get_env() -> EnvSettings:
    return EnvSettings()  # type: ignore[call-arg]


@lru_cache
def get_config() -> AppConfig:
    env = get_env()
    raw = yaml.safe_load(env.config_path.read_text())
    return AppConfig(**raw)