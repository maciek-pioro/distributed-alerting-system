import functions_framework
from google.cloud import firestore
from google.cloud import logging
import os
from datetime import datetime
import json
import rsa

PROJECT_ID = os.getenv("GCP_PROJECT")
EMAILS_SENT_COLLECTION_NAME = os.getenv("EMAIL_COLLECTION")


def decode_message(message):
    privkey_raw = os.environ.get("PRIVATE_KEY")
    pk_raw = privkey_raw.replace('\\n', '\n').encode('ascii')
    privkey = rsa.PrivateKey.load_pkcs1(pk_raw)
    dectex = rsa.decrypt(bytes.fromhex(message), privkey)
    return dectex.decode()


def get_args(request):
    json_raw = decode_message(request.script_root[1:])
    args = json.loads(json_raw)
    uuid = args["uuid"]
    admin = args["admin"]
    return uuid, admin


@functions_framework.http
def handle_request(request):
    uuid, admin = get_args(request)

    db = firestore.Client(project=PROJECT_ID)
    doc_ref = db.collection(EMAILS_SENT_COLLECTION_NAME).document(uuid)
    doc_ref.set({"ack_by": admin, "ack": True}, merge=True)

    logging_client = logging.Client()
    logger = logging_client.logger("outages")
    logger.log_text(
        json.dumps(
            {
                "service": doc_ref.get().to_dict()["url"],
                "outage": uuid,
                "event": f"{admin} admin ack {datetime.now()}",
            }
        )
    )

    return "<html><head>Thank you for acknowledging the outage.</head></html>"
