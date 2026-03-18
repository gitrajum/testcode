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
# repo_name="smart-azure-${project_name}-${beat_id}"
subscription_id=$(az account show --query 'id' --output tsv)

subscription_ou=$(echo "$subscription_id" | sed 's/[^0-9]*//g' | cut -c -12)

# Define an environment name
env_name="${env_prefix}-${subscription_ou}"


# Define a Rg

# Define an Identity NAme
# var_usrmgd_identity="$project_name" | "_CICD"

# Get service principal id
#sp_id=$(az ad sp show --id $app_id --query id --output tsv)

echo "Creating Core Resource Group..."
az group create --name $var_core_rgname --location $var_region




az role assignment create --role Reader --subscription $subscription_id --assignee-object-id  $var_ReaderGroup_ID --assignee-principal-type Group --scope /subscriptions/$subscription_id

#Create federated credential for the environment
echo "Creating User Managed Identity...."

az identity create \
  --name $var_usrmgd_identity \
  --resource-group  $var_core_rgname \
  --location $var_region \
  --tags repo=$var_repo_url
# #Create federated credential for the environment
# echo "Creating Terraform State Storage ...."
# az storage account create \
#   --name $var_core_storagename \
#   --resource-group $var_core_rgname \
#   --location $var_region \
#   --sku Standard_ZRS \
#   --tags repo=$var_repo_url
echo "Setting Identity REPO Relation"

# Create a JSON variable using a Here Document
# read -r -d '' credential_json << EOF
# {
#   "name": $var_usrmgd_identity
#   "issuer": "https://token.actions.githubusercontent.com",
#   "subject": "repo:bayer-int/af-platform:ref:refs/heads/Development-317459554298",
#   "description": "Federated credentials for repo:bayer-int/${project_name}:environment:${env_name}",
#   "audiences": [
#     "api://AzureADTokenExchange"
#   ]
# }
# EOF

# az identity federated-credential create --id $app_id

 az identity federated-credential create --identity-name $var_usrmgd_identity \
                                        --name $var_usrmgd_identity \
                                        --resource-group $var_core_rgname \
                                        --audience  "api://AzureADTokenExchange" \
                                        --issuer "https://token.actions.githubusercontent.com" \
                                        --subject "repo:bayer-int/af_agent_group1:environment:prod"


echo "Role Assignment for Managed Identity"

hurzid=$(az identity show --name $var_usrmgd_identity --resource-group $var_core_rgname --query id --output tsv)
# echo "xxxxxxxxxx"
# echo $hurzid

hurz=$(az resource show --id $hurzid --query properties.principalId --output tsv)

# echo "xxxxxxxxxx"
# echo $hurz
az role assignment create --role SMARTBasicOwner --subscription $subscription_id --assignee-object-id  $hurz --assignee-principal-type ServicePrincipal --scope /subscriptions/$subscription_id

echo "Script completed"
