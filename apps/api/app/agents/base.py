"""Agent base types and execution context."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel

from app.ports.interfaces import (
    ImageProvider,
    LLMProvider,
    Storage,
    TTSProvider,
    VideoRenderer,
    YouTubeService,
)
from app.ports.interfaces import Usage as PortUsage

InT = TypeVar("InT", bound=BaseModel)
OutT = TypeVar("OutT", bound=BaseModel)


class AgentError(RuntimeError):
    def __init__(self, message: str, *, agent_key: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.agent_key = agent_key
        self.retryable = retryable


@dataclass(slots=True)
class AgentContext:
    """Everything an agent may use. Providers are injected — agents never construct them."""

    workspace_id: uuid.UUID
    project_id: uuid.UUID | None = None
    workflow_id: uuid.UUID | None = None
    channel_id: uuid.UUID | None = None
    request_key: str = field(default_factory=lambda: uuid.uuid4().hex)
    llm: LLMProvider | None = None
    tts: TTSProvider | None = None
    image: ImageProvider | None = None
    storage: Storage | None = None
    renderer: VideoRenderer | None = None
    youtube: YouTubeService | None = None
    provider_id: uuid.UUID | None = None
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    logger: Any = None

    def require_llm(self) -> LLMProvider:
        if self.llm is None:
            raise AgentError("This agent requires an LLM provider that is not configured",
                             agent_key="llm", retryable=False)
        return self.llm

    def require_tts(self) -> TTSProvider:
        if self.tts is None:
            raise AgentError("This agent requires a TTS provider that is not configured",
                             agent_key="tts", retryable=False)
        return self.tts

    def require_image(self) -> ImageProvider:
        if self.image is None:
            raise AgentError("This agent requires an image provider that is not configured",
                             agent_key="image", retryable=False)
        return self.image

    def require_storage(self) -> Storage:
        if self.storage is None:
            raise AgentError("Storage is not configured", agent_key="storage", retryable=False)
        return self.storage


@dataclass(slots=True)
class AgentResult(Generic[OutT]):
    output: OutT
    usage: PortUsage
    provider: str = ""
    model: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)

    @property
    def duration_ms(self) -> int:
        return int((time.time() - self.started_at) * 1000)


class Agent(Protocol[InT, OutT]):
    key: str
    name: str
    InputModel: type[InT]
    OutputModel: type[OutT]

    async def run(self, ctx: AgentContext, payload: InT) -> AgentResult[OutT]: ...
