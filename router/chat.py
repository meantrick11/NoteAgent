from fastapi import FastAPI,Request,Body
from fastapi.responses import HTMLResponse
from fastapi.sse import EventSourceResponse
from typing import Annotated
import os

from router.json_schema import RequestModel,ResponseModel 

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def register_basic_router(app:FastAPI):
    '''BUILD FASTAPI SERVER'''
    @app.get("/",response_class=HTMLResponse)
    async def home():
        '''GET THE HOME PAGE'''
        with open(os.path.join(BASE_DIR,"..","templates","home.html"),"r",encoding="utf-8") as f:
            return f.read() 
    @app.post("/chat",response_class=EventSourceResponse)
    async def chat_with(request:Request,require:Annotated[RequestModel,Body()]):
        agent = request.app.state.agent #获取app的实例
        
        question = require.question
        thread_id = require.thread_id
        
        async for token in agent.stream_answer(question,thread_id):
            yield token
        
        

