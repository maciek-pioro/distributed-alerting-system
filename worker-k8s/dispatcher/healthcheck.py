import asyncio

EXIT_CODE = None


async def check():
    global EXIT_CODE
    with open("/app/health", "r") as f:
        health = f.read()
    await asyncio.sleep(120)
    with open("/app/health", "r") as f:
        new_health = f.read()

    if health == new_health:
        EXIT_CODE = 0
    else:
        EXIT_CODE = 1


if __name__ == "__main__":
    asyncio.run(check())
    exit(EXIT_CODE)
