import rsa
import os
import functions_framework
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from google.cloud import firestore, logging
from datetime import datetime
import json
from twilio.rest import Client as TwilioClient


def encode_message(message):
    pubkey_raw = os.environ.get("PUBLIC_KEY")
    pk_raw = pubkey_raw.replace('\\n', '\n').encode('ascii')
    pubkey = rsa.PublicKey.load_pkcs1(pk_raw)
    enctex = rsa.encrypt(message.encode(), pubkey)
    hex_message = enctex.hex()
    return hex_message


def create_url(event_id):
    json_msg = json.dumps({"uuid": event_id, "admin": 2})
    obfuscated_event = encode_message(json_msg)
    return f"{os.environ.get('ACK_ENDPOINT')}/{obfuscated_event}"


def create_message_content(event_details, event_id):
    email_content = (
            f"Your service {event_details['url']} is down.\n"
            + f"First email sent at: {str(event_details['last_email_time'])}, but left without acknowledgement.\n"
            + "Click here to acknowledge the outage: "
            + create_url(event_id)
    )

    return email_content


def send_sms(content, phone_number):
    try:
        print(f"Will try sending sms to {phone_number}")
        # Your Account SID from twilio.com/console
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        # Your Auth Token from twilio.com/console
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        from_number = os.environ.get("TWILIO_NUMBER")

        client = TwilioClient(username=account_sid, password=auth_token)

        message = client.messages.create(
            to=phone_number, from_=from_number, body=content
        )

        print(message.sid)
    except Exception as e:
        print(e)


def send_email(event_details, message_content):
    print(event_details)
    message = Mail(
        from_email=os.environ.get("EMAIL_SENDER"),
        to_emails=event_details["admin_mail2"],
        subject="Service is down",
        html_content=message_content,
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
    event_doc = (
        db.collection(os.environ.get("EMAIL_COLLECTION")).document(event_id).get()
    )

    if event_doc.exists:
        return event_doc.to_dict()
    else:
        raise Exception("Document does not exist")


def set_email_sent(event_id, logger):
    db = firestore.Client(project=os.environ.get("GCP_PROJECT"))
    db.collection(os.environ.get("EMAIL_COLLECTION")).document(event_id).set(
        {"second_email_time": firestore.SERVER_TIMESTAMP}, merge=True
    )


@functions_framework.http
def check_send_event(request):
    logging_client = logging.Client()
    logger = logging_client.logger("outages")
    try:
        args = request.args
        event_id = args["event_id"]
        service = args["service"]
        event_details = get_event_details(event_id)

        if event_details["ack"] is False:
            message_content = create_message_content(event_details, event_id)
            send_email(event_details, message_content)
            admin_phone2 = event_details.get("admin_phone2")
            if admin_phone2:
                send_sms(message_content, admin_phone2)
            else:
                print("No phone number provided")
            set_email_sent(event_id, logger)
            logger.log_text(
                json.dumps(
                    {
                        "service": service,
                        "outage": event_id,
                        "event": f"second email sent {datetime.now()}",
                    }
                )
            )

    except Exception as e:
        print(e)
        return "error", 404
    return "OK", 200
