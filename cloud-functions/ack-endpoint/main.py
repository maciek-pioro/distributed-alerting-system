import functions_framework
from google.cloud import firestore
from google.cloud import logging


@functions_framework.http
def handle_request(request):
    args = request.args
    uuid = args["uuid"]
    admin = args["admin"]
    db = firestore.Client(project='irio-solution')
    db.collection(u'emails_sent').document(u"document_to_delete").delete()
    logging_client = logging.Client()
    logger = logging_client.logger("outages")
    logger.log_text(f"Admin {admin} acknowledged outage {uuid}.")
    return '<html><head>Thank you for acknowledging the outage.</head></html>'