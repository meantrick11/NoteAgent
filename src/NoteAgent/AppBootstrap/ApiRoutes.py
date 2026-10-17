"""Single registration point for HTTP endpoints; public URL paths are unchanged."""

from fastapi import APIRouter
from NoteAgent.Modules.Chat.Router.ChatRoutes import router as chat_router
from NoteAgent.Modules.Conversations.Router.ConversationRoutes import router as conversations_router
from NoteAgent.Modules.Notes.Router.NoteRoutes import router as notes_router
from NoteAgent.Modules.Models.Router.ModelSettingsRoutes import router as models_router
from NoteAgent.Modules.Recovery.Router.ConversationRecoveryRoutes import router as recovery_router
from NoteAgent.WebFrontend.WebRoutes import router as web_router
from NoteAgent.Modules.Sources.Router.SourceFileRoutes import router as source_file_router

router = APIRouter()
for child in (web_router, conversations_router, chat_router, notes_router, models_router, recovery_router, source_file_router):
    router.include_router(child)
