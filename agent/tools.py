from langchain.tools import tool
from pathlib import Path
from datetime import datetime

from rag.simple_rag import RAGPipeline
#screen

NOTES_DIR: Path = Path("./notes")

def screeen_related()->list:
    '''registery screen_related tools'''
    @tool("understand screen",description="This tool can help you ")
    def screen():
        pass

#file_tools
def file_related_tools(rag:RAGPipeline)->list:
    '''registery file_related tools with @tool decorator'''
    
    @tool("list_files", description="列出notes目录下所有笔记文件，用于查看有哪些历史笔记可以读取")
    def list_files() -> dict:
        """列出 notes/ 目录下所有文件"""
        try:
            files = [f.name for f in NOTES_DIR.iterdir() if f.is_file()]
            return {"files": files}
        except Exception as e:
            return {"error": str(e)}
    
    @tool("read__from_file",description="读取笔记文件内容。file_path 必须是 create_file 返回的完整路径，不能自己构造文件名。")
    def read_from_file(file_name:str)->dict:
        "read a file"
        if not file_name:
            return {"error":"no target file given"}
        try:
            with open(file_name,"r",encoding="utf-8") as f:
                content = f.read()
            return {"file_content":content}
        except Exception as e:
            return {"error":str(e)}
    
    @tool(
        "write_to_file",
        description="追加内容到笔记文件。file_path 必须是 create_file 返回的完整路径，不能自己构造文件名。"
    )
    def write_to_file(file_name:str,content: str)->dict:
        """write content to the target_file"""
        path = file_name
        if not path:
            return {"error":"not target file given in notes portfolio"}
        if not content:
            return {"error":"no content given"}
        try:
            with open(path,"a",encoding="utf-8") as f:
                f.write(content)
            return  {"status":"finished"}
        except Exception as e:
            return {"error":str(e)}
    
    @tool("create_file",description="Create a new markdown file with a title,auto-generates filename by date.")
    def create_file(title: str) -> dict:
        """Create today's note file, filename auto-generated as YYYY-MM-DD.md"""
        try:
            date_str = datetime.now().strftime("%Y-%m-%d")
            file_name = f"{date_str}.md"
            path = Path(__file__).parent.parent / "notes" / file_name
            
            if path.exists():
                return {"status": "already exists", "file_path": path}
            
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n")
            return {"status": "success", "file_path": path}
        except Exception as e:
            return {"error": str(e)}
   
    @tool("search_relative_from_chromadb", description="根据问题在笔记库中语义检索最相关的笔记片段，返回匹配的片段列表。当用户询问历史记录中的知识点时，应优先使用此工具。")
    def search_relative_from_chromadb(query: str) -> dict:
        """
        使用 RAG 检索相关笔记片段
        :param query: 用户的问题或关键词
        :return: {"fragments": [片段列表], "count": 片段数量}
        """
        try:
            
            results = rag.search_similar(query=query, top_k=3)
            docs = results.get("documents", [[]])[0]  # 取文档列表
            if docs:
                return {"fragments": docs, "count": len(docs)}
            else:
                return {"fragments": [], "count": 0}
        except Exception as e:
            return {"error": str(e)}
 
    return [read_from_file,write_to_file,create_file,list_files,search_relative_from_chromadb]


            
            
    
