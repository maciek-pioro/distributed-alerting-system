from google.cloud import firestore, pubsub_v1, logging, bigquery
from datetime import datetime
from hashlib import md5

def extract_url_and_uuid_from_msg(msg):
    ack_url = msg.text # TODO extract ack url when the mail format is known, for now assuming that text of an email consists only of the url

    tmp1 = ack_url.split('/') # ['https:', '', 'ack-server-rlvishyx4a-uc.a.run.app', '?admin=<admin_number>&uuid=<outage_uuid>']
    tmp2 = tmp1[-1].split('=') # ['?admin', '<admin_number>&uuid', '<outage_uuid>']
    uuid = tmp2[-1]        
    return (ack_url, uuid)

def find_appropriate_log(logging_client, logger_name, pattern):
    logger = logging_client.logger(logger_name)
    for entry in logger.list_entries():
        if pattern in entry.payload:
            return True
    return False



def add_service(firestore_client, bigquery_client, SERVICES_DB_NAME, SERVICES_COLLECTION_NAME, service_url, service):
    # add url to big query
    rows_to_insert = [
        {"url": service_url, "updated_at": str(datetime.now())},
    ]

    errors = bigquery_client.insert_rows_json(
        SERVICES_DB_NAME, rows_to_insert, row_ids=[None]
    )  # Make an API request.
    if errors == []:
        print("New rows have been added.")
    else:
        print("Encountered errors while inserting rows: {}".format(errors))

    # add service monitoring details to firestore
    service_digest = md5(service_url.encode("utf-8")).hexdigest()
    print("digest ", service_digest)
    doc_ref = firestore_client.collection(SERVICES_COLLECTION_NAME).document(service_digest)
    doc_ref.set(service)

    return