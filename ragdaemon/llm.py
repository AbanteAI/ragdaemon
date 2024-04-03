from chromadb.api.types import Embeddable, EmbeddingFunction, Embeddings
from spice import Spice, SpiceEmbeddings
from spice.utils import count_string_tokens

DEFAULT_COMPLETION_MODEL = "gpt-4-0125-preview"

embedding_client = SpiceEmbeddings()


class RagdaemonEmbeddingFunction(EmbeddingFunction[Embeddable]):
    def __call__(self, input: Embeddable) -> Embeddings:
        return embedding_client.get_embeddings(input)


embedding_function = RagdaemonEmbeddingFunction()


completions_client = Spice()


async def acompletion(
    messages: list[dict[str, str]],
    model: str = DEFAULT_COMPLETION_MODEL,
    response_format: dict = {"type": "text"},
) -> str:
    response = await completions_client.call_llm(
        messages=messages,
        model=model,
        stream=False,
        response_format=response_format,
    )
    return response.text


def token_counter(text: str) -> int:
    return count_string_tokens(text, DEFAULT_COMPLETION_MODEL, full_message=True)
