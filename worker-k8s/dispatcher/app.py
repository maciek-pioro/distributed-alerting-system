from kubernetes import client, config
import time
from google.cloud import bigquery
from typing import List
import requests

config.load_incluster_config()
CORE_API = client.CoreV1Api()
APPS_API = client.AppsV1Api()
BQ_CLIENT = bigquery.Client()


def get_quantiles(n_workers: int) -> List[int]:
    query = f"SELECT APPROX_QUANTILES(id, {n_workers}) FROM `irio-solution.production.services`"
    res = next(BQ_CLIENT.query(query).result()).values()[0]
    return res


def send_config(worker_ip, min_id, max_id):
    requests.post(
        f"http://{worker_ip}:5000/schedule",
        params={"min_service_id": min_id, "max_service_id": max_id},
    )


def reschedule(workers):
    quantiles = get_quantiles(len(workers))
    for i, worker in enumerate(workers):
        worker_id = worker.metadata.uid
        min_id = quantiles[i]
        max_id = quantiles[i + 1]
        if i == 0:
            min_id = 0
        if i == len(workers) - 1:
            max_id = -1
        print(f"(Re)scheduling worker {worker_id} to {min_id} - {max_id}")
        send_config(worker.status.pod_ip, min_id, max_id)


def get_ready_workers():
    pods = CORE_API.list_namespaced_pod("default")
    res = []
    for pod in pods.items:
        if (
            pod.metadata.labels.get("app") == "worker"
            and pod.status.container_statuses[0].ready
        ):
            res.append(pod)
    return res

def are_there_other_dispatchers():
    pods = CORE_API.list_namespaced_pod("default")
    dispatchers = 0
    for pod in pods.items:
        if (
            pod.metadata.labels.get("app") == "dispatcher" and not pod.status.container_statuses[0].state.terminated
        ):
            dispatchers += 1
    return dispatchers > 1

def main():
    workers_ids = set()
    while True:
        print("Checking if there are other dispatchers")
        if are_there_other_dispatchers():
            print("There are other dispatchers, waiting")
            time.sleep(60)
            continue
        print("Checking workers")
        ready_workers = get_ready_workers()
        print(f"Ready workers: {len(ready_workers)}")
        new_workers_ids = {worker.metadata.uid for worker in ready_workers}
        if workers_ids != new_workers_ids:
            print("Rescheduling")
            reschedule(ready_workers)
            workers_ids = new_workers_ids
        time.sleep(60)


#
if __name__ == "__main__":
    main()

# get pods
# pods = CORE_API.list_namespaced_pod('default')
# get pod ip
# pods.items[0].status.pod_ip
# is worker
# pods.items[0].metadata.labels.get('app') == 'worker'
# get uid
# pods.items[0].metadata.uid
# is ready
# pods.items[0].status.container_statuses[0].
# get max bigquery row:
# c = bigquery.Client()
# for r in c.query('SELECT max(id) FROM `irio-solution.production.services` LIMIT 1000').result():
#    M = r.values()[0]
# quantiles
# SELECT APPROX_QUANTILES(id, n_workers) AS from FROM `irio-solution.production.services` LIMIT 1000
# r.values()[0] = (e. g.) [1, 3, 5] for 2 workers
