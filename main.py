from fastapi import FastAPI,Body
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Annotated
import uvicorn
import os

from agent import AgentPipeline
from rag import RAGPipeline

from router import register_all_router

def main():

   RAG = RAGPipeline(
      embed_model_name="all-MiniLM-L6-v2",
      cache_folder=r"D:\develop\aidevelop\models",
      chromadb_path="./chromadb_persist",
      collection_name="my_knowledge",
   )
   app = FastAPI()   #创建FastAPI实例
   agent =AgentPipeline(rag=RAG)    #传入具体的RAG实例，创造一个agent实例，
   app.state.agent = agent    #和app实例绑定一个属性
   register_all_router(app)   #注册路由
   
   uvicorn.run(app,host="127.0.0.1",port=8000)
   
   

if __name__=="__main__":
   main()


