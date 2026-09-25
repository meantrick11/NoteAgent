"""运行对象的唯一装配入口。

chat、notes 与模型管理都从这里构造模型/工具/检索对象，避免多处各拼一套依赖。它属于
bootstrap，因此 model_management 只依赖注入进来的装配器，不反向导入本包。
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from noteagent.chat.agent import ChatAgent
from noteagent.chat.context_budget import ContextBudget, budget_from_settings
from noteagent.chat.tools import build_chat_tools
from noteagent.llm.factory import create_chat_model_from_config
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.embedder import build_embedder
from noteagent.retrieval.service import RetrievalService, index_fingerprint_for_model
from noteagent.retrieval.vector_store import ChromaVectorStore

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

    from noteagent.bootstrap.settings import Settings
    from noteagent.chat.drafts import DraftStore
    from noteagent.chat.history import ConversationStore
    from noteagent.model_management.schemas import ChatProfile
    from noteagent.notes.repository import FileNoteRepository

_logger = logging.getLogger(__name__)

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
    ):
        self._settings = settings
        self._notes = notes
        self._drafts = drafts
        self._history = history

    def build_chat_model(self, profile: ChatProfile) -> BaseChatModel:
        """Build the chat client for one profile without logging its credential."""
        return create_chat_model_from_config(
            provider=profile.provider,
            model=profile.model,
            base_url=profile.base_url,
            api_key=api_key_for_profile(profile),
        )

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
        self, *, profile: ChatProfile, retrieval: RetrievalService | None
    ) -> ChatAgent:
        """Build an agent whose model, tools, and budget all belong to one profile.

        Tools are rebuilt together with the retrieval object because their closures
        capture it; patching a private attribute on the old agent would silently keep
        searching the old index.
        """
        return ChatAgent(
            model=self.build_chat_model(profile),
            tools=build_chat_tools(self._notes, retrieval, self._drafts),
            notes=self._notes,
            drafts=self._drafts,
            history=self._history,
            budget=budget_for_window(self._settings, profile.context_window),
            retrieval=retrieval,
        )
