import json
import time
from flask import Flask, request
from dataclasses import dataclass
import asyncio
import aiohttp
from google.cloud import firestore, bigquery, pubsub_v1
import datetime
import threading
from multiprocessing import Process

from typing import Optional

app = Flask(__name__)

# NUM_WORKERS = None
# WORKER_ID = None
MIN_SERVICE_ID = None
MAX_SERVICE_ID = None
MAX_RESPONSE_TIME_SECONDS = 10
WORKER_THREADS = []
COLLECTION = "services"
PROJECT = "irio-solution"
# DB = firestore.AsyncClient(PROJECT)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
BQ_CLIENT = bigquery.Client()
MAIN_THREAD = None
TASKS = []
FIRST_EMAIL_TOPIC = "projects/irio-solution/topics/first_email"


def optionally_parse_date(date):
    if date is not None:
        return datetime.datetime.strptime(date, DATE_FORMAT)
    else:
        return None


@dataclass
class BaseServiceData:
    id_: int
    url: str


@dataclass
class LiveServiceData:
    first_bad_response_time: Optional[datetime.datetime]
    last_ok_response_time: Optional[datetime.datetime]
    last_response_time: Optional[datetime.datetime]
    check_interval_minutes: int
    alert_window_minutes: int
    allowed_response_time_minutes: int
    admin_mail1: str
    admin_mail2: str

    @classmethod
    def from_dict(cls, dict) -> "LiveServiceData":
        return cls(
            first_bad_response_time=optionally_parse_date(
                dict.get("first_bad_response_time")
            ),
            last_ok_response_time=optionally_parse_date(
                dict.get("last_ok_response_time")
            ),
            last_response_time=optionally_parse_date(dict.get("last_response_time")),
            check_interval_minutes=dict["check_interval_minutes"],
            alert_window_minutes=dict["alert_window_minutes"],
            allowed_response_time_minutes=dict["allowed_response_time_minutes"],
            admin_mail1=dict["admin_mail1"],
            admin_mail2=dict["admin_mail2"],
        )

    def to_dict(self):
        return {
            "first_bad_response_time": format_date(self.first_bad_response_time)
            if self.first_bad_response_time
            else None,
            "last_ok_response_time": format_date(self.last_ok_response_time)
            if self.last_ok_response_time
            else None,
            "check_interval_minutes": self.check_interval_minutes,
            "alert_window_minutes": self.alert_window_minutes,
            "allowed_response_time_minutes": self.allowed_response_time_minutes,
            "admin_mail1": self.admin_mail1,
            "admin_mail2": self.admin_mail2,
        }


def parse_date(date):
    return datetime.datetime.strptime(date, DATE_FORMAT)


def format_date(date):
    return datetime.datetime.strftime(date, DATE_FORMAT)


def get_jobs():
    optional_max_clause = f"and id < {MAX_SERVICE_ID}" if MAX_SERVICE_ID != -1 else ""
    res = BQ_CLIENT.query(
        f"SELECT id, url FROM `irio-solution.production.services` where id >= {MIN_SERVICE_ID} {optional_max_clause}"
    ).result()
    return [BaseServiceData(id_=row[0], url=row[1]) for row in res]


async def get_data_from_firestore(service_data: BaseServiceData, db) -> LiveServiceData:
    data = (
        await db.collection(COLLECTION).document(str(service_data.id_)).get()
    ).to_dict()
    return LiveServiceData.from_dict(data)


def seconds_until_next_update(
    last_update: Optional[datetime.datetime], check_interval_minutes: int
):
    if last_update is None:
        return 0
    next_update = last_update + datetime.timedelta(minutes=check_interval_minutes)
    now = datetime.datetime.now()
    if next_update < now:
        return 0
    return (next_update - now).seconds


async def worker_coroutine(
    service_data: BaseServiceData,
    db: firestore.AsyncClient,
    publisher: pubsub_v1.PublisherClient,
):
    try:
        data = await get_data_from_firestore(service_data, db)
        remaining_time_seconds = seconds_until_next_update(
            data.last_response_time, data.check_interval_minutes
        )
        print(remaining_time_seconds)
        while True:
            if remaining_time_seconds > 0:
                print(
                    f"Waiting {remaining_time_seconds} seconds for service {service_data.id_} ({service_data.url})"
                )
                await asyncio.sleep(remaining_time_seconds)
                print("Woke up")
            handling_time_start = time.perf_counter()
            
            try:
                async with aiohttp.request(
                    "GET",
                    service_data.url,
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=MAX_RESPONSE_TIME_SECONDS),
                ) as rq:
                    status_ok = rq.ok
            except asyncio.exceptions.TimeoutError:
                status_ok = False

            now = datetime.datetime.now()
            data.last_response_time = now
            if status_ok:
                data.last_ok_response_time = now
                await db.collection(COLLECTION).document(
                    str(service_data.id_)
                ).update(
                    {
                        "last_response_time": format_date(data.last_response_time),
                        "last_ok_response_time": format_date(
                            data.last_ok_response_time
                        ),
                    }
                )
            else:
                if data.first_bad_response_time is None or (
                    data.last_ok_response_time is not None
                    and data.last_ok_response_time > data.first_bad_response_time
                ):
                    data.first_bad_response_time = now
                await db.collection(COLLECTION).document(
                    str(service_data.id_)
                ).update(
                    {
                        "last_response_time": format_date(data.last_response_time),
                        "first_bad_response_time": format_date(
                            data.first_bad_response_time
                        ),
                    }
                )
                if now - data.first_bad_response_time > datetime.timedelta(
                    minutes=data.alert_window_minutes
                ):
                    print(
                        f"Sending alert for service {service_data.id_} ({service_data.url})"
                    )

            handling_time_end = time.perf_counter()
            print(f"Handling time: {handling_time_end - handling_time_start} seconds")
            remaining_time_seconds = int(
                data.check_interval_minutes * 60
                - (handling_time_end - handling_time_start)
            )

    except asyncio.CancelledError as e:
        print(f"Cancelled service {service_data.id_} ({service_data.url})")
        raise e


def start_coroutines(jobs, db, publisher):
    tasks = []
    for job in jobs:
        task = asyncio.create_task(worker_coroutine(job, db, publisher))
        tasks.append(task)
    return tasks


def kill_current_tasks():
    global TASKS
    for task in TASKS:
        task.cancel()
    TASKS = []


async def main(jobs):
    db = firestore.AsyncClient(PROJECT)
    publisher = pubsub_v1.PublisherClient()

    global TASKS
    try:
        TASKS = start_coroutines(jobs, db, publisher)
        await asyncio.gather(*TASKS)
    except asyncio.CancelledError:
        print("Finito")


def worker_thread():
    kill_current_tasks()
    jobs = get_jobs()
    # global BQ_CLIENT
    # BQ_CLIENT = bigquery.Client(PROJECT)
    # loop = asyncio.new_event_loop()
    # loop.run_until_complete(main(jobs))
    asyncio.run(main(jobs))


def set_config():
    global MIN_SERVICE_ID
    global MAX_SERVICE_ID
    new_min = int(request.args.get("min_service_id"))
    new_max = int(request.args.get("max_service_id"))
    if new_min != MIN_SERVICE_ID or new_max != MAX_SERVICE_ID:
        set_new_config = True
    else:
        set_new_config = False
    MIN_SERVICE_ID = new_min
    MAX_SERVICE_ID = new_max
    return set_new_config


@app.route("/config", methods=["GET"])
def get_config():
    return {"min_service_id": MIN_SERVICE_ID, "max_service_id": MAX_SERVICE_ID}


@app.route("/schedule", methods=["POST"])
def schedule():
    if set_config():
        threading.Thread(target=worker_thread).start()
    return "OK", 202


# @app.route("/config", methods=["GET", "POST"])
# def config():
#     if request.method == "POST":
#         set_config()
#         threading.Thread(target=worker_thread).start()
#         return "OK"
#         # return set_config()
#     return get_config()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
