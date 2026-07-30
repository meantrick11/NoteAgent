from fastapi import FastAPI
from router.chat import register_basic_router


def register_all_router(app:FastAPI):
    '''注册所有路由'''
    register_basic_router(app)
    
__all__ = ["register_all_router"]

