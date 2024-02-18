import fire
from operations import add_numbers, divide_numbers, multiply_numbers, subtract_numbers


def calculate(operation, num1, num2):
    result = None

    if operation == "add":
        result = add_numbers(num1, num2)
    elif operation == "subtract":
        result = subtract_numbers(num1, num2)
    elif operation == "multiply":
        result = multiply_numbers(num1, num2)
    elif operation == "divide":
        result = divide_numbers(num1, num2)
    else:
        print("Invalid operation")

    return result


if __name__ == "__main__":
    fire.Fire(calculate)
