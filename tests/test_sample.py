import subprocess
from pathlib import Path


def test_sample():
    sample_dir = Path(__file__).parent / "sample"

    addition = subprocess.run(
        ["python3", "main.py", "3+4"], capture_output=True, text=True, cwd=sample_dir
    )
    assert addition.stdout.strip() == "7"

    subtraction = subprocess.run(
        ["python3", "main.py", "10-5"], capture_output=True, text=True, cwd=sample_dir
    )
    assert subtraction.stdout.strip() == "5"

    multiplication = subprocess.run(
        ["python3", "main.py", "6*7"], capture_output=True, text=True, cwd=sample_dir
    )
    assert multiplication.stdout.strip() == "42"

    division = subprocess.run(
        ["python3", "main.py", "8/2"], capture_output=True, text=True, cwd=sample_dir
    )
    assert division.stdout.strip() == "4.0"
