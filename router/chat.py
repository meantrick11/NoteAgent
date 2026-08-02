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
    
    @app.post("/chat/user_exit")
    async def chat_with_exist(request:Request,require:Annotated[RequestModel,Body()]): 
        agent = request.app.state.agent #获取AgentPipeline的实例
        
        thread_id = require.thread_id
        prompt = "在用户退出时，请整理本次对话通过write_to_file工具追加到context.md中，尽可能精炼（每次追加不超过500 char）"
        print(f"[user_exit] 收到退出请求, thread_id={thread_id}")
        result = await agent.agent.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]},
            {"configurable": {"thread_id": thread_id}}
        )
        # 打印 Agent 最后一条消息，看它实际干了什么
        msgs = result.get("messages", [])
        last_msg = msgs[-1] if msgs else None
        print(f"[user_exit] Agent 最后一条消息 type={type(last_msg).__name__}, content={getattr(last_msg, 'content', str(last_msg))[:300]}")
        print(f"[user_exit] 处理完成")
        return {"status":"finished"}
        
        
        

