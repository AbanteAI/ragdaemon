import argparse
import re


def parse_arguments():
    parser = argparse.ArgumentParser(description="Basic Calculator")
    parser.add_argument("operation", type=str, help="Calculation operation")
    args = parser.parse_args()

    # use re to parse symbol, nubmer before, nubmer after
    match = re.match(r"(\d+)(\D)(\d+)", args.operation)
    if match is None:
        raise ValueError("Invalid operation")
    return int(match.group(1)), match.group(2), int(match.group(3))


def render_response(result):
    print(result)
