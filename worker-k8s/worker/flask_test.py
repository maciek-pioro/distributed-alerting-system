from flask import Flask, request
import time
import threading
import asyncio
import os
import sys

app = Flask(__name__)


async def thread_function(sleep_time, num):
    # try:
    while True:
        print(num)
        await asyncio.sleep(sleep_time)

    # except asyncio.CancelledError:
    #     # runs shell command
    #     os.system("touch success")


async def gather(tds):
    await asyncio.gather(*tds)


go_to_sleep = False
# loop = asyncio.new_event_loop()
TASKS = []

# @app.route("/sleep", methods=["POST"])
# def sleep():
#     global go_to_sleep
#     go_to_sleep = True
#     return {"message": "Accepted"}, 202


@app.route("/kill_tasks", methods=["POST"])
def kill():
    for t in TASKS:
        # print("Cancelling", t)
        t.cancel()
    return "ok"
    # global go_to_sleep
    # go_to_sleep = True
    # return {"message": "Accepted"}, 202


# async def main(num):
#     global TASKS
#     threads_count = 5
#     sleep_time = 1
#     tds = [
#         asyncio.create_task(thread_function(sleep_time, num))
#         for _ in range(threads_count)
#     ]
#     TASKS = tds
#     await asyncio.gather(*tds)


def run_tasks(num):
    global TASKS
    threads_count = 5
    sleep_time = 1
    tds = [
        asyncio.create_task(thread_function(sleep_time, num))
        for _ in range(threads_count)
    ]
    TASKS = tds
    return TASKS


NUM = 1


@app.route("/start_task", methods=["POST"])
def start_task():
    # data = request.get_json()
    data = {"x": "d"}
    global NUM
    NUM += 1

    def run_coroutines(num):
        asyncio.run(asyncio.gather(*run_tasks(num)))
        print("Gathered")

    # def long_running_task(**kwargs):
    #     loop = asyncio.new_event_loop()
    #     threads_count = 2
    #     sleep_time = 1
    #     tds = []
    #     # loop = asyncio.get_event_loop()
    #     tds = [
    #         asyncio.run_coroutine_threadsafe(thread_function(sleep_time), loop)
    #         for _ in range(threads_count)
    #     ]
    #     global TASKS
    #     TASKS = tds
    #     counter = 1
    #     while True:
    #         print(len(tds))
    #         print(tds[0].cancelled())
    #         print(tds[0].done())
    #         time.sleep(1)
    #         print(counter)
    #         counter += 1
    #         if all(map(lambda t: t.done(), tds)):
    #             break
    #     print("finished")
    # for t in tds:
    #     if t.done():
    #         tds.remove(t)
    # loop.run_forever()
    # if go_to_sleep == True:
    #     print("Stopping long task")
    #     for t in tds:
    #         t.cancel()
    #     break
    # asyncio.run(gather(tds))
    # your_params = kwargs.get("post_data", {})
    # print("Starting long task")
    # print("Your params:", your_params)
    # for _ in range(10):
    #     time.sleep(1)
    #     print(".")

    threading.Thread(target=run_coroutines, args=[NUM]).start()
    return {"message": "Accepted"}, 202


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
