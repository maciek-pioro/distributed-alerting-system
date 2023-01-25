from google.cloud import firestore, pubsub_v1, logging, bigquery
from datetime import datetime
from hashlib import md5
import json

def extract_from_msg(msg):
    # email layout
    """
        f"Your service {service_url} is down.\n"
        + "Click here to acknowledge the outage: "
        + f"{ack_endpoint')}/?uuid={event_id}&admin=1
    """

    tmp = msg.text.split("https://")
    ack_url = "https://" + tmp[-1] # tmp[-1] is the last url in the message

    tmp = ack_url.split('/') # ['https:', '', 'ack-server-rlvishyx4a-uc.a.run.app', '?admin=<admin_number>&uuid=<outage_uuid>']
    tmp = tmp[-1].split('=') # ['?admin', '<admin_number>&uuid', '<outage_uuid>']
    tmp1 = tmp[1].split('&') # ['<admin_number>', 'uuid']
    uuid = tmp1[0]
    admin = tmp[-1]        
    return (ack_url, uuid, admin)

def find_appropriate_log(logging_client, logger_name, pattern):
    logger = logging_client.logger(logger_name)
    for entry in logger.list_entries():
        if pattern in entry.payload:
            return True
    return False

def clear_test_tables(firestore_client, bigquery_client, SERVICES_DB_NAME, SERVICES_COLLECTION_NAME):
    try:
        query = f"DELETE FROM `{SERVICES_DB_NAME}` WHERE true"
        query_job = bigquery_client.query(query)
        res = query_job.result()
        print(json.dumps({"message": f"deleted rows from {SERVICES_DB_NAME}, res: {res}", "severity": "DEBUG"}))
    except Exception as e:
        print(json.dumps({"message": f"failed to delete rows from {SERVICES_DB_NAME}, err: {e}", "severity": "ERROR"}))

    docs = firestore_client.collection(SERVICES_COLLECTION_NAME).list_documents()
    for doc in docs:
        doc.delete()
    print(json.dumps({"message": f"deleted documents from {SERVICES_COLLECTION_NAME}", "severity": "DEBUG"}))


def add_service(firestore_client, bigquery_client, SERVICES_DB_NAME, SERVICES_COLLECTION_NAME, service_url, service):
    # add url to big query
    rows_to_insert = [
        {"url": service_url, "updated_at": str(datetime.now())},
    ]

    errors = bigquery_client.insert_rows_json(
        SERVICES_DB_NAME, rows_to_insert, row_ids=[None]
    )
    if errors == []:
        print("Added row to " + SERVICES_DB_NAME)
    else:
        print("Encountered errors while inserting rows: {}".format(errors))

    # add service monitoring details to firestore
    service_digest = md5(service_url.encode("utf-8")).hexdigest()
    doc_ref = firestore_client.collection(SERVICES_COLLECTION_NAME).document(service_digest)
    doc_ref.set(service)
    print("Added row to " + SERVICES_COLLECTION_NAME)

def remove_service(firestore_client, bigquery_client, SERVICES_DB_NAME, SERVICES_COLLECTION_NAME, service_url, service):
    QUERY = f'DELETE FROM `{SERVICES_DB_NAME}` WHERE url = "{service_url}"'
    query_job = bigquery_client.query(QUERY)
    rows = query_job.result() 
    return