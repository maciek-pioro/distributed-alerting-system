import argparse
from hashlib import md5
import os
import asyncio
from google.cloud import firestore, bigquery
from typing import Optional

# admin_mail1: "example@gmail.com" (string)
# admin_mail2: "example@gmail.com" (string)
# alert_window_minutes: 1 (number)
# allowed_response_time_minutes: 1 (number)
# check_interval_minutes: 1 (number)
# first_bad_response_time: null (null)
# last_ok_response_time: "2023-01-23 23:39:51" (string)
# last_response_time: "2023-01-23 23:39:51"


async def main(
    service: str,
    bigquery_table: str,
    firestore_collection: str,
    admin_mail1: str,
    admin_mail2: str,
    admin_phone1: Optional[str],
    admin_phone2: Optional[str],
    check_interval_minutes: int,
    alert_window_minutes: int,
    allowed_response_time_minutes: int,
):
    bigquery_client = bigquery.Client()
    db = firestore.Client()
    service_digest = md5(service.encode("utf-8")).hexdigest()
    db.collection(firestore_collection).document(service_digest).set(
        {
            "admin_mail1": admin_mail1,
            "admin_mail2": admin_mail2,
            "admin_phone1": admin_phone1,
            "admin_phone2": admin_phone2,
            "check_interval_minutes": check_interval_minutes,
            "alert_window_minutes": alert_window_minutes,
            "allowed_response_time_minutes": allowed_response_time_minutes,
            "first_bad_response_time": None,
            "last_ok_response_time": None,
            "last_response_time": None,
        }
    )
    bigquery_client.query(
        f"INSERT INTO `{bigquery_table}` (url, updated_at) VALUES ('{service}', CURRENT_DATE())"
    ).result()
    print("Done!")


if __name__ == "__main__":
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print("GOOGLE_APPLICATION_CREDENTIALS not set. Exiting...")
        exit(1)
    parser = argparse.ArgumentParser(
        description="Add a service to the k8s cluster",
    )
    parser.add_argument("--service", type=str, help="The service to add", required=True)
    parser.add_argument("--bigquery", type=str, help="BigQuery Table", required=True)
    parser.add_argument(
        "--firestore", type=str, help="Firestore Collection", required=True
    )
    parser.add_argument("--admin1", type=str, help="Admin 1", required=True)
    parser.add_argument("--admin2", type=str, help="Admin 2", required=True)
    parser.add_argument(
        "--phone1", type=str, help="Phone 1", required=False, default=None
    )
    parser.add_argument(
        "--phone2", type=str, help="Phone 2", required=False, default=None
    )
    parser.add_argument(
        "--check_interval_minutes",
        type=int,
        help="Check interval in minutes",
        required=True,
    )
    parser.add_argument(
        "--alert_window_minutes",
        type=int,
        help="Alert window in minutes",
        required=True,
    )
    parser.add_argument(
        "--allowed_response_time_minutes",
        type=int,
        help="Allowed response time in minutes",
        required=True,
    )
    args = parser.parse_args()

    asyncio.run(
        main(
            service=args.service,
            bigquery_table=args.bigquery,
            firestore_collection=args.firestore,
            admin_mail1=args.admin1,
            admin_mail2=args.admin2,
            admin_phone1=args.phone1,
            admin_phone2=args.phone2,
            check_interval_minutes=args.check_interval_minutes,
            alert_window_minutes=args.alert_window_minutes,
            allowed_response_time_minutes=args.allowed_response_time_minutes,
        )
    )
