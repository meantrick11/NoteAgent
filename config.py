import os
from dotenv import load_dotenv 
from pydantic import BaseModel
from langchain.chat_models import init_chat_model


load_dotenv()

BASE_URL = os.getenv('DEEPSEEK_API_BASE')
API_KEY = os.getenv("DEEPSEEK_API_KEY")


def create_model(model:str | None)->BaseModel:
    """create and return a new chat_model"""
    model = init_chat_model(
        model = "deepseek-v4-flash",
        model_provider = "deepseek",
        api_key = API_KEY
    )
    
    return model



    
    
