from pydantic import BaseModel



class RequestModel(BaseModel):
    question:str
    thread_id:str
    
class ResponseModel(BaseModel):
    answer:str
    thread_id:str