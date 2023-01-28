import functions_framework
from google.cloud import firestore
from google.cloud import logging
import os
from datetime import datetime
import json

PROJECT_ID = os.getenv("GCP_PROJECT")
EMAILS_SENT_COLLECTION_NAME = os.getenv("EMAIL_COLLECTION")


@functions_framework.http
def handle_request(request):
    args = request.args
    uuid = args["uuid"]
    admin = args["admin"]

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
