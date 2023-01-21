import os
import base64
import functions_framework
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from google.cloud import firestore
import uuid
import json


def create_email_content(client_details, event_id):
    email_content = (
        f"Your service {client_details['url']} is down.\n"
        + "Click here to acknowledge the outage: "
        + f"{os.environ.get('ACK_ENDPOINT')}/?uuid={event_id}&admin=1"
    )

    return email_content


def send_email(client_details, event_id):
    message = Mail(
        from_email=os.environ.get("EMAIL_SENDER"),
        to_emails=client_details["admin_mail1"],
        subject="Service is down",
        html_content=create_email_content(client_details, event_id),
    )
    try:
        sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
        response = sg.send(message)
        print(response.status_code)
        print(response.body)
        print(response.headers)
    except Exception as e:
        print(e)


def set_email_sent(client_details, event_id):
    db = firestore.Client(project="irio-solution")
    db.collection(os.environ.get("EMAIL_COLLECTION")).document(event_id).create(
        {
            "last_email_time": firestore.SERVER_TIMESTAMP,
            "ack": False,
            "url": client_details.get("url", "service unknown"),
            "admin_mail2": client_details["admin_mail2"],
            "allowed_response_time_minutes": client_details[
                "allowed_response_time_minutes"
            ],
        }
    )


# def queue_next_email(event_id):


# Triggered from a message on a Cloud Pub/Sub topic.
@functions_framework.cloud_event
def save_send_query_event(cloud_event):
    b64encoded = cloud_event.data["message"]["data"]
    b64decoded = base64.b64decode(b64encoded)
    client_details = json.loads(b64decoded)["message"]
    event_id = str(uuid.uuid4())
    send_email(client_details, event_id)
    set_email_sent(client_details, event_id)
