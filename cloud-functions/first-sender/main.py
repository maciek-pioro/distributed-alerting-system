import os
import base64
import uuid
import json
import datetime
import functions_framework
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from google.cloud import firestore, tasks_v2
from google.protobuf import duration_pb2, timestamp_pb2

#
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
    db = firestore.Client(project=os.environ.get("GCP_PROJECT"))
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


def queue_next_email(client_details, event_id):
    # Create a client.
    client = tasks_v2.CloudTasksClient()

    project = os.environ.get("GCP_PROJECT")
    queue = os.environ.get("EMAIL_QUEUE")
    location = os.environ.get("GCP_REGION")
    url = os.environ.get("SECOND_SENDER_ENDPOINT")
    payload = {'event_id': event_id}
    in_seconds = client_details["allowed_response_time_minutes"] * 60
    task_name = event_id
    deadline = 5 * in_seconds

    # Construct the fully qualified queue name.
    parent = client.queue_path(project, location, queue)

    # Construct the request body.
    task = {
        "http_request": {  # Specify the type of request.
            "http_method": tasks_v2.HttpMethod.POST,
            "url": url,  # The full url path that the task will be sent to.
        }
    }
    if payload is not None:
        if isinstance(payload, dict):
            # Convert dict to JSON string
            payload = json.dumps(payload)
            # specify http content-type to application/json
            task["http_request"]["headers"] = {"Content-type": "application/json"}

        # The API expects a payload of type bytes.
        converted_payload = payload.encode()

        # Add the payload to the request.
        task["http_request"]["body"] = converted_payload

    if in_seconds is not None:
        # Convert "seconds from now" into an rfc3339 datetime string.
        d = datetime.datetime.utcnow() + datetime.timedelta(seconds=in_seconds)

        # Create Timestamp protobuf.
        timestamp = timestamp_pb2.Timestamp()
        timestamp.FromDatetime(d)

        # Add the timestamp to the tasks.
        task["schedule_time"] = timestamp

    if task_name is not None:
        # Add the name to tasks.
        task["name"] = client.task_path(project, location, queue, task_name)

    if deadline is not None:
        # Add dispatch deadline for requests sent to the worker.
        duration = duration_pb2.Duration()
        duration.FromSeconds(deadline)
        task["dispatch_deadline"] = duration

    # Use the client to build and send the task.
    response = client.create_task(request={"parent": parent, "task": task})

    print("Created task {}".format(response.name))


# Triggered from a message on a Cloud Pub/Sub topic.
@functions_framework.cloud_event
def save_send_query_event(cloud_event):
    b64encoded = cloud_event.data["message"]["data"]
    b64decoded = base64.b64decode(b64encoded)
    client_details = json.loads(b64decoded)["message"]
    event_id = str(uuid.uuid4())
    send_email(client_details, event_id)
    set_email_sent(client_details, event_id)
    queue_next_email(client_details, event_id)
