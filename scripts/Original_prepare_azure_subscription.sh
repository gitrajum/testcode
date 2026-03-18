#!/bin/sh

# This script allows you to use a semi-automated way to connect an existing subscription to IaCAP
# Please refer to the following document for instructions on how to use the script:
# https://docs.int.bayer.com/cloud/smart-cloud-automation/iacap/connect-existing-account/

# Set variables from vars.env file
source vars.env

# Prompt for input parameters using a dialog box
# read -p "Enter project name: " project_name
# read -p "Enter BEAT ID: " beat_id
# read -p "Enter environment prefix (for example, 'int' or 'prod'): " env_prefix
# read -p "Enter subscription id (for OIDC): " subscription_id
# read -p "Enter application id (for OIDC): " app_id

az account set --subscription $subscription_id

# Check if the project name matches the "AZS" pattern
pattern="^AZS[0-9]+_"
if [[ $project_name =~ $pattern ]]; then
  # Remove the pattern from the project name
  project_name="${project_name/$BASH_REMATCH/}"
fi

# Get the repository name and subscription
repo_name="smart-azure-${project_name}-${beat_id}"
subscription_id=$(az account show --query 'id' --output tsv)
subscription_ou=$(echo "$subscription_id" | sed 's/[^0-9]*//g' | cut -c -12)

# Define an environment name
env_name="${env_prefix}-${subscription_ou}"

# Get service principal id
sp_id=$(az ad sp show --id $app_id --query id --output tsv)

# Create role assignment
echo "Creating role assignment..."
az role assignment create --role BayerContributor --subscription $subscription_id --assignee-object-id  $sp_id --assignee-principal-type ServicePrincipal --scope /subscriptions/$subscription_id

# Create a JSON variable using a Here Document
read -r -d '' credential_json << EOF
{
  "name": "${repo_name}:environment:${env_name}",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:bayer-int/${repo_name}:environment:${env_name}",
  "description": "Federated credentials for repo:bayer-int/${repo_name}:environment:${env_name}",
  "audiences": [
    "api://AzureADTokenExchange"
  ]
}
EOF

#Create federated credential for the environment
echo "Creating federated credential..."
az ad app federated-credential create --id $app_id --parameters "$credential_json"
echo "Script completed"
