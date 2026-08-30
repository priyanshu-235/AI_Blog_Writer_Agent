from langchain_google_genai import ChatGoogleGenerativeAI

from backend.config import TEXT_MODEL

content_engine = ChatGoogleGenerativeAI(
    model=TEXT_MODEL,
    temperature=0.3,
)
