"""ORM models — one module per domain. Import order matters for metadata only; FKs are
referenced by table name so circular imports are avoided."""

from app.models.ai import Agent, AgentConfiguration, AiProvider
from app.models.channel import (
    Channel,
    ChannelCharacter,
    ChannelSetting,
    Schedule,
    YouTubeOAuthConnection,
)
from app.models.content import (
    AudioAsset,
    ContentProject,
    MediaAsset,
    Scene,
    Script,
    Storyboard,
    VideoRender,
)
from app.models.identity import ApiKey, User, Workspace, WorkspaceMember
from app.models.production import (
    AiUsageLog,
    AnalyticsSnapshot,
    ApprovalRequest,
    AuditLog,
    ContentIdea,
    ProductionWorkflow,
    PublishingJob,
    QualityReport,
    WorkflowLog,
    WorkflowTask,
    YouTubeVideo,
)
from app.models.render import RenderCostLog, RenderJob, RenderValidation
from app.models.tts import TTSConfiguration
from app.models.tts_generation import TTSGeneration, TTSPreviewCache, TTSUsageLog

__all__ = [
    "ApiKey",
    "User",
    "Workspace",
    "WorkspaceMember",
    "Channel",
    "ChannelCharacter",
    "ChannelSetting",
    "Schedule",
    "YouTubeOAuthConnection",
    "Agent",
    "AgentConfiguration",
    "AiProvider",
    "TTSConfiguration",
    "TTSGeneration",
    "TTSUsageLog",
    "TTSPreviewCache",
    "AudioAsset",
    "MediaAsset",
    "Scene",
    "Script",
    "Storyboard",
    "VideoRender",
    "AiUsageLog",
    "AnalyticsSnapshot",
    "ApprovalRequest",
    "AuditLog",
    "ContentIdea",
    "ContentProject",
    "ProductionWorkflow",
    "PublishingJob",
    "QualityReport",
    "WorkflowLog",
    "WorkflowTask",
    "YouTubeVideo",
    "RenderJob",
    "RenderValidation",
    "RenderCostLog",
]
