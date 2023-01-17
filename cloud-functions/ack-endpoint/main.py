import functions_framework
from google.cloud import firestore
from google.cloud import logging
import os

PROJECT_ID = os.getenv("PROJECT_ID", "irio-solution")
EMAILS_SENT_COLLECTION_NAME = os.getenv("EMAILS_SENT_COLLECTION", "emails_sent")

@functions_framework.http
def handle_request(request):
    args = request.args
    uuid = args["uuid"]
    admin = args["admin"]

    db = firestore.Client(project='irio-solution')
    db.collection(EMAILS_SENT_COLLECTION_NAME).document(uuid).delete()

    logging_client = logging.Client()
    logger = logging_client.logger("outages")
    logger.log_text(f"Admin {admin} acknowledged outage {uuid}.")
    
    return '<html><head>Thank you for acknowledging the outage.</head></html>'
    