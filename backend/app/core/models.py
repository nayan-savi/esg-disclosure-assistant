import os
from abc import ABC, abstractmethod

class BaseModelProvider(ABC):
    @abstractmethod
    def get_embeddings(self):
        """
        Returns the appropriate LangChain embeddings instance.
        """
        pass
        
    @abstractmethod
    def get_llm(self, temperature: float = 0.0):
        """
        Returns the appropriate LangChain ChatModel instance.
        """
        pass

class GeminiProvider(BaseModelProvider):
    def get_embeddings(self):
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        api_key = os.getenv("GEMINI_API_KEY")
        return GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=api_key)
        
    def get_llm(self, temperature: float = 0.0):
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.getenv("GEMINI_API_KEY")
        return ChatGoogleGenerativeAI(model="gemini-3.5-flash", temperature=temperature, google_api_key=api_key)

class OllamaProvider(BaseModelProvider):
    def get_embeddings(self):
        from langchain_ollama import OllamaEmbeddings
        return OllamaEmbeddings(model="nomic-embed-text")
        
    def get_llm(self, temperature: float = 0.0):
        from langchain_ollama import ChatOllama
        return ChatOllama(model="llama3", temperature=temperature)

def get_model_provider(model_name: str) -> BaseModelProvider:
    if model_name == "gemini-3.5":
        return GeminiProvider()
    else:
        return OllamaProvider()
