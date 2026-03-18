# Table of Contents

<!--TOC-->

- [Table of Contents](#table-of-contents)
- [Infrastructure and configuration for your Azure subscription](#infrastructure-and-configuration-for-your-azure-subscription)
  - [Overview](#overview)
  - [Working with the repository](#working-with-the-repository)
    - [Introduction](#introduction)
    - [Repository Structure](#repository-structure)
    - [Create a Pull Request](#create-a-pull-request)
    - [Validation and Merge](#validation-and-merge)
  - [What to do next](#what-to-do-next)
  - [What to do if GitHub Actions workflow execution fails?](#what-to-do-if-github-actions-workflow-execution-fails)
    - [In case of failed syntax-checks:](#in-case-of-failed-syntax-checks)
    - [Notes on Tool Versions](#notes-on-tool-versions)
    - [In case of failed deployment:](#in-case-of-failed-deployment)
  - [Examples usage](#examples-usage)
  - [Adding tags to AzureRM Provider resources in Terraform](#adding-tags-to-azurerm-provider-resources-in-terraform)
  - [Pull Request workflow](#pull-request-workflow)
  - [Detaching a Fork from the Parent Repository](#detaching-a-fork-from-the-parent-repository)
  - [AI-powered code generation using GitHub Copilot](#ai-powered-code-generation-using-github-copilot)
    - [Options for using GitHub Copilot](#options-for-using-github-copilot)
    - [Copilot access to internal repositories](#copilot-access-to-internal-repositories)
    - [Steps for code generation with GitHub Copilot](#steps-for-code-generation-with-github-copilot)
    - [Important Notes](#important-notes)

<!--TOC-->

# Infrastructure and configuration for your Azure subscription

## Overview

This repository was automatically created for your Azure subscription by
[IaC Automation Pipeline](https://docs.int.bayer.com/cloud/smart-cloud-automation/iacap/)
(previously called "Fawkes"). It is meant to store Infrastructure-as-Code (IaC) for your cloud
resources, probably alongside your application code and other configuration. It is
assumed that you will be using [Terraform](https://www.terraform.io/) for your IaC.

The repository also contains everything needed to quickly start working on your
application:

1. GitHub [workflow](./.github/workflows/deploy.yaml) which will deploy your Terraform
   infrastructure.

1. [Examples](./configuration/examples) of infrastructure using our
   [modules](https://docs.int.bayer.com/cloud/smart-cloud-automation/terraform-modules/)
   As existing modules are periodically updated and new modules are developed, examples are also updated. Please keep track of changes in the upstream repository and synchronize the `template` branch with it, taking any necessary changes into your own branches. Please refer to the [Examples usage](#examples-usage) section for instructions on how to use the examples.

1. GitHub teams that define access control to this repository. They are synchronized
   with the same Entra ID groups that are used to control access to the GCP project
   itself. See 'Settings -> Collaborators and teams'.

1. Pre-configured GitHub [environments](/settings/environments)
   (see 'Settings -> Environments') with variables and
   secrets for you Azure subscription. One environment per Azure subscription.
   The name of the environment is created by combining its type with the first 12 digits of the subscription ID (e.g., if the Subscription ID is 'da87104e-3249-1g73-87c5-b12a9b68d40f', the environment name will be 'Develop-871043249173' for Development and 'Production-871043249173' for Production). This naming convention clearly indicates the subscription to which the environment is linked.

1. Associated [SonarQube](https://docs.int.bayer.com/cloud/devops/sonarqube/)
   project for code quality analysis.

1. Artifactory repository for your Docker images (you should've received email with
   details. Keep in mind that you will need to populate the `FAWKES_JFROG_USER_NAME` variable and the `FAWKES_JFROG_USER_TOKEN` secret in your repository before using the `container-build.yaml` workflow).

This repository is already authorized with your Azure subscription, so the GitHub Actions
pipelines can deploy your infrastructure without any additional configuration.

> [!NOTE]
> If you have created several projects with the same name and BEAT ID but different
> Stage, they will be represented as separate branch+environment in this repository.

## Working with the repository

### Introduction

This repository adheres to a `branch-based workflow`, where there are multiple branches, each associated with a specific environment for deployment. For example, branches such as `Develop-xxxxxxxxxxxx` and `Production-xxxxxxxxxxxx` are used to manage configurations and deployments specific to each environment. Additionally, there is a `template` branch that can be used for synchronizing with the template repository. Feature branches should be created from the appropriate environment branch, depending on the target environment for the changes. In this readme, we will provide a detailed explanation of how the workflow operates and outline the steps involved in managing configurations across different environments.
> You can familiarize yourself with the branch-based branching strategy workflow at [go/cloud](https://docs.int.bayer.com/cloud/smart-cloud-automation/iacap/user-journeys-devops/#branch-based-strategy).

### Repository Structure

The repository includes one or multiple branches for each environment: Development and Production (if you requested only one environment, then there will be only one environment branch). Each environment branch contains the ["configuration" folder](/configuration/), which holds the Terraform configuration that will be deployed in the environment of that branch.

### Create a Pull Request

It is recommended that you work on your changes in a `feature` branch and then create a pull request targeting the environment branch (Development, if it exists).
When you create a pull request into environment branch, Terraform planning is executed for the corresponding environment, and the plan results are displayed as a comment on the pull request.

> [!NOTE]
> Please refrain from clicking the "Compare & pull request" button, as it by default targets the pull request to the upstream repository (the template repository from which your repository was forked). Instead, kindly follow the algorithm provided below:
> - Navigate to the "Pull requests" tab.
> - Click on "New pull request".
> - Select the "feature" branch as the source and choose environment branch as the base.

### Validation and Merge

Once you are satisfied with the Terraform plan, you can proceed to merge the pull request. After the merge, the configuration is deployed into the environment.
After your changes have been validated and merged into the Development branch, you should then create a second pull request from the Development branch to the Production branch.

## What to do next

1. Check and adjust if needed access permissions on your repository in 'Settings ->
   Collaborators and teams'.

1. Make sure your
   [branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule)
   and
   [environments](https://docs.github.com/en/actions/deployment/protecting-deployments/configuring-custom-deployment-protection-rules)
   have correct protection rules.

1. Enable GitHub Actions in ['Actions'](/actions/) section. The "template" branch will be used for syncing forks only, not for development.

1. Add some Terraform configuration for your project in [configuration](./configuration)
   directory. Make sure to use [branch](/branches/) corresponding to your project.

1. Create Terraform backend by running workflow 'Create Terraform Backend'. Select your branch, specify the newly created environment (you can copy the value from `Settings > Environments`), and click on 'Run Workflow'. Additionally, you can specify the desired location where the backend should be created by overriding the default value, which is set to 'westeurope'. Wait for the workflow to complete successfully before proceeding to the next step.

1. Deploy your infrastructure by creating and merging pull requests into the project's branch.

1. Create your wonderful application in the cloud!

You can read more about SMART Cloud Automation at
[go/cloud](https://docs.int.bayer.com/cloud/smart-cloud-automation/fawkes/).

## What to do if GitHub Actions workflow execution fails?

### In case of failed syntax-checks:

During the pull request process, even if syntax verification errors occur, the Terraform planning will continue, and a warning comment will be posted on the pull request indicating the failure of the syntax check stage. Although the Terraform planning might succeed, it is recommended to resolve these syntax errors to prevent potential misconfigurations.

We strongly recommend using pull requests to make changes. This method allows all checks to be visible before the code is pushed to an environment branch, providing an opportunity to address any errors and ensure that the configuration is correct before deployment. This practice helps maintain the stability and integrity of the environment.

Below, you will find details on how to fix failed syntax-checks.

#### Codespace

In a Codespace, the `pre-commit` and `checkov` tools are already installed, and hooks are automatically set up for the current branch. This means that `pre-commit` runs automatically on every commit. If `pre-commit` reports any issues, they need to be addressed (some issues may be fixed automatically, such as formatting the README file and adjusting indentation in code files). After addressing the issues, stage the files again and commit the changes. The commit will only be executed if the checks pass successfully.

To run `pre-commit` in a Codespace:

1. Commit the changes using `git commit`.
2. Review the output of `pre-commit` and address any reported issues.
3. Stage the files again using `git add`.
4. Commit the changes using `git commit`.
5. Proceed with the pipeline or further actions.

#### Local IDE

If you are working in a local IDE, follow the steps below to set up the necessary tools:

##### Installation on Linux

To install all necessary tools on Linux, run the following script in your terminal:

```bash
# Install pre-commit and checkov
pip install pre-commit==4.1.0 checkov==3.2.370

# Install tflint
wget -O tflint.zip "https://github.com/terraform-linters/tflint/releases/download/v0.55.1/tflint_$(uname)_amd64.zip"
unzip tflint.zip
rm tflint.zip
chmod +x tflint
sudo mv tflint /usr/bin/

# Install terraform-docs
wget -O terraform-docs.tgz "https://terraform-docs.io/dl/v0.16.0/terraform-docs-v0.16.0-$(uname)-amd64.tar.gz"
tar -xzf terraform-docs.tgz
rm terraform-docs.tgz
chmod +x terraform-docs
sudo mv terraform-docs /usr/bin/
```

##### Installation on Other Operating Systems

For other operating systems, or for additional information, refer to the official installation instructions:

- **`pre-commit`:** [Installation Guide](https://pre-commit.com/#installation)
- **`checkov`:** [Installation Guide](https://www.checkov.io/2.Basics/Installing%20Checkov.html)
- **`terraform-docs`:** [Installation Guide](https://terraform-docs.io/user-guide/installation/)
- **`tflint`:** [Installation Guide](https://github.com/terraform-linters/tflint?tab=readme-ov-file#installation)

##### Post-Installation Steps

1. Set up the Git hooks by running the following command in the terminal:
   ```bash
   pre-commit install
   ```

2. Run `pre-commit` on all files by executing the following command:
   ```bash
   pre-commit run --all-files
   ```
   Alternatively, you can use the shorthand command:
   ```bash
   pre-commit run -a
   ```

3. After running `pre-commit`, stage the files again using `git add`.

4. Commit the changes using `git commit`.

5. Proceed with the pipeline or further actions.

#### Skipping `pre-commit` Checks

If you want to bypass the `pre-commit` checks and commit your changes regardless of their success, you can use the `--no-verify` flag. Be cautious when using this option, as it skips all Git hooks, including syntax and security checks, which might lead to potential issues in the codebase.

To commit changes without running `pre-commit`:

```bash
git commit --no-verify
```

This approach should only be used in exceptional cases where you are certain that skipping the checks will not introduce errors or misconfigurations.

### Notes on Tool Versions

- **`pre-commit`:** Default version is `4.1.0`. To use a different version in the workflows, set the `PRE_COMMIT_VERSION` repository variable.

- **`checkov`:** Default version is `3.2.370`. To use a different version in the workflows, set the `CHECKOV_VERSION` repository variable.

- **`terraform-docs`:** Default version is `0.16.0`. To use a different version in the workflows, set the `TERRAFORM_DOCS_VERSION` repository variable.

- **`tflint`:** Default version is `0.55.1`. To use a different version in the workflows, set the `TFLINT_VERSION` repository variable.

If you install a different version of any tool locally, make sure to update the corresponding repository variable to ensure consistency between your local environment and the workflow.

### In case of failed deployment:

Check Terraform configuration and try again.

For more detailed description of the template repository this repository was forked
from, information on the proposed way of working with IaC and collaboration see
[Repository Template](https://docs.int.bayer.com/cloud/smart-cloud-automation/fawkes/template-repository-README/)
and
[DevOps User Journey](https://docs.int.bayer.com/cloud/smart-cloud-automation/fawkes/user-journeys-devops/).

## Examples usage

The `configuration/examples` folder contains sub-folders with usage examples for Terraform modules developed by the Smart team. To use a module, simply copy the `.tf` files from the example folder to the root of the `configuration` folder, modifying the variable values as needed.
Please note that if you are using multiple modules, you need to merge the contents of the `variables.tf` and `outputs.tf` files (removing any duplicate variables if present). Additionally, the `terraform.tf` file should contain provider versions that satisfy the requirements of all the modules at once.
You might also need to use the output of one module as a value for another module. To do this, use the syntax `module.{module_name}.{output_name}` to reference the output value of a specific module in another module.
>[!NOTE] The API Gateway example differs slightly from the others and includes an additional `api-gateway` folder. This folder should also be copied to the root of the `configuration` folder. Refer to the [usage documentation](./configuration/examples/api-gateway/README.md) to find additional information on its usage.

## Adding tags to AzureRM Provider resources in Terraform

Tagging resources is a crucial practice when working with cloud infrastructure. Tags are key-value pairs that provide metadata and organizational information about resources. Resource tagging is essential for cost allocation, resource management, automation, visibility, auditability, governance, and security. The `azurerm` provider in Terraform does not have native support for specifying default tags for resources. Therefore, tags need to be directly specified for each resource, as shown in the example below:

```hcl
resource "azurerm_resource_group" "example" {
  name     = var.rg_name
  location = var.location

  tags = {
    Environment = "Production"
    Owner       = "Name Surname"
    Application = "App name"
    Project     = "Project name"
    ManagedBy   = "Terraform"
  }
}
```

To pass tags to modules, you can use the `tags` variable, which is present in all modules developed by the SMART team. Here's an example of passing tags to a module:

```hcl
module "example_module" {
  source = "git::https://modules/example"

  tags = {
    Environment = "Production"
    Owner       = "Name Surname"
    Application = "App name"
    Project     = "Project name"
    ManagedBy   = "Terraform"
  }
}
```

## Pull Request workflow

We encourage you to follow the pull request workflow in the tenant repository. It is recommended that you work on your changes in a `feature` branch and then create a pull request targeting either the environment (`Develop-*`, `Production-*`, etc.) branch.

When you create a pull request, a Terraform plan will be automatically run to assess the potential changes introduced by merging the head branch into the base branch. The plan results will be posted directly in the pull request, allowing for easy review and discussion.

Once the pull request is merged, a deployment will be triggered in the base branch environment, allowing the changes to be deployed.

## Detaching a Fork from the Parent Repository

If for any reason you want to detach a fork from the parent repository, please follow these steps:

1. Go to the fork request page by visiting [GitHub Support Fork page](https://support.github.com/request/fork).
2. Click on "Detach a Fork" to initiate a chat with the bot.
3. The bot will prompt you to enter the repository name in the format `owner/repo-name`.
4. After entering the repository name, the bot will ask if you have made any commits to the fork and the reason why you want to detach the fork.
5. The bot will inform you that a ticket has been created, and you will also receive an email confirming the ticket creation. Soon (within 5 minutes to a few hours), you will receive an email stating that the fork has been detached from the parent repository.

Please note that the actual time for the fork detachment process may vary.

If you have any further questions or need assistance, please reach out to GitHub support through the fork request page.

## AI-powered code generation using GitHub Copilot

This repository includes specific instructions for GitHub Copilot to assist with code generation. These instructions are stored in the `.github/copilot-instructions.md` file. The instructions are periodically updated in the template repository, so we recommend keeping your environment branches synchronized with the template repository to ensure you have the latest updates.

You can also add custom instructions for Copilot specific to your project by creating a `.instructions.md` file and placing it in the `.github/` directory. For more details, please refer to the [Copilot customization documentation](https://code.visualstudio.com/docs/copilot/copilot-customization).

Additionally, the `devcontainer` configuration for this repository already includes the GitHub Copilot extension, making it easier to get started.

### Options for using GitHub Copilot

There are three main ways to use GitHub Copilot in your repository:

1. **Running GitHub Codespaces**

   GitHub Codespaces provides a cloud-based development environment. The `devcontainer` configuration in this repository includes GitHub Copilot, so no additional setup is required to use Copilot within Codespaces.

2. **Running the Devcontainer locally**

   You can run the `devcontainer` locally using Visual Studio Code and Docker. The `devcontainer` includes GitHub Copilot, so once the container is running, Copilot will be available for use without further configuration.

3. **Using your local IDE**

   If you prefer using your local IDE, ensure that the GitHub Copilot extension is installed.
   - For optimal performance, we recommend enabling the `github.copilot.chat.agent.thinkingTool` setting in your IDE.
   - Additionally, make sure the `github.copilot.chat.codeGeneration.useInstructionFiles` setting is enabled to allow Copilot to use the `.github/copilot-instructions.md` file for context.

   **Important Note:**
   When working in a local IDE, there are rare cases where the `.github/copilot-instructions.md` file is not automatically included in Copilot's context, even with the `useInstructionFiles` setting enabled. If you notice that Copilot is generating irrelevant or incorrect suggestions, remind it about the instructions file by explicitly referencing it in your chat prompt. For example, you can say:
   _"Refer to the instructions in the `.github/copilot-instructions.md` file."_

   Once reminded, Copilot will immediately adjust its behavior and provide more accurate and relevant suggestions.

### Copilot access to internal repositories

- **In GitHub Codespaces:**

   When working in a Codespace, GitHub Copilot has access to internal repositories within the `bayer-int` organization. This allows it to automatically retrieve necessary information from those repositories to assist you in generating code and configurations.

- **On Local Machines:**

   When using Copilot on your local machine, it does not have direct access to the internal repositories of the `bayer-int` organization. However, Copilot can suggest Git commands that you can run to retrieve the required information from the necessary repositories.

   **Important:** For this to work, your local Git client must be authorized to access the `bayer-int` organization with read access to internal repositories. Ensure that your Git credentials are properly configured to authenticate with the organization.

### Steps for code generation with GitHub Copilot

Follow these steps to use GitHub Copilot effectively:

1. **Start the Copilot Chat**

   - If you are using GitHub Codespaces, the Copilot chat interface will open automatically.
   - If you are using an IDE (e.g., Visual Studio Code), locate the Copilot icon (in VS Code, it is to the right of the search bar), click on it, and the chat will open.

2. **Switch Copilot to Agent mode**

   Switch Copilot to its Agent mode to enable interactive code generation and assistance. The mode switch is located below the input field in the chat interface.

3. **Compose a request**

   Write a clear and concise request describing the code or configuration you need.

   **Example request:**
   *"Create an Azure Virtual Network named `my-vnet` with two subnets: `subnet-a` (address range `10.0.1.0/24`) and `subnet-b` (address range `10.0.2.0/24`). Include a network security group for each subnet with basic inbound rules allowing HTTP (port 80) and SSH (port 22)."*

4. **Review suggestions and execute commands**

   Copilot will generate the configuration and suggest commands for initialization, formatting, validation, syntax checking, etc.
   - To execute the suggested commands, click the **Continue** button in the Copilot interface.

5. **Iterative refinement**

   Based on the output of the executed commands, Copilot will make adjustments and run additional commands as needed.
   - Multiple iterations may be required to achieve a correct and functional configuration.
   - Copilot may ask for your confirmation to apply suggested changes or, in some cases, apply them automatically.

6. **Ask Copilot to commit changes**

   Once you are satisfied with the results, you can ask Copilot to commit the changes.
   - Copilot will generate a commit message based on the changes and suggest the necessary Git commands to add the files to the index and create the commit.
   - To execute the suggested commands, simply click the **Continue** button.

### Important Notes

- **Copilot is not perfect**: Do not expect Copilot to produce a fully functional configuration without your involvement. It is a powerful tool for reducing routine work and accelerating development, but it benefits from your input and oversight.
- **Stay updated**: Keep your repository synchronized with the template repository to benefit from the latest Copilot instructions and improvements.
- **Iterative process**: Achieving the desired result may require several iterations. Copilot is designed to collaborate with you, not replace you entirely.
