from langchain.tools import tool
from pathlib import Path

from rag.simple_rag import RAGPipeline
#screen

NOTES_DIR: Path =  Path(__file__).parent.parent / "notes"
def screeen_related()->list:
    '''registery screen_related tools'''
    @tool("understand screen",description="This tool can help you ")
    def screen():
        pass

#file_tools
def file_related_tools(rag:RAGPipeline)->list:
    '''registery file_related tools with @tool decorator'''
    
    @tool("list_files", description="列出notes目录下所有笔记文件，返回文件名列表。")
    def list_files() -> dict:
        """列出 notes/ 目录下所有文件"""
        try:
            files = [f.name for f in NOTES_DIR.iterdir() if f.is_file()]
            return {"files": files}
        except Exception as e:
            return {"error": str(e)}
    
    @tool("read_file",description="""读取笔记文件内容。
          file_name参数必须是已经存在的笔记文件名(可通过list_files工具获取),不能通过此工具创建新文件。此工具也只能默认"r"模式读取文件内容,不能修改文件内容。
          该工具返回值为一个字典，如果存在内容则是笔记文件的具体内容，否则返回错误信息。""")
    def read_file(file_name:str)->dict:
        "read a file"
        if not file_name:
            return {"error":"no target file given"}
        try:
            with open(NOTES_DIR / file_name,"r",encoding="utf-8") as f:
                content = f.read()
            return {"file_content":content}
        except Exception as e:
            return {"error":str(e)}
    
    @tool(
        "write_to_file",
        description="""修改或追加内容到笔记文件。
        工具参数：
        file_name参数必须是已经存在的笔记文件名,不能通过此工具创建新文件。
        mode参数默认为"a"，表示追加内容，也可以为"w",表示覆盖写入,在每次新内容写入之前,需要获取到当前文件内容,如果100%确认有矛盾或者冗余的内容,将内容整合,并在写入前给用户提示确认。绝大多数情况下,应该使用追加模式。
        content参数为具体的写入内容,必须是字符串类型,默认为空字符串."""
    )
    def write_to_file(file_name:str,mode:str="a",content: str="")->dict:
        """write content to the target_file"""
        path = NOTES_DIR / file_name
        if not path:
            return {"error":"not target file given in notes portfolio"}
        if not content:
            return {"error":"no content given"}
        try:
            with open(path,mode,encoding="utf-8") as f:
                f.write(content)
            return  {"status":"finished"}
        except Exception as e:
            return {"error":str(e)}
    
    @tool("create_file",
          description="""
          在确定是新的领域的笔记时,创建一个新的markdown笔记文件,并在文件中写入一级标题。需按照以下SOP操作:
          1.首先通过list_files工具获取已经存在的笔记文件名，然后尝试匹配(当前主题和匹配的笔记文件的内容相似度,可以使用read_flle获取可能匹配的笔记文件内容)，如果相似度较高，那么询问用户是否将现有的内容添加到匹配的文件笔记中;
          2.如果没有匹配到,在确定是完全新的领域的笔记的时候才能创造一个新的markdown笔记文件，文件名必须高度概括当前领域的主题,并且文件名不能包含空格和特殊字符,只能包含字母、数字、下划线和中划线。比如:'Agent.md','LLM.md','Python.md','JavaScript.md'等；
          3.将新起的文件名或者可能追加的笔记文件名，发送给用户确认，得到用户的肯定回复或者用户给了新的笔记文件名，则按照用户的要求追加内容或新建笔记文件；
          工具参数：
          file_name参数表示具体的文件名,必须是字符串类型,不能包含特殊字符和空格,只能包含字母、数字、下划线和中划线。该参数会作为创建的文件名。
          工具返回值为一个字典，包含两个键值对，文件的创建状态和文件的路径名。
          title参数为笔记文件的标题,必须是字符串类型,不能包含特殊字符和空格,只能包含字母、数字、下划线和中划线。该参数会在创建文件时作为一级标题写入文件。如:传入title='Agent',则创建的文件内容为'# Agent'。
          status键表示文件的创建状态，可能的值为'success'表示文件创建成功，'already exists'表示文件已存在，'error'表示创建过程中出现错误。file_name键表示创建的文件名，如果创建失败则为None。""")
    def create_file(file_name:str,title: str) -> dict:
        try:
            if not file_name.endswith(".md"):
                file_name += ".md"
                
            path = NOTES_DIR / file_name
            
            if path.exists():
                return {"status": "already exists", "file_name": file_name}
            
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n")
            return {"status": "success", "file_name": file_name}
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
 
    return [read_file,write_to_file,create_file,list_files,search_relative_from_chromadb]


            
            
    
