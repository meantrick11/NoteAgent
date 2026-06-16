from langchain.agents import create_agent
from langchain.messages import HumanMessage,AIMessage,SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from agent.tools import file_related_tools
from config import create_model
import json

system_message = SystemMessage(content="""
你是一个学习笔记助手，用户会给你一段学习内容，你需要将其整理成结构化的 Markdown 笔记。

## 你拥有的工具
- create_file：返回 file_path（完整路径）
- read_from_file：传入 file_path
- write_to_file：传入 file_path

## 工作流程
1. 调用 create_file 获取 file_path
2. 调用 read_from_file(file_path) 读取已有内容
3. 调用 write_to_file(file_path, content) 写入

## 笔记格式规范
写入内容必须严格遵守以下格式：

## [HH:MM:SS] 章节标题

- 要点1
- 要点2
- 要点3

## 注意事项
- 要点要简洁，每条不超过30字
- 章节标题根据内容自动归纳，不要照抄用户输入
- 每次写入末尾加一个空行，和下一个章节隔开
- 不要重复已有笔记中已经写过的内容
""")

model = create_model(None)#create model
tools = file_related_tools()

agent = create_agent(
    model = model,
    tools = tools,
    checkpointer = InMemorySaver(),
)

def structured_output(data):
    output = {}
    output["messages"] = []
    
    for msg in data["messages"]:
        msg_type = "human" if "HumanMessage" in str(type(msg)) else "ai"
        item = {
            "type": msg_type,
            "content": msg.content,
            "id": msg.id
        }
        
        # 只保留有用的字段，去掉冗余信息
        if hasattr(msg, "response_metadata"):
            item["token_usage"] = msg.response_metadata.get("token_usage", {})
            
        if hasattr(msg, "usage_metadata"):
            item["usage_metadata"] = msg.usage_metadata
            
        if hasattr(msg, "tool_calls"):
            item["tool_calls"] = msg.tool_calls
            
        output["messages"].append(item)
    
    # 美化打印
    print(json.dumps(output, indent=2, ensure_ascii=False))


while True:
    question = input("enter your question(q to quit):")
    if question == "q":
        break
    message = HumanMessage(content=question)
    res = agent.invoke(
        input={#用户输入
            "messages":
                [
                    system_message,
                    message,]
            },
        config={
            "configurable": {"thread_id": "1"}},#记录线程
        )
    print(res["messages"][-1].content)
    
    

