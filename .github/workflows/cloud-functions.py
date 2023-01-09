on:
  push:
    branches: [ "main" ]

jobs:
  job_id:
    runs-on: 'ubuntu-latest'
    permissions:
      contents: 'read'
      id-token: 'write'

    steps:
    - uses: 'actions/checkout@v3'

#     - id: 'auth'
#       uses: 'google-github-actions/auth@v1'
#       with:
#         workload_identity_provider: 'projects/123456789/locations/global/workloadIdentityPools/my-pool/providers/my-provider'
#         service_account: 'my-service-account@my-project.iam.gserviceaccount.com'
    - id: 'auth'
      name: 'Authenticate to Google Cloud'
      uses: 'google-github-actions/auth@v0'
      with:
        token_format: 'access_token'
        workload_identity_provider: 'projects/7432286469/locations/global/workloadIdentityPools/default-pool/providers/gh-provider'
        service_account: 'gh-service-account@irio-solution.iam.gserviceaccount.com'

    - id: 'deploy_sender1'
      uses: 'google-github-actions/deploy-cloud-functions@v1'
      with:
        name: 'first-sender'
        runtime: 'python310'
        entrypoint: 'handle_first_email'
        memory_mb: 128
        region: 'europe-central2'
        source_dir: 'cloud-functions/first-sender'
    
    - id: 'deploy_sender2'
      uses: 'google-github-actions/deploy-cloud-functions@v1'
      with:
        name: 'second-sender'
        runtime: 'python310'
        entrypoint: 'handle_second_email'
        memory_mb: 128
        region: 'europe-central2'
        source_dir: 'cloud-functions/second-sender'
    
    - id: 'deploy_ack_endpoint'
      uses: 'google-github-actions/deploy-cloud-functions@v1'
      with:
        name: 'ack-endpoint'
        runtime: 'python310'
        entrypoint: 'handle_request'
        memory_mb: 128
        region: 'europe-central2'
        source_dir: 'cloud-functions/ack-endpoint'

    # Example of using the output
#     - id: 'test'
#       run: 'curl "${{ steps.deploy.outputs.url }}"'
