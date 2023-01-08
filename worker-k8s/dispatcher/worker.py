import time
from click import option
from flask import Flask, request
from dataclasses import dataclass
import asyncio
import aiohttp
from google.cloud import firestore
import datetime

from typing import Optional

app = Flask(__name__)

NUM_WORKERS = None
WORKER_ID = None
MAX_RESPONSE_TIME_SECONDS = 10
WORKER_THREADS = []
COLLECTION = "services"
PROJECT = "irio-solution"
DB = firestore.AsyncClient(PROJECT)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def optionally_parse_date(date):
    if date is not None:
        return datetime.datetime.strptime(date, DATE_FORMAT)
    else:
        return None


@dataclass
class BaseServiceData:
    id: int
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
    ...


async def get_data_from_firestore(service_data: BaseServiceData) -> LiveServiceData:
    data = (await DB.document(COLLECTION).document(base_data.id).get()).to_dict()
    return LiveServiceData.from_dict(data.to_dict())


async def worker_coroutine(service_data: BaseServiceData):
    data = await get_data_from_firestore(service_data)
    remaining_time_seconds = (
        (datetime.datetime.now() - data.last_response_time).seconds
        if data.last_response_time
        else 0
    )
    while True:
        if remaining_time_seconds > 0:
            await asyncio.sleep(remaining_time_seconds)
        handling_time_start = time.perf_counter()
        async with aiohttp.request(
            "GET", data, allow_redirects=False, timeout=10
        ) as rq:
            now = datetime.datetime.now()
            data.last_response_time = now
            if rq.ok:
                data.last_ok_response_time = now
                await DB.collection(COLLECTION).document(data.id).update(
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
                await DB.collection(COLLECTION).document(base_data.id).update(
                    {
                        "last_response_time": format_date(data.last_response_time),
                        "first_bad_response_time": format_date(
                            data.first_bad_response_time
                        ),
                    }
                )
        handling_time_end = time.perf_counter()
        remaining_time_seconds = data.check_interval_minutes * 60 - (
            handling_time_end - handling_time_start
        )


def start_threads(jobs):
    tasks = []
    for job in jobs:
        task = asyncio.create_task(worker_coroutine(job))
        tasks.append(task)
    return tasks


def set_config():
    global NUM_WORKERS
    global WORKER_ID
    NUM_WORKERS = int(request.args.get("num_workers"))
    WORKER_ID = int(request.args.get("worker_id"))
    jobs = get_jobs()
    start_threads(jobs)


def get_config():
    global NUM_WORKERS
    global WORKER_ID
    return {"num_workers": NUM_WORKERS, "worker_id": WORKER_ID}


@app.route("/config", methods=["GET", "POST"])
def config():
    if request.method == "POST":
        return set_config()
    return get_config()


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
