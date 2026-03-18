#!/bin/bash

set -ex

echo "Updating package lists..."
sudo apt update

echo "Installing Python and pip..."
# chown not needed on GitHub-hosted runners
sudo apt install -y python${PYTHON_VERSION} python3-pip

echo "Python and pip installed successfully"
