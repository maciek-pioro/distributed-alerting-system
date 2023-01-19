from google.cloud import firestore, pubsub_v1, logging, bigquery
from datetime import datetime
from hashlib import md5

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
    admin = tmp1[0]
    uuid = tmp[-1]        
    return (ack_url, uuid, admin)

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

def remove_service(firestore_client, bigquery_client, SERVICES_DB_NAME, SERVICES_COLLECTION_NAME, service_url, service):
    # TODO
    return