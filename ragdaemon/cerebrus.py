import ast

from spice import Spice, SpiceMessages

from ragdaemon.graph import KnowledgeGraph


def parse_script(response: str) -> tuple[str, str]:
    """Split the response into a message and a script.

    Expected use is: run the script if there is one, otherwise print the message.
    """
    # Parse delimiter
    n_delimiters = response.count("```")
    if n_delimiters < 2:
        return response, ""
    segments = response.split("```")
    message = f"{segments[0]}\n{segments[-1]}"
    script = "```".join(segments[1:-1]).strip()  # Leave 'inner' delimiters alone

    # Check for common mistakes
    if script.split("\n")[0].startswith("python"):
        script = "\n".join(script.split("\n")[1:])
    try:  # Make sure it's valid python
        ast.parse(script)
    except SyntaxError:
        raise SyntaxError(f"Script contains invalid Python:\n{response}")
    return message, script


class Printer:
    printed: str = ""
    answered: str = ""

    def print(self, *args: str):
        self.printed += " ".join(str(a) for a in args) + "\n"

    def answer(self, *args: str):
        self.answered += " ".join(str(a) for a in args) + "\n"


async def cerebrus(
    query: str, graph: KnowledgeGraph, spice_client: Spice, leash: bool = False
) -> str:
    messages = SpiceMessages(spice_client)
    messages.add_system_prompt("cerebrus")
    messages.add_user_message(query)

    starting_cost = spice_client.total_cost
    printer = Printer()
    max_iterations = 10
    answer = ""
    for _ in range(max_iterations):
        response = await spice_client.get_response(messages=messages)
        script = ""
        try:
            message, script = parse_script(response.text)
            if not script:
                if message:
                    answer = message
                break
            exec(
                script,
                {"print": printer.print, "answer": printer.answer, "graph": graph},
            )
        except KeyboardInterrupt:
            raise
        except Exception as e:
            printer.print(f"Error: {e}")
        if not printer.printed:
            if printer.answered:
                answer = printer.answered
            break
        next_message = f"Script: {script}\n{80*'-'}\nOutput: {printer.printed}"
        messages.add_system_message(next_message)
        if leash:
            print(next_message)
        printer.printed = ""
    if leash:
        print("Total cost:", spice_client.total_cost - starting_cost)
    return answer
