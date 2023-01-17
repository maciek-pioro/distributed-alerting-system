# eval $(minikube docker-env)
version=$(cat cur-worker-version.txt)
version=$(($version + 1))
new_tag="mpioro/irio-worker:$version"
docker build -t $new_tag worker
minikube image load $new_tag
echo "Worker: $new_tag"
echo $version > cur-worker-version.txt

version=$(cat cur-dispatcher-version.txt)
version=$(($version + 1))
new_tag="mpioro/irio-dispatcher:$version"
docker build -t $new_tag dispatcher
minikube image load $new_tag
echo "Dispatcher: $new_tag"
echo $version > cur-dispatcher-version.txt