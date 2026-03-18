#!/bin/bash

set -ex

echo "Updating package lists..."
sudo apt update

if [ -z "$GIT_VERSION" ]; then
  echo "No specific Git version provided. Installing the latest version..."
  sudo apt install -y git
else
  echo "Installing Git version $GIT_VERSION..."
  sudo apt install -y git=$GIT_VERSION
fi

echo "Configuring Git..."
git config --global --add safe.directory "*"

echo "Git installed successfully"
git --version
