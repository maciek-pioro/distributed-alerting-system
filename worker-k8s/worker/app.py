from hashlib import md5
import json
import time
from flask import Flask, request
from dataclasses import dataclass
import asyncio
import aiohttp
from google.cloud import firestore, bigquery, pubsub_v1
import datetime
import threading
import os
from typing import Optional

app = Flask(__name__)

MAX_RESPONSE_TIME_SECONDS = 10
COLLECTION = os.getenv("SERVICES_COLLECTION", "test_services")
PROJECT = "irio-solution"
DB = firestore.AsyncClient(PROJECT)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
BQ_CLIENT = bigquery.Client()
MAIN_THREAD = None
TASKS = []
FIRST_EMAIL_TOPIC = os.getenv(
    "FIRST_EMAIL_TOPIC", "projects/irio-solution/topics/first-email-test"
)


def optionally_parse_date(date):
    if date is not None:
        return datetime.datetime.strptime(date, DATE_FORMAT)
    else:
        return None


@dataclass
class LiveServiceData:
    first_bad_response_time: Optional[datetime.datetime]
    last_ok_response_time: Optional[datetime.datetime]
    last_response_time: Optional[datetime.datetime]
    last_alert_time: Optional[datetime.datetime]
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
            last_alert_time=optionally_parse_date(dict.get("last_alert_time")),
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


async def get_data_from_firestore(service_digest: str, db) -> LiveServiceData:
    firestore_dict = (
        await db.collection(COLLECTION).document(service_digest).get()
    ).to_dict()
    if firestore_dict is None:
        raise Exception(f"Service (digest: {service_digest}) not found in firestore")
    print(service_digest)
    print("fs_dict", firestore_dict)
    return LiveServiceData.from_dict(firestore_dict)


def seconds_until_next_update(
    last_update: Optional[datetime.datetime], check_interval_minutes: int
):
    if last_update is None:
        return 0
    next_update = last_update + datetime.timedelta(minutes=check_interval_minutes)
    now = datetime.datetime.utcnow()
    if next_update < now:
        return 0
    return (next_update - now).seconds


async def worker_coroutine(
    service_url: str,
    db: firestore.AsyncClient,
    publisher: pubsub_v1.PublisherClient,
):
    service_digest = md5(service_url.encode("utf-8")).hexdigest()
    while True:
        try:
            data = await get_data_from_firestore(service_digest, db)
            break
        except Exception as e:
            print(f"Error getting data from firestore for service {service_url}: {e}")
            await asyncio.sleep(60)
    remaining_time_seconds = seconds_until_next_update(
        data.last_response_time, data.check_interval_minutes
    )
    print(remaining_time_seconds)
    while True:
        if remaining_time_seconds > 0:
            print(f"Waiting {remaining_time_seconds} seconds for service {service_url}")
            await asyncio.sleep(remaining_time_seconds)
            print(f"Woke up for service {service_url}")

        handling_time_start = time.perf_counter()

        try:
            print(f"sending request for service {service_url}")
            async with aiohttp.request(
                "GET",
                service_url,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=MAX_RESPONSE_TIME_SECONDS),
            ) as rq:
                status_ok = rq.ok
        except asyncio.exceptions.TimeoutError:
            status_ok = False

        now = datetime.datetime.utcnow()
        data.last_response_time = now
        if status_ok:
            data.last_ok_response_time = now
            await db.collection(COLLECTION).document(service_digest).update(
                {
                    "last_response_time": format_date(data.last_response_time),
                    "last_ok_response_time": format_date(data.last_ok_response_time),
                }
            )
        else:
            if data.first_bad_response_time is None or (
                data.last_ok_response_time is not None
                and data.last_ok_response_time > data.first_bad_response_time
            ):
                data.first_bad_response_time = now
            await db.collection(COLLECTION).document(service_digest).update(
                {
                    "last_response_time": format_date(data.last_response_time),
                    "first_bad_response_time": format_date(
                        data.first_bad_response_time
                    ),
                }
            )
            if now - data.first_bad_response_time > datetime.timedelta(
                minutes=data.alert_window_minutes
            ) and (
                data.last_alert_time is None
                or (data.last_alert_time < data.first_bad_response_time)
            ):
                print(f"Sending alert for service {service_url} on topic {FIRST_EMAIL_TOPIC}")
                await publisher.publish(
                    FIRST_EMAIL_TOPIC,
                    data=json.dumps(
                        {
                            "message": {
                                "admin_mail1": data.admin_mail1,
                                "admin_mail2": data.admin_mail2,
                                "url": service_url,
                                "allowed_response_time_minutes": data.allowed_response_time_minutes,
                            }
                        }
                    ).encode("utf-8"),
                )
                data.last_alert_time = now
                await db.collection(COLLECTION).document(service_digest).update(
                    {
                        "last_alert_time": format_date(now),
                    }
                )
        handling_time_end = time.perf_counter()
        print(f"Handling time: {handling_time_end - handling_time_start} seconds")
        remaining_time_seconds = int(
            data.check_interval_minutes * 60 - (handling_time_end - handling_time_start)
        )


SERVICES_MUTEX = threading.Lock()
SERVICE_TASK_MAP = {}
SERVICE_WAITLIST = []
is_awaiter_running = False


async def starter_coroutine():
    while True:
        await asyncio.sleep(5)
        with SERVICES_MUTEX:
            while len(SERVICE_WAITLIST) > 0:
                waiting_item = SERVICE_WAITLIST.pop()
                SERVICE_TASK_MAP[waiting_item] = asyncio.create_task(
                    worker_coroutine(waiting_item, DB, None)
                )

            for service_url in SERVICE_TASK_MAP:
                if (
                    SERVICE_TASK_MAP[service_url].done()
                    or SERVICE_TASK_MAP[service_url].cancelled()
                ):
                    SERVICE_TASK_MAP[service_url] = asyncio.create_task(
                        worker_coroutine(service_url, DB, None)
                    )


def awaiter_thread():
    global is_awaiter_running
    asyncio.run(starter_coroutine())
    is_awaiter_running = False


def start_awaiter_if_needed():
    global is_awaiter_running
    if not is_awaiter_running:
        is_awaiter_running = True
        threading.Thread(target=awaiter_thread).start()


@app.route("/add", methods=["POST"])
def add_services():
    services = request.json["services"]
    for service in services:
        if service not in SERVICE_TASK_MAP:
            SERVICE_WAITLIST.append(service)
    start_awaiter_if_needed()
    return "OK", 202


@app.route("/remove", methods=["POST"])
def remove_services():
    with SERVICES_MUTEX:
        services = request.json["services"]
        for service in services:
            if service in SERVICE_TASK_MAP:
                SERVICE_TASK_MAP[service].cancel()
                del SERVICE_TASK_MAP[service]
    return "OK", 200


@app.route("/remove_all", methods=["POST"])
def remove_all():
    with SERVICES_MUTEX:
        for service, task in SERVICE_TASK_MAP.items():
            task.cancel()
            del SERVICE_TASK_MAP[service]
    return "OK", 200


@app.route("/services", methods=["GET"])
def list_services():
    return {"services": list(SERVICE_TASK_MAP.keys())}


@app.route("/health", methods=["GET"])
def healthcheck():
    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
