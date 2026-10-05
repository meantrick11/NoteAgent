"""Create the HTTP application from an already assembled dependency container."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from NoteAgent.HttpApi.HttpErrors import register_exception_handlers
from NoteAgent.HttpApi.ApiRoutes import router
from NoteAgent.HttpApi.WebFrontend import DIST_DIR, STATIC_DIR
from NoteAgent.AppBootstrap.ContainerAssembly import AppContainer
from NoteAgent.AppBootstrap.AppLifespan import lifespan


def create_app(container: AppContainer) -> FastAPI:
    """Attach resources, HTTP error handlers and the complete endpoint registry."""
    app = FastAPI(lifespan=lifespan)    #
    app.state.container = container     #通过state挂载容器
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static") #访问 http://xxx/static/a.jpg → 返回服务器本地 STATIC_DIR/a.jpg 文件。
    app.mount("/ui-assets", StaticFiles(directory=str(DIST_DIR), check_dir=False), name="ui-assets")    #访问/ui-assets/index.js读取前端打包 dist 目录的静态资源，给前端页面用。
    register_exception_handlers(app)    #注册所有可能的error处理器
    app.include_router(router)      #注册所有路由
    return app
