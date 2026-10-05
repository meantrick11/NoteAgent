"""Single registration point for HTTP endpoints; public URL paths are unchanged."""

from fastapi import APIRouter
from NoteAgent.HttpApi.ChatApi.ChatRoutes import router as chat_router
from NoteAgent.HttpApi.ConversationApi.ConversationRoutes import router as conversations_router
from NoteAgent.HttpApi.NoteApi.NoteRoutes import router as notes_router
from NoteAgent.HttpApi.ModelSettingsApi.ModelSettingsRoutes import router as models_router
from NoteAgent.HttpApi.ConversationRecoveryApi.ConversationRecoveryRoutes import router as recovery_router
from NoteAgent.HttpApi.WebFrontend.WebRoutes import router as web_router

router = APIRouter()
for child in (web_router, conversations_router, chat_router, notes_router, models_router, recovery_router):
    router.include_router(child)
