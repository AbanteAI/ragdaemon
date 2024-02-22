import asyncio

from ragdaemon.app import main


def run():
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
