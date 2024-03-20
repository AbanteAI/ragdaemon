import os

from chromadb.utils.embedding_functions import (
    DefaultEmbeddingFunction, 
    OpenAIEmbeddingFunction,
)
from openai import AsyncOpenAI
import tiktoken


DEFAULT_COMPLETION_MODEL = "gpt-4-0125-preview"
embedding_function = DefaultEmbeddingFunction()
client = None
completion_model = None

openai_api_key = os.environ.get("OPENAI_API_KEY")
if openai_api_key is not None:
    embedding_function = OpenAIEmbeddingFunction(
        api_key=openai_api_key,
        model_name="text-embedding-3-small",
    )
    client = AsyncOpenAI()
    completion_model = DEFAULT_COMPLETION_MODEL


async def acompletion(
    messages: list[dict[str, str]],
    model: str = completion_model,
    response_format: dict = {"type": "text"},
):
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        stream=False,
        response_format=response_format,
    )
    return response



encodings = {}
def get_encoding_for(model: str) -> tiktoken.Encoding:
    if encodings.get(model) is None:
        encodings[model] = tiktoken.encoding_for_model(model)
    return encodings[model]


def token_counter(
    text: str,
    model: str = None,
) -> int:
    if model is None:
        model = completion_model or DEFAULT_COMPLETION_MODEL
    encoding = get_encoding_for(model)
    return len(encoding.encode(text))
