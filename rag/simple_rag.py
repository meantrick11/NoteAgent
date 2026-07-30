import os 
import time
import sys
from typing import List,Optional

from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
from chromadb import PersistentClient,Client
from chromadb import QueryResult
from chromadb.config import Settings
from chromadb.api.models.Collection import Collection

class RAGPipeline:   
    
    def __init__(
        self,
        embed_model_name: str = "all-MiniLM-L6-v2",
        cache_folder: Optional[str] = None,
        chromadb_path: str = "./chromadb_persist",
        collection_name: str = "my_knowledge",
    ):
        self.embed_model = self.init_embed_model(embed_model_name)#类初始化的向量嵌入模型
        self.cache_folder = cache_folder
        self.chromadb_path = chromadb_path
        self.collection_name = collection_name
        self.client = self.link_to_chromadb()
        self.collection = self.client.get_or_create_collection(self.collection_name)
        
    def path_to_save(self,file_name:str)->None:
        '''give path's content(which is in the notes portfile) &save to the chromadb automately'''
        content = self.get_file_content(file_name)  # 获取本地文件的内容
        chunks = self.content_split_to_chunks(content)  #将获取的内容进行本地embedding模型进行分块
        embeddings = self.embed_model.encode(chunks).tolist()
        client = self.link_to_chromadb()    #连接到chromdb数据库
        collection = self.save_to_collection(client,embeddings,chunks)  #将路径中的
        
    def query_from_local_chromadb(self,question:str,collection=None,embd_model=None)->QueryResult:
        '''GET RELATIVE CHUNKS FORM CHROMDB'''
        if not collection:
            collection = self.collection
        if not embed_model:
            embed_model = self.embed_model
        return self.search_similar(question,collection,embed_model)
        
        
        
        
    def init_embed_model(self,model_name:str="all-Min-L6-v2")->SentenceTransformer:
        '''INIT THE EMBEDDING MODEL'''
        embed_model = SentenceTransformer(
            "all-MiniLM-L6-v2",
            cache_folder=r"D:\develop\aidevelop\transformer_models",
            local_files_only=True,
        )
        return embed_model
    
    def get_file_content(self,file_name:str)->str:
        '''get the content form ../notes/(file_name)'''
        file_path = os.path.join("notes",file_name)
        with open(file_path,"r",encoding="utf-8") as f:
            content = f.read()
        return content

    def content_split_to_chunks(self,content:str)->List[str]:
        '''split content to chunks'''
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size = 500,
            chunk_overlap = 50,
            length_function = len,
            separators = ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        )
        chunks = text_splitter.split_text(content)
        return chunks

    def link_to_chromadb(self,chromadb_path:str=None)->PersistentClient:
        '''link to local chromadb，return chromadb class client'''
        if not chromadb_path:
            chromadb_path = self.chromadb_path
    
        client = chromadb.PersistentClient(
            path=chromadb_path,
            settings = Settings(anonymized_telemetry_enabled=False)
        )
        return client

    def save_to_collection(self,client:Client,embeddings:List[List[float]],chunks:List[str],collection_name:str=None)->None:
        """将带有chunks的元数据的向量入库到collections中"""
        if not collection_name:
            collection_name = self.collection_name
        collection = client.get_or_create_collection(collection_name)
        base_id = f"doc_{int(time.time())}"
        ids = [f"{base_id}_{i}" for i in range(len(chunks))]
        
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=[{"chunk_index": i} for i in range(len(chunks))]
        )  

    # ========== 检索测试（验证入库是否成功） ==========

    def search_similar(self,query:str,collection:Collection=None,embed_model:str=None, top_k:int=2)->QueryResult:
        """根据问题检索最相关的文本切片"""
        if not embed_model:
            embed_model = self.embed_model
        if not collection:
            collection=self.collection
        # 1. 把问题变成向量
        query_emb = self.embed_model.encode([query]).tolist()
        
        # 2. 去数据库查询
        results = collection.query(
            query_embeddings=query_emb,
            n_results=top_k,
            include=["documents", "distances"]  # 只返回原文和相似度分数
        )
        
        return results
        # # 3. 打印结果
        # if results["documents"] and len(results["documents"][0]) > 0:
        #     print(f"\n🔍 检索结果（共 {len(results['documents'][0])} 条）")
        #     for i, (doc, dist) in enumerate(zip(results["documents"][0], results["distances"][0])):
        #         # 注意：ChromaDB 返回的是距离（越小越相似），转成相似度分数用 1 - dist
        #         score = 1 - dist
        #         print(f"\n--- 片段 {i+1} （相似度得分：{score:.4f}）---")
        #         print(doc[:150] + "..." if len(doc) > 150 else doc)
        # else:
        #     print("未找到相关结果")



def main():
    # 1. 初始化 RAG 流水线
    rag = RAGPipeline()
    
    # 2. 索引文件（假设 notes/2026-06-21.md 存在）
    file_to_index = "2026-06-21.md"
    try:
        print(f"正在索引文件：{file_to_index}")
        rag.path_to_save(file_to_index)
    except FileNotFoundError:
        print(f"❌ 文件 {file_to_index} 未找到，请确保它位于 notes/ 目录下。")
        return
    except Exception as e:
        print(f"❌ 索引过程中发生错误：{e}")
        return

    # 3. 交互式检索
    print("\n✅ 索引完成，可以开始检索。输入 q 退出。")
    while True:
        question = input("\n请输入你的问题：").strip()
        if question.lower() == "q":
            print("退出程序。")
            break
        if not question:
            continue

        # 执行检索（只传 query，其他使用默认值）
        results = rag.search_similar(query=question)

        # 打印检索结果
        if results["documents"] and len(results["documents"][0]) > 0:
            print(f"\n🔍 检索结果（共 {len(results['documents'][0])} 条）")
            for i, (doc, dist) in enumerate(
                zip(results["documents"][0], results["distances"][0])
            ):
                score = 1 - dist  # 距离转相似度
                print(f"\n--- 片段 {i+1} （相似度得分：{score:.4f}）---")
                preview = doc[:150] + "..." if len(doc) > 150 else doc
                print(preview)
        else:
            print("未找到相关结果。")

if __name__ == "__main__":
    main()