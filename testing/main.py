import json
import os
import sys
import time
import requests
from hashlib import md5
from google.cloud import firestore, pubsub_v1, logging, bigquery
from pymailtm import MailTm
import test_utils
import datetime

PROJECT_ID = os.getenv("PROJECT_ID", "irio-solution")
FIRST_EMAIL_TOPIC = os.getenv("FIRST_EMAIL_TOPIC", "projects/irio-solution/topics/first_email_test")
UUIDS_COLLECTION_NAME = os.getenv("UUIDS_COLLECTION", "uuids")
EMAILS_SENT_COLLECTION_NAME = os.getenv("EMAILS_SENT_COLLECTION", "emails_sent")
SERVICES_COLLECTION_NAME = os.getenv("SERVICES_COLLECTION", "services_test")
SERVICES_DB_NAME = os.getenv("SERVICES_BQ_TABLE", "irio-solution.test.services")
BAD_URL = "404"


def first_admin_reponds(firestore_client, publisher_client, FIRST_EMAIL_TOPIC_path, logging_client):
    # setup temporary email
    tm = MailTm()
    acc = tm.get_account()
    temp_email_address = acc.address

    # send message about outage to first_sender via pub/sub
    msg = {"url": BAD_URL, "email_address": temp_email_address, "allowed_response_time_in_seconds": 60*60} # TODO and other things that email_sender needs
    data = json.dumps(msg)
    try:
        publisher_client.publish(FIRST_EMAIL_TOPIC_path, data).result()
    except Exception as e:
        print(json.dumps({"message": f"Could not publish msg into topic {FIRST_EMAIL_TOPIC_path}: {e}", "severity": "ERROR"}))
        sys.exit(1)

    # obtain outage uuid generated by first_sender
    time.sleep(60)
    doc_ref = firestore_client.collection(UUIDS_COLLECTION_NAME).document(BAD_URL)
    uuid = doc_ref.uuid

    # check if first_sender properly logged
    if not test_utils.find_appropriate_log(logging_client, "outages", f"Email about outage {uuid} sent to the first admin"): # TODO consult logging content
        print(json.dumps({"message": f"ERROR: Could not find log about first email sent. Url: {BAD_URL}, uuid: {uuid}", "severity": "ERROR"}))

    # wait for an email with outage info and link to come
    msg = acc.wait_for_message()
    try:
        (ack_url, uuid) = test_utils.extract_url_and_uuid_from_msg(msg)
    except Exception:
        print(json.dumps({"message": f"Could not get ack link from email. Email: {msg}", "severity": "ERROR"}))
        sys.exit(1)

    # click the link
    res = requests.get(ack_url)
    if not res.ok():
        print(json.dumps({"message": f"Could not request ack link. Res: {res}, ack_url: {ack_url}", "severity": "ERROR"}))
        sys.exit(1)

    # check if ack server propely logged
    if not find_appropriate_log(logging_client, "outages", f"Admin 1 acknowledged outage {uuid}"):
        print(json.dumps({"message": f"Could not find log about first admin acknowlegdment sent. Url: {BAD_URL}, uuid: {uuid}", "severity": "ERROR"}))

    # check that uuid is no longer present in emails_sent store
    if firestore_client.collection(EMAILS_SENT_COLLECTION_NAME).document(uuid).get().to_dict() is not None:
        print(json.dumps({"message": f"ERROR: Uuid {uuid} still present in {EMAILS_SENT_COLLECTION_NAME} db after admin acknowlegded the outage.", "severity": "ERROR"}))

def e2e_continious_outage(mailTm, firestore_client, bigquery_client, logging_client):
    acc1 = mailTm.get_account()
    address1 = acc1.address
    acc2 = mailTm.get_account()
    address2 = acc2.address
    url = BAD_URL
    service = {
        "check_interval_minutes": 1,
        "alert_window_minutes": 2,
        "allowed_response_time_minutes": 10,
        "admin_mail1": address1,
        "admin_mail2": address2
    }
    # add service to bigquery and firestore
    test_utils.add_service(firestore_client, bigquery_client, SERVICES_DB_NAME, SERVICES_COLLECTION_NAME, url, service)

    # sleep for 10 minutes
    time.sleep(60*10)

     # obtain outage uuid generated by first_sender
    url_digest = md5((url).encode("utf-8")).hexdigest()
    doc_ref = firestore_client.collection(UUIDS_COLLECTION_NAME).document(url_digest)
    uuid = doc_ref.uuid

    # check if first_sender properly logged
    if not test_utils.find_appropriate_log(logging_client, "outages", f"Email about outage {uuid} sent to the first admin"): # TODO consult logging content
        print(json.dumps({"message": f"ERROR: Could not find log about first email sent. Url: {url}, uuid: {uuid}", "severity": "ERROR"}))

    # wait for an email with outage info and link to come
    msg = acc1.wait_for_message()
    try:
        (ack_url, uuid) = test_utils.extract_url_and_uuid_from_msg(msg)
    except:
        print(json.dumps({"message": f"Could not get ack link from email. Email: {msg}", "severity": "ERROR"}))
        sys.exit(1)

    # click the link
    res = requests.get(ack_url)
    if not res.ok():
        print(json.dumps({"message": f"Could not request ack link. Res: {res}, ack_url: {ack_url}", "severity": "ERROR"}))
        sys.exit(1)

    # check if ack server propely logged
    if not test_utils.find_appropriate_log(logging_client, "outages", f"Admin 1 acknowledged outage {uuid}"):
        print(json.dumps({"message": f"Could not find log about first admin acknowlegdment sent. Url: {url}, uuid: {uuid}", "severity": "ERROR"}))

    # check that uuid is no longer present in emails_sent store
    if firestore_client.collection(EMAILS_SENT_COLLECTION_NAME).document(uuid).get().to_dict() is not None:
        print(json.dumps({"message": f"ERROR: Uuid {uuid} still present in {EMAILS_SENT_COLLECTION_NAME} db after admin acknowlegded the outage.", "severity": "ERROR"}))
    
    # sleep for 10 minutes
    time.sleep(60*10)

    # assert that admin has not received new emails after they've already acknowledged the outage
    msgs = acc1.get_messages()
    if len(msgs) > 1:
        print(json.dumps({"message": f"Sent too many ({len(msgs)}) emails to admin {address1} after they've already clicked the link.", "severity": "ERROR"}))

    test_utils.remove_service(firestore_client, bigquery_client, SERVICES_DB_NAME, SERVICES_COLLECTION_NAME, url, service)

def e2e_outage_shorted_than_alerting_window(mailTm, firestore_client, bigquery_client, logging_client):
    url = "some_url" # TODO url that doesn't respond for 5 minutes and then works correctly
    acc1 = mailTm.get_account()
    address1 = acc1.address
    acc2 = mailTm.get_account()
    address2 = acc2.address
    service = {
        "check_interval_minutes": 1,
        "alert_window_minutes": 10,
        "allowed_response_time_minutes": 10,
        "admin_mail1": address1,
        "admin_mail2": address2
    }

    # add service to bigquery and firestore
    test_utils.add_service(firestore_client, bigquery_client, SERVICES_DB_NAME, SERVICES_COLLECTION_NAME, url, service)

    # sleep for 15 minutes
    time.sleep(60*15)

     # obtain outage uuid generated by first_sender
    url_digest = md5((url).encode("utf-8")).hexdigest()
    doc_ref = firestore_client.collection(UUIDS_COLLECTION_NAME).document(url_digest)
    uuid = doc_ref.uuid

    # ASSERT THAT OUTAGE WASN'T PICKED UP BY THE ALERTING SYSTEM

    # check that first_sender didn't log
    if test_utils.find_appropriate_log(logging_client, "outages", f"Email about outage {uuid} sent to the first admin"): # TODO consult logging content
        print(json.dumps({"message": f"ERROR: Found log about first email sent. Url: {url}, uuid: {uuid}", "severity": "ERROR"}))

    # assert that admin has not received any emails
    msgs = acc1.get_messages()
    if len(msgs) > 1:
        print(json.dumps({"message": f"Received email about outage didn't exceed alerting_window emails to admin {address1} after they've already clicked the link.", "severity": "ERROR"}))

def main():
    mailTm = MailTm()
    firestore_client = firestore.Client(project=PROJECT_ID)
    bigquery_client = bigquery.Client()
    logging_client = logging.Client()
    publisher_client = pubsub_v1.PublisherClient()
    FIRST_EMAIL_TOPIC_PATH = publisher_client.topic_path(PROJECT_ID, FIRST_EMAIL_TOPIC)
    e2e_continious_outage(mailTm, firestore_client, bigquery_client, logging_client)
    e2e_outage_shorted_than_alerting_window(mailTm, firestore_client, bigquery_client, logging_client)

if __name__ == "__main__":
    main()