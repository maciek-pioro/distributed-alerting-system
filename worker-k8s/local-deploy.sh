worker_version=$(cat cur-worker-version.txt)
dispatcher_version=$(cat cur-dispatcher-version.txt)

sed "s,IMAGE_PULL_POLICY,Never,g" ./deploy/worker-deployment.yaml > worker-deployment.yaml
sed -i "s,WORKER_IMAGE,mpioro/irio-worker:$worker_version,g" worker-deployment.yaml
sed "s,IMAGE_PULL_POLICY,Never,g" ./deploy/dispatcher-deployment.yaml > dispatcher-deployment.yaml
sed -i "s,DISPATCHER_IMAGE,mpioro/irio-dispatcher:$dispatcher_version,g" dispatcher-deployment.yaml
minikube kubectl -- apply -f worker-deployment.yaml
minikube kubectl -- apply -f dispatcher-deployment.yaml