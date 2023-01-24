import os
import functions_framework
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from google.cloud import firestore


def create_email_content(event_details, event_id):
    email_content = (
            f"Your service {event_details['url']} is down.\n"
            + f"First email sent at: {str(event_details['last_email_time'])}, but left without acknowledgement.\n"
            + "Click here to acknowledge the outage: "
            + f"{os.environ.get('ACK_ENDPOINT')}/?uuid={event_id}&admin=2"
    )

    return email_content


def send_email(event_details, event_id):
    message = Mail(
        from_email=os.environ.get("EMAIL_SENDER"),
        to_emails=event_details["admin_mail2"],
        subject="Service is down",
        html_content=create_email_content(event_details, event_id),
    )
    try:
        sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
        response = sg.send(message)
        print(response.status_code)
        print(response.body)
        print(response.headers)
    except Exception as e:
        print(e)


def get_event_details(event_id):
    db = firestore.Client(project=os.environ.get("GCP_PROJECT"))
    event_doc = db.collection(os.environ.get("EMAILS_SENT_COLLECTION")).document(event_id).get()

    if event_doc.exists:
        return event_doc.to_dict()
    else:
        raise Exception("Document does not exist")


def set_email_sent(event_id):
    db = firestore.Client(project=os.environ.get("GCP_PROJECT"))
    db.collection(os.environ.get("EMAIL_COLLECTION")).document(event_id).set(
        {"second_email_time": firestore.SERVER_TIMESTAMP}, merge=True)


@functions_framework.cloud_event
def check_send_event(request):
    try:
        args = request.args
        event_id = args['event_id']
        event_details = get_event_details(event_id)

        if event_details['ack'] is False:
            send_email(event_details, event_id)
            set_email_sent(event_id)

    except Exception as e:
        return e, 404
