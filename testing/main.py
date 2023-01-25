import json
import os
import sys
import time
import requests
from hashlib import md5
from google.cloud import firestore, pubsub_v1, logging, bigquery
from pymailtm import MailTm
import test_utils
from datetime import datetime
import inspect

PROJECT_ID = os.getenv("PROJECT_ID", "irio-solution")
FIRST_EMAIL_TOPIC = os.getenv("FIRST_EMAIL_TOPIC", "projects/irio-solution/topics/first-email-test")
UUIDS_COLLECTION_NAME = os.getenv("UUIDS_COLLECTION", "uuids_test")
EMAILS_SENT_COLLECTION_NAME = os.getenv("EMAILS_SENT_COLLECTION", "emails_sent_test")
SERVICES_COLLECTION_NAME = os.getenv("SERVICES_COLLECTION", "services_test")
SERVICES_DB_NAME = os.getenv("SERVICES_BQ_TABLE", "irio-solution.test.services")
TEST1 = os.getenv("TEST1", "True")
TEST2 = os.getenv("TEST2", "True")
CLEAR = os.getenv("CLEAR", "False")
TEST_SERVICE_BASE_URL = os.getenv("TEST_SERVICE_BASE_URL", "https://service-test-rlvishyx4a-lm.a.run.app/")

def e2e_continious_outage(mailTm, firestore_client, bigquery_client, logging_client):
    url = TEST_SERVICE_BASE_URL + md5(str(datetime.now()).encode("utf-8")).hexdigest()
    test_name = "e2e_continious_outage"
    acc1 = mailTm.get_account()
    address1 = acc1.address
    acc2 = mailTm.get_account()
    address2 = acc2.address
    service = {
        "check_interval_minutes": 1,
        "alert_window_minutes": 1,
        "allowed_response_time_minutes": 30,
        "admin_mail1": address1,
        "admin_mail2": address2
    }
    # add service to bigquery and firestore
    test_utils.add_service(firestore_client, bigquery_client, SERVICES_DB_NAME, SERVICES_COLLECTION_NAME, url, service)

    n = 2
    # sleep for 4 minutes
    print(json.dumps({"test_name": test_name, "message": f"Sleep for {n} minutes", "severity": "INFO"}))
    time.sleep(60*n)
    print(json.dumps({"test_name": test_name, "message": f"Woke up from {n} minutes nap", "severity": "INFO"}))

    # wait for an email with outage info and link to come
    print(json.dumps({"test_name": test_name, "message": f"Waiting for a message to {address1}.", "severity": "DEBUG"}))
    msgs = []
    tries = 0
    while len(msgs) == 0 and tries <= 20:
        time.sleep(15)
        msgs = acc1.get_messages()
        tries += 1
    if len(msgs) == 0:
        print(json.dumps({"test_name": test_name, "message": f"Did not receive an email to {address1}.", "severity": "ERROR"}))
        sys.exit(1)
    else:
        if len(msgs) > 1:
            print(json.dumps({"message": f"msgs received (should be only one): {msgs}", "severity": "DEBUG"}))
        msg = msgs[-1]
    
    # extract from email
    try:
        (ack_url, uuid, admin) = test_utils.extract_from_msg(msg)
        print(json.dumps({"test_name": test_name, "message": f"Extracted from email. ack_url: {ack_url}, uuid: {uuid}, admin: {admin}", "severity": "INFO"}))
    except Exception:
        print(json.dumps({"test_name": test_name, "message": f"Could not get ack link from email. Email: {msg}", "severity": "ERROR"}))
        sys.exit(1)
    
    # check if first_sender properly logged
    if not test_utils.find_appropriate_log(logging_client, "outages", f"Service {url} outage {uuid}: first email sent"):
        print(json.dumps({"test_name": test_name, "message": f"Could not find log about first email sent. Url: {url}, uuid: {uuid}", "severity": "ERROR"}))
    else:
        print(json.dumps({"test_name": test_name, "message": f"Send of first email logged properly. Url: {url}, uuid: {uuid}", "severity": "INFO"}))

    # click the link
    res = requests.get(ack_url)
    if res.status_code != requests.codes.ok:
        print(json.dumps({"test_name": test_name, "message": f"Could not request ack link. Res: {res}, ack_url: {ack_url}", "severity": "ERROR"}))
        sys.exit(1)
    else:
        print(json.dumps({"test_name": test_name, "message": f"Clicked the link {ack_url}", "severity": "INFO"}))

    # check if ack server propely logged
    if not test_utils.find_appropriate_log(logging_client, "outages", f"Service {url} outage {uuid}: 1 admin ack"):
        print(json.dumps({"test_name": test_name, "message": f"Could not find log about first admin acknowlegdment sent. Url: {url}, uuid: {uuid}", "severity": "ERROR"}))
    else:
        print(json.dumps({"test_name": test_name, "message": f"First admin acknowlegdment logged properly. Url: {url}, uuid: {uuid}", "severity": "INFO"}))


    # check that uuid is no longer present in emails_sent store
    doc_ref = firestore_client.collection(EMAILS_SENT_COLLECTION_NAME).document(uuid).get().to_dict()
    if doc_ref and doc_ref["ack"] and doc_ref["ack_by"] == "1" :
        print(json.dumps({"test_name": test_name, "message": f"Acknowledgement noted in {EMAILS_SENT_COLLECTION_NAME} collection.", "severity": "INFO"}))
    else:
        print(json.dumps({"test_name": test_name, "message": f"Acknowledgement wasn't noted in {EMAILS_SENT_COLLECTION_NAME} collection.", "severity": "ERROR"}))

    
    n = 2
    # sleep for 4 minutes
    print(json.dumps({"test_name": test_name, "message": f"Sleep for {n} minutes", "severity": "INFO"}))
    time.sleep(60*n)
    print(json.dumps({"test_name": test_name, "message": f"Woke up from {n} minutes nap", "severity": "INFO"}))

    # assert that admin has not received new emails after they've already acknowledged the outage
    msgs = acc1.get_messages()
    if len(msgs) > 1:
        print(json.dumps({"test_name": test_name, "message": f"Sent too many ({len(msgs)}) emails to admin {address1} after they've already clicked the link.", "severity": "ERROR"}))
    else:
        print(json.dumps({"test_name": test_name, "message": f"Sent only one email to admin {address1}.", "severity": "INFO"}))
        

    test_utils.clear_test_tables(firestore_client, bigquery_client, SERVICES_DB_NAME, SERVICES_COLLECTION_NAME)
    print(json.dumps({"test_name": test_name, "message": f"Test done.", "severity": "INFO"}))


def e2e_outage_shorted_than_alerting_window(mailTm, firestore_client, bigquery_client, logging_client):
    # set up test service
    endpoint = "/test_endpoint"
    body = {"name": endpoint, "down_time_seconds": 3*60}
    requests.post(TEST_SERVICE_BASE_URL + endpoint, json=body)

    url = TEST_SERVICE_BASE_URL + endpoint
    test_name = "e2e_outage_shorted_than_alerting_window"

    acc1 = mailTm.get_account()
    address1 = acc1.address
    acc2 = mailTm.get_account()
    address2 = acc2.address
    service = {
        "check_interval_minutes": 1,
        "alert_window_minutes": 6,
        "allowed_response_time_minutes": 10,
        "admin_mail1": address1,
        "admin_mail2": address2
    }

    # add service to bigquery and firestore
    test_utils.add_service(firestore_client, bigquery_client, SERVICES_DB_NAME, SERVICES_COLLECTION_NAME, url, service)

    # sleep for 15 minutes
    time.sleep(60*12)

     # obtain outage uuid generated by first_sender
    url_digest = md5((url).encode("utf-8")).hexdigest()
    doc_ref = firestore_client.collection(UUIDS_COLLECTION_NAME).document(url_digest)
    try:
        uuid = doc_ref.uuid
    except Exception:
        print(json.dumps({"test_name": test_name, "message": f"Could not find uuid in uuids store. Url: {url}, Url_digest: {url_digest}", "severity": "ERROR"}))
        uuid = None

    # ASSERT THAT OUTAGE WASN'T PICKED UP BY THE ALERTING SYSTEM

    # check that first_sender didn't log
    if test_utils.find_appropriate_log(logging_client, "outages", f"Email about outage {uuid} sent to the first admin"): # TODO consult logging content
        print(json.dumps({"test_name": test_name, "message": f"Found log about first email sent. Url: {url}, uuid: {uuid}", "severity": "ERROR"}))

    # assert that admin has not received any emails
    msgs = acc1.get_messages()
    if len(msgs) > 1:
        print(json.dumps({"test_name": test_name, "message": f"Received email about outage didn't exceed alerting_window emails to admin {address1} after they've already clicked the link. Messages {msgs}", "severity": "ERROR"}))

def main():
    mailTm = MailTm()
    firestore_client = firestore.Client(project=PROJECT_ID)
    bigquery_client = bigquery.Client()
    logging_client = logging.Client()
    if(CLEAR == "True"):
        test_utils.clear_test_tables(firestore_client, bigquery_client, SERVICES_DB_NAME, SERVICES_COLLECTION_NAME)
    if(TEST1 == "True"):
        e2e_continious_outage(mailTm, firestore_client, bigquery_client, logging_client)
    if(TEST2 == "True"):
        e2e_outage_shorted_than_alerting_window(mailTm, firestore_client, bigquery_client, logging_client)

if __name__ == "__main__":
    main()
    