#!/bin/bash

set -ex

echo "Updating package lists..."
sudo apt update

sudo apt install -y wget gpg lsb-release

echo "Adding the GPG key for the HashiCorp repository..."
wget -O - https://apt.releases.hashicorp.com/gpg | gpg --dearmor | sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg > /dev/null

echo "Adding the HashiCorp repository to the sources list..."
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list

echo "Updating package lists and installing Terraform..."
sudo apt update && sudo apt install -y terraform=${TERRAFORM_VERSION}-1

echo "Terraform installed successfully"
terraform --version
