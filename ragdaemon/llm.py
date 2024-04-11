import tiktoken


DEFAULT_COMPLETION_MODEL = "gpt-4-0125-preview"


def token_counter(
    text: str, model: str | None = None, full_message: bool = False
) -> int:
    if model is None:
        model = DEFAULT_COMPLETION_MODEL
    return len(tiktoken.encoding_for_model(model).encode(text))
