"""运行对象的唯一装配入口。

chat、notes 与模型管理都从这里构造模型/工具/检索对象，避免多处各拼一套依赖。它属于
bootstrap，因此 model_management 只依赖注入进来的装配器，不反向导入本包。
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from NoteAgent.Modules.Chat.Agent.Graph.ChatAgent import ChatAgent
from NoteAgent.Modules.Chat.Agent.Context.ContextBudget import ContextBudget, budget_from_settings
from NoteAgent.AppBootstrap.ChatAgentFactory import build_graph_agent
from NoteAgent.Modules.Chat.Agent.Tools.ChatTools import build_chat_tools
from NoteAgent.Modules.Chat.Agent.Tools.WebReading import HttpTrafilaturaReader
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig
from NoteAgent.Modules.Models.Provider.ModelClients import build_chat_model
from NoteAgent.Modules.Models.Provider.ProviderRegistry import ProviderRegistry
from NoteAgent.Modules.Retrieval.Engine.Chunking.MarkdownChunker import MarkdownChunker
from NoteAgent.Modules.Retrieval.Engine.Embedding.TextEmbedder import build_embedder
from NoteAgent.Modules.Retrieval.Service.NoteRetrievalService import RetrievalService, index_fingerprint_for_model
from NoteAgent.Modules.Retrieval.Engine.VectorStore.ChromaVectorStore import ChromaVectorStore

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

    from NoteAgent.AppBootstrap.AppSettings import Settings
    from NoteAgent.Modules.Conversations.Service.PendingDrafts import DraftStore
    from NoteAgent.Modules.Conversations.Legacy.LegacyConversationStore import ConversationStore
    from NoteAgent.Modules.Conversations.Checkpoint.ConversationCheckpoints import CheckpointRuntime
    from NoteAgent.Modules.Conversations.Service.ConversationStateService import ConversationService
    from NoteAgent.Modules.Models.Domain.Vo.ModelContracts import ChatProfile
    from NoteAgent.Modules.Notes.Storage.Markdown.MarkdownRepository import FileNoteRepository

_logger = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parents[1] / "Modules" / "Chat" / "Agent" / "SystemPrompts" / "system.txt"

# 用户显式选择"无需认证"时给 SDK 的占位值：部分客户端要求非空字符串才肯构造。
NO_AUTH_PLACEHOLDER = "no-auth-required"


def budget_for_window(settings: Settings, context_window: int) -> ContextBudget:
    """Use the profile's context window, keeping every other threshold from Settings.

    The window is whatever the user typed in the profile; it is never guessed from the
    model name.
    """
    return replace(budget_from_settings(settings), window=context_window)


def api_key_for_profile(profile: ChatProfile) -> str:
    """Return the credential to hand the SDK for this profile.

    A keyless deployment gets an explicit placeholder, because the OpenAI client refuses
    to construct without one; a profile that requires a key and has none is an error
    rather than a silent unauthenticated request.
    """
    if profile.auth_mode == "none":
        return NO_AUTH_PLACEHOLDER
    key = profile.api_key.get_secret_value().strip()
    if not key:
        raise ValueError("该配置要求 API Key，但当前没有可用凭据")
    return key


class BootstrapAssembler:
    """Implements the RuntimeAssembler protocol consumed by model_management."""

    def __init__(
        self,
        settings: Settings,
        notes: FileNoteRepository,
        drafts: DraftStore,
        history: ConversationStore,
        conversations: ConversationService | None = None,
        checkpoints: CheckpointRuntime | None = None,
        mutations=None,
        source_files=None,
        catalog=None,
    ):
        self._settings = settings
        self._notes = notes
        self._drafts = drafts
        self._history = history
        self._conversations = conversations
        self._checkpoints = checkpoints
        self._mutations = mutations
        self._source_files = source_files
        self._catalog = catalog or ProviderRegistry()

    def build_chat_model(self, model: ModelConfig) -> BaseChatModel:
        """Build the chat client for one model configuration."""
        return build_chat_model(model, self._catalog.resolve(model.provider))

    def index_fingerprint(self, *, model_id: str, resolved_revision: str | None) -> str:
        """Identity of the index this model and chunk configuration would build.

        Computed without loading the model, because the target collection has to be
        named from this identity before the rebuild starts.
        """
        return index_fingerprint_for_model(
            model_id,
            strategy=self._settings.chunk_strategy,
            embed_heading_prefix=self._settings.embed_heading_prefix,
            resolved_revision=resolved_revision,
        )

    def build_retrieval(
        self,
        *,
        model_id: str,
        resolved_revision: str | None,
        collection: str,
        local_files_only: bool,
        create_if_missing: bool,
    ) -> RetrievalService:
        """Build the retrieval stack for one embedding model and collection."""
        embedder = build_embedder(
            model_id,
            self._settings.embedding_cache_dir,
            local_files_only=local_files_only,
        )
        return RetrievalService(
            notes=self._notes,
            chunker=MarkdownChunker(strategy=self._settings.chunk_strategy),
            embedder=embedder,
            store=ChromaVectorStore(
                self._settings.chroma_dir, collection, create_if_missing=create_if_missing
            ),
            embed_heading_prefix=self._settings.embed_heading_prefix,
            resolved_revision=resolved_revision,
        )

    def build_agent(
        self, *, model: ModelConfig, retrieval: RetrievalService | None
    ) -> ChatAgent:
        """Build a graph-backed agent bound to the shared checkpoint service.

        Tools are rebuilt together with the retrieval object because their closures
        capture it; patching a private attribute on the old agent would silently keep
        searching the old index. The conversation service and checkpointer are shared
        across model switches, so a switch never orphans the persisted history.
        """
        if self._conversations is None or self._checkpoints is None:
            raise RuntimeError("assembler needs the conversation service and checkpointer")
        client = self.build_chat_model(model)
        return build_graph_agent(
            model=client,
            tools=build_chat_tools(
                self._notes,
                retrieval,
                self._drafts,
                repairs=self._mutations.index_repairs if self._mutations else None,
                web_reader=HttpTrafilaturaReader(),
                source_files=self._source_files,
            ),
            notes=self._notes,
            drafts=self._drafts,
            budget=budget_for_window(self._settings, model.context_window),
            system_prompt=SYSTEM_PROMPT_PATH.read_text(encoding="utf-8"),
            service=self._conversations,
            checkpoints=self._checkpoints,
            retrieval=retrieval,
            mutations=self._mutations,
        )
