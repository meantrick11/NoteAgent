from langchain.agents import create_agent
from langchain.messages import HumanMessage,AIMessage,AIMessageChunk,SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from agent.tools import file_related_tools
from config import create_model


from typing import AsyncGenerator
import os

from agent.tools import NOTES_DIR

class AgentPipeline:
    def __init__(self,rag=None):
        self.rag = rag
        self.agent = self.init_agent()
        
    def init_agent(self):
        '''初始化agent,create_model&create_tools->return an agent'''
        model = create_model(None)#create model
        tools = file_related_tools(self.rag)# add tools #inculde create rag tools

        agent = create_agent(
            model = model,
            tools = tools,
            checkpointer = InMemorySaver(),
        )
        return agent
       
    def get_sys_prompt(self)->SystemMessage:
        '''read system_prompts and return SystemMessage(content)'''
        current_dir = os.path.dirname(__file__)#获取当前文件夹的目录
        file_path = os.path.join(current_dir, "prompts", "system_prompts.txt")#拼接系统提示词目录,根据操作系统拼接
        with open(file_path,'r',encoding="utf-8") as f:
            file_content = f.read()
        sys_prompt = SystemMessage(content=file_content)
        return sys_prompt


        
    async def stream_answer(self,question:str,thread_id:str,system_message:str="")->AsyncGenerator[str, None]:
        '''get answer from agent asynchronously,return AIMessage'''
        config = {"configurable":{"thread_id":thread_id}}
        state = await self.agent.aget_state(config=config)  #获取当前的agent的thread_id的状态，方便判断是否是第一次对话，只加载一次sys_prompt&context.md
        
        humanmessage = HumanMessage(content=question)
        system_message1 = self.get_sys_prompt() #获取系统提示词
        if state.values:    #如果当前thread_id的状态中有值,说明不是第一次对话,不需要再加载sys_prompt和context.md
            messages = [humanmessage]
        else:   #如果当前thread_id的状态中没有值,说明是第一次对话,需要加载sys_prompt和context.md
            try:
                with open(NOTES_DIR / "context.md","r",encoding="utf-8") as f:    #读取context.md文件内容
                    context_content = f.read()  
                system_message2 = SystemMessage(content=context_content)    #将context.md文件内容作为系统消息
                messages = [system_message1,system_message2,humanmessage]
            except FileNotFoundError:
                # Handle the case where context.md does not exist
                messages = [system_message1,humanmessage]

        async for mode,chunk in self.agent.astream(
            input={#用户输入
                "messages":
                    messages
                },
            config={
                "configurable": {"thread_id":thread_id}},#记录线程
            stream_mode = ["messages"],
            ):
                aimessage,metadata = chunk
                if isinstance(aimessage,(AIMessage,AIMessageChunk)):#过滤只有AIMessage和AIMessageChunk的内容，而不是ToolMessage也返回
                    yield aimessage.content 
    
if __name__ == "__main__":
    import asyncio
    agent = AgentPipeline()
    async def main():
        async for answer in agent.stream_answer(question="你好",thread_id=1):
            print(answer)
    asyncio.run(main())