from src.interface import parse_arguments, render_response
from src.operations import add, divide, multiply, subtract


def main():
    a, op, b = parse_arguments()

    if op == "+":
        result = add(a, b)
    elif op == "-":
        result = subtract(a, b)
    elif op == "*":
        result = multiply(a, b)
    elif op == "/":
        result = divide(a, b)
    else:
        raise ValueError("Unsupported operation")

    render_response(result)


if __name__ == "__main__":
    main()
