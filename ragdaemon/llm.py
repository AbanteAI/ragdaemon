from openai import AsyncOpenAI
import tiktoken

MODEL = "gpt-4-0125-preview"
client = AsyncOpenAI()


async def acompletion(
    messages: list[dict[str, str]],
    model: str = MODEL,
    response_format: dict = {"type": "text"},
):
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        stream=False,
        response_format=response_format,
    )
    return response


def token_counter(
    text: str,
    model: str = MODEL,
) -> int:
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))
