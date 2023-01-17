from kubernetes import client, config
import time
from google.cloud import bigquery
from typing import List
import requests
from uhashring import HashRing
import os

config.load_incluster_config()
CORE_API = client.CoreV1Api()
APPS_API = client.AppsV1Api()
BQ_CLIENT = bigquery.Client()
SERVICES_BQ_TABLE = os.getenv("SERVICES_BQ_TABLE", "irio-solution.test.services")


def get_services() -> List[str]:
    query = f"SELECT url FROM `{SERVICES_BQ_TABLE}`"
    urls = [row[0] for row in BQ_CLIENT.query(query).result()]
    return urls


def get_ready_workers():
    pods = CORE_API.list_namespaced_pod("default")
    res = []
    for pod in pods.items:
        if (
            pod.metadata.labels.get("app") == "worker"
            and pod.status.container_statuses
            and pod.status.container_statuses[0].ready
        ):
            try:
                resp = requests.get(f"http://{pod.status.pod_ip}:5000/health")
                if resp.status_code == 200:
                    res.append(pod)
            except:
                continue
    return res


def send_remove_from_worker(worker_ip, services):
    requests.post(
        f"http://{worker_ip}:5000/remove",
        json={"services": services},
    )


def send_removeall_from_worker(worker_ip):
    requests.post(
        f"http://{worker_ip}:5000/remove_all",
    )


def send_add_to_worker(worker_ip, services):
    requests.post(
        f"http://{worker_ip}:5000/add",
        json={"services": services},
    )


def get_current_worker_services(worker_ip):
    try:
        resp = requests.get(f"http://{worker_ip}:5000/services")
        return resp.json()["services"]
    except:
        return []


def get_current_worker_mapping():
    workers = get_ready_workers()
    service_worker_mapping = {}
    for worker in workers:
        worker_ip = worker.status.pod_ip
        worker_id = worker.metadata.uid
        services = get_current_worker_services(worker_ip)
        for service in services:
            service_worker_mapping[service] = worker_id
    return service_worker_mapping


def main():
    hashring = HashRing()
    services = get_services()
    service_worker_mapping = {service: None for service in services}
    service_worker_mapping.update(get_current_worker_mapping())
    while True:
        print("Checking workers")
        workers = get_ready_workers()
        id_to_worker = {worker.metadata.uid: worker for worker in workers}
        ready_workers_ids = set(id_to_worker.keys())
        newfound_workers = ready_workers_ids - hashring.get_nodes()
        lost_workers = hashring.get_nodes() - ready_workers_ids
        for worker in newfound_workers:
            hashring.add_node(worker)
        for worker in lost_workers:
            hashring.remove_node(worker)
        remove_from_worker = {}
        add_to_worker = {}
        for service in services:
            should_be_worker = hashring.get_node(service)
            current_worker = service_worker_mapping[service]
            if should_be_worker != current_worker:
                if current_worker not in lost_workers and current_worker is not None:
                    remove_from_worker.setdefault(current_worker, []).append(service)
                add_to_worker.setdefault(should_be_worker, []).append(service)
        for worker, changed_services in remove_from_worker.items():
            try:
                send_remove_from_worker(
                    id_to_worker[worker].status.pod_ip, changed_services
                )
                for service in changed_services:
                    service_worker_mapping[service] = None
            except:
                print(f"Failed to remove services from worker {worker}")
        for worker, changed_services in add_to_worker.items():
            try:
                if worker in newfound_workers:
                    send_removeall_from_worker(id_to_worker[worker].status.pod_ip)
                send_add_to_worker(id_to_worker[worker].status.pod_ip, changed_services)
                for service in changed_services:
                    service_worker_mapping[service] = worker
            except:
                print(f"Failed to add services to worker {worker}")

        time.sleep(60)


if __name__ == "__main__":
    main()
