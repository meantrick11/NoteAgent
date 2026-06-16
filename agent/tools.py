from langchain.tools import tool
from pathlib import Path
from datetime import datetime
#screen
def screeen_related()->list:
    '''registery screen_related tools'''
    @tool("understand screen",description="This tool can help you ")
    def screen():
        pass

#file_tools
def file_related_tools()->list:
    '''registery file_related tools '''
    
    @tool("read__from_file",description="读取笔记文件内容。file_path 必须是 create_file 返回的完整路径，不能自己构造文件名。")
    def read_from_file(file_name:str)->dict:
        "read a file"
        if not file_name:
            return {"error":"no target file given"}
        try:
            with open(file_name,"r") as f:
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
    
    return [read_from_file,write_to_file,create_file]


            
            
    
