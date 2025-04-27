Below is the **entire** Markdown reformatting in one block, using ASCII-style headings (`=` and `-`) and focusing on Python examples. Non-Python examples have been omitted, and code blocks are preserved using triple backticks.

---

```markdown
OVERVIEW
========

Learn how to build and deploy applications on the RunPod platform with this set of tutorials. Covering tools, technologies, and deployment methods, including Containers, Docker, and Serverless implementation.

SERVERLESS
----------

Explore how to run and deploy AI applications using RunPod's Serverless platform.

GPUs
----

- **Generate images with SDXL Turbo:** Learn how to build a web application using RunPod's Serverless Workers and SDXL Turbo from Stability AI, a fast text-to-image model, and send requests to an Endpoint to generate images from text-based inputs.

- **Run Google's Gemma model:** Deploy Google's Gemma model on RunPod's vLLM Worker, create a Serverless Endpoint, and interact with the model using OpenAI APIs and **Python**.

- **Run your first serverless endpoint with Stable Diffusion:** Use RunPod's Stable Diffusion v1 inference endpoint to generate images, set up your serverless worker, start a job, check job status, and retrieve results.

CPUs
----

- **Run an Ollama Server on a RunPod CPU:** Set up and run an Ollama server on RunPod CPU for inference with this step-by-step tutorial.

PODS
----

Discover how to leverage RunPod Pods to run and manage your AI applications.

GPUs
----

- **Fine tune an LLM with Axolotl on RunPod:** Learn how to fine-tune large language models with Axolotl on RunPod, a streamlined workflow for configuring and training AI models with GPU resources, and explore examples for LLaMA2, Gemma, LLaMA3, and Jamba.

- **Run Fooocus in Jupyter Notebook:** Learn how to run Fooocus, an open-source image generating model, in a Jupyter Notebook and launch the Gradio-based interface in under 5 minutes, with minimal requirements of 4GB Nvidia GPU memory and 8GB system memory.

- **How To Connect to a Pod Instance through VSCode:** Learn how to connect to a RunPod Pod instance through VSCode for seamless development and management.

- **Build Docker Images on RunPod with Bazel:** Learn how to build Docker images on RunPod using Bazel, a powerful build tool for creating consistent and efficient builds.

- **Set up Ollama on your GPU Pod:** Set up Ollama, a powerful language model, on a GPU Pod using RunPod, and interact with it through HTTP API requests, harnessing the power of GPU acceleration for your AI projects.

- **Run your first Fast Stable Diffusion with Jupyter Notebook:** Deploy a Jupyter Notebook to RunPod and generate your first image with Stable Diffusion in just 20 minutes, requiring a Hugging Face user access token, RunPod infrastructure, and basic familiarity with the platform.

CPUs
----

- **Run Docker in Docker on RunPod CPU Instances:** Learn how to run Docker in Docker on RunPod CPU instances for enhanced development and testing capabilities.

CONTAINERS
----------

Understand the use of Docker images and containers within the RunPod ecosystem.

- **Persist data outside of containers:** Learn how to persist data outside of containers by creating named volumes, mounting volumes to data directories, and accessing persisted data from multiple container runs and removals in Docker.

- **Containers overview:** Discover the world of containerization with Docker, a platform for isolated environments that package applications, frameworks, and libraries into self-contained containers for consistent and reliable deployment across diverse computing environments.

- **Dockerfile:** Learn how to create a Dockerfile to customize a Docker image and use an entrypoint script to run a command when the container starts, making it a reusable and executable unit for deploying and sharing applications.

- **Docker commands:** RunPod enables BYOC development with Docker, providing a reference sheet for commonly used Docker commands, including login, images, containers, Dockerfile, volumes, network, and execute.

INTEGRATIONS
------------

Explore how to integrate RunPod with other tools and platforms like OpenAI, SkyPilot, and Charm's Mods.

- **OpenAI**
  - *Overview:* Use the OpenAI SDK to integrate with your Serverless Endpoints.

- **SkyPilot**
  - *Running RunPod on SkyPilot:* Learn how to deploy Pods from RunPod using SkyPilot.

- **Mods**
  - *Running RunPod on Mods:* Learn to integrate into Charm's Mods tool chain and use RunPod as the Serverless Endpoint.

MIGRATION
---------

Learn how to migrate from other tools and technologies to RunPod.

- **Cog**
  - *Cog Migration:* Migrate your Cog model from Replicate.com to RunPod by following this step-by-step guide.

- **Banana**
  - *Banana migration:* Quickly migrate from Banana to RunPod with Docker, leveraging a bridge between the two environments for a seamless transition.

-------------------------------------------------------------------------------
RUN AN OLLAMA SERVER ON A RUNPOD CPU
====================================

In this guide, you will learn how to run an Ollama server on your RunPod CPU for inference. Although this tutorial focuses on CPU compute, you can also select a GPU type and follow the same steps. By the end of this tutorial, you will have a fully functioning Ollama server ready to handle requests.

Setting up your Endpoint
------------------------

**note**  
Use a Network volume to attach to your Worker so that it can cache the LLM and decrease cold start times. If you do not use a network volume, the Worker will have to download the model every time it spins back up, leading to increased latency and resource consumption.

1. Log in to your RunPod account.  
2. Navigate to the **Serverless** section and select **New Endpoint**.  
3. Choose **CPU** and provide a name for your Endpoint (for example, `8 vCPUs 16 GB RAM`).  
4. Configure your Worker settings according to your needs.  
5. In the **Container Image** field, enter:
   ```
   pooyaharatian/runpod-ollama:0.0.8
   ```
6. In the **Container Start Command** field, specify the Ollama-supported model (e.g. `orca-mini` or `llama3.1`).  
7. Allocate sufficient container disk space for your model (typically 20 GB).  
8. *(Optional)* In Environment Variables, set `OLLAMA_MODELS` to `/runpod-volume` to store the model on your attached volume.  
9. Click **Deploy** to initiate the setup.

Once the Worker is ready and your model is downloaded, proceed to send a test request.

Sending a Run request
---------------------

1. Go to the **Requests** section in the RunPod web UI.  
2. In the input module, enter the following JSON:

   ```json
   {
     "input": {
       "method_name": "generate",
       "input": {
         "prompt": "why the sky is blue?"
       }
     }
   }
   ```

3. Select **Run** to execute the request.  
4. Wait a few seconds for a response, which should look like:

   ```json
   {
     "delayTime": 153,
     "executionTime": 4343,
     "id": "c2cb6af5-c822-4950-bca9-5349288c001d-u1",
     "output": {
       "context": [
         "omitted for brevity"
       ],
       "created_at": "2024-05-17T16:56:29.256938735Z",
       "done": true,
       "eval_count": 118,
       "eval_duration": 807433000,
       "load_duration": 3403140284,
       "model": "orca-mini",
       "prompt_eval_count": 46,
       "prompt_eval_duration": 38548000,
       "response": "The sky appears blue because of a process called scattering...",
       "total_duration": 4249684714
     },
     "status": "COMPLETED"
   }
   ```

With your Endpoint set up, you can now integrate it into your application as needed.

Conclusion
----------

You have successfully set up and run an Ollama server on a RunPod CPU. Now you can handle inference requests using your deployed model.

For further exploration, check out:

- [Runpod Ollama repository](https://github.com/pooyaharatian/runpod-ollama)  
- [RunPod Ollama container image](https://hub.docker.com/r/pooyaharatian/runpod-ollama)

-------------------------------------------------------------------------------
RUN YOUR FIRST FAST STABLE DIFFUSION WITH JUPYTER NOTEBOOK
==========================================================

Overview
--------

By the end of this tutorial, you’ll have deployed a Jupyter Notebook to RunPod, deployed an instance of Stable Diffusion, and generated your first image.

**Time to complete:** ~20 minutes

Prerequisites
-------------

- Hugging Face user access token  
- RunPod infrastructure  

Steps
-----

1. **Select RunPod Fast Stable Diffusion**  
   - Choose `1x RTX A5000` or `1x RTX 3090`  
   - Select **Start Jupyter Notebook**  
   - Deploy.

2. **Run the notebook**  
   - Select `RNPD-A1111.ipynb`.  
   - Enter your Hugging Face user access token.  
   - Select the model you want to run: `v.1.5`, `v2-512`, or `v2-768`.

3. **Launch Automatic1111 on your pod**  
   - The cell labeled **Start Stable-Diffusion** will launch your pod.  
   - *(Optional)* Provide login credentials for this instance.  
   - Select the blue link ending in `.proxy.runpod.net`.

4. **Explore Stable-Diffusion**  
   - Now that your pod is up and running Stable-Diffusion, explore and run the model.

-------------------------------------------------------------------------------
RUN FOOOCUS IN JUPYTER NOTEBOOK
===============================

Overview
--------

Fooocus is an open-source image generating model.

In this tutorial, you'll run Fooocus in a Jupyter Notebook and then launch the Gradio-based interface to generate images.

**Time to complete:** ~5 minutes

Prerequisites
-------------

- **Minimum**
  - 4GB Nvidia GPU memory (4GB VRAM)
  - 8GB system memory (8GB RAM)

- **RunPod infrastructure**
  1. Select **Pods** and choose `+ GPU Pod`.
  2. Choose a GPU instance with at least 4GB VRAM and 8GB RAM by selecting **Deploy**.
  3. Search for a template that includes Jupyter Notebook and select **Deploy**.
  4. Select **RunPod Pytorch 2**.
  5. Ensure **Start Jupyter Notebook** is selected.
  6. Select **Choose** and then **Deploy**.

Run the Notebook
----------------

1. Select **Connect to Jupyter Lab**.
2. In the Jupyter Lab file browser, select **File > New > Notebook**.
3. In the first cell, paste the following and then run the Notebook:

   ```bash
   !pip install pygit2==1.12.2
   !pip install opencv-python==4.9.0.80
   %cd /workspace
   !git clone https://github.com/lllyasviel/Fooocus.git
   %cd /workspace/Fooocus
   !python entry_with_update.py --share
   ```

Launch UI
---------

Look for the line:

```
App started successful. Use the app with ....
```

and select the link.

Explore the model
-----------------

Explore and run the model as desired.

-------------------------------------------------------------------------------
SET UP OLLAMA ON YOUR GPU POD
=============================

This tutorial will guide you through setting up Ollama, a powerful platform serving large language model, on a GPU Pod using RunPod. Ollama makes it easy to run, create, and customize models.

In the following tutorial, you'll set up a Pod on a GPU, install and serve the Ollama model, and interact with it on the CLI.

Prerequisites
-------------

- A RunPod account with credits (no other prior knowledge needed).

Step 1: Start a PyTorch Template on RunPod
------------------------------------------

1. Log in to your RunPod account and choose `+ GPU Pod`.
2. Choose a GPU Pod like **A40**.
3. From the available templates, select the latest **PyTorch** template.
4. Select **Customize Deployment**.
   - Add the port `11434` to the list of exposed ports.
   - Add the following environment variable to your Pod to allow Ollama to bind to the HTTP port:

     ```
     Key: OLLAMA_HOST
     Value: 0.0.0.0
     ```

5. Select **Set Overrides**, **Continue**, then **Deploy**.

Once the Pod is up and running, you'll have access to a terminal in the RunPod interface.

Step 2: Install Ollama
----------------------

1. Select **Connect** and choose **Start Web Terminal**.
2. Make note of the Username and Password, then select **Connect to Web Terminal**.
3. Enter your username and password.

Install `lshw` so Ollama can automatically detect and utilize your GPU:

```bash
apt update
apt install lshw
```

Run the following command to install Ollama and send to the background:

```bash
(curl -fsSL https://ollama.com/install.sh | sh && ollama serve > ollama.log 2>&1) &
```

Step 3: Run an AI Model with Ollama
-----------------------------------

To run an AI model using Ollama, pass the model name:

```bash
ollama run [model name]
# ollama run llama2
# ollama run mistral
```

Step 4: Interact with Ollama via HTTP API
-----------------------------------------

With Ollama set up and running, you can now interact with it using HTTP API requests:

- **Get a list of models**:

  ```bash
  curl https://{POD_ID}-11434.proxy.runpod.net/api/tags
  # e.g. curl https://abcd1234-11434.proxy.runpod.net/api/tags
  ```

- **Make requests**:

  ```bash
  curl -X POST https://{POD_ID}-11434.proxy.runpod.net/api/generate -d '{
    "model": "mistral",
    "prompt": "Here is a story about llamas eating grass"
  }'
  ```

-------------------------------------------------------------------------------
BUILD DOCKER IMAGES ON RUNPOD WITH BAZEL
========================================

RunPod's GPU Pods use custom Docker images to run your code. You cannot directly spin up your own Docker instance or build Docker containers on a GPU Pod. Tools like Docker Compose are also unavailable. However, you can build custom Docker images on RunPod using **Bazel**.

Prerequisites
-------------

- Docker Hub account and access token
- Enough volume space for building an image

Steps
-----

1. **Create a Pod**
   - Navigate to **Pods** and select **+ Deploy**.
   - Choose between GPU and CPU.
   - Specify an instance type, optionally attach a Network volume, etc.

2. **Connect to your Pod** via the Web Terminal.

3. **Clone the example GitHub repository**:

   ```bash
   git clone https://github.com/therealadityashankar/build-docker-in-runpod.git && cd build-docker-in-runpod
   ```

4. **Install dependencies**:

   ```bash
   apt update && apt install -y sudo
   curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh
   docker login -u <your-username>
   # paste in your Docker Hub access token
   ```

   ```bash
   wget https://github.com/bazelbuild/bazelisk/releases/download/v1.20.0/bazelisk-linux-amd64
   chmod +x bazelisk-linux-amd64
   sudo cp ./bazelisk-linux-amd64 /usr/local/bin/bazel
   ```

5. **Configure the Bazel Build** by editing the `BUILD.bazel` file:

   ```bash
   sudo apt install nano
   nano BUILD.bazel
   ```

   Replace `{YOUR_USERNAME}` with your Docker Hub username.

6. **Build and Push the Docker Image**:

   ```bash
   bazel run //:push_custom_image
   ```

7. **Check Docker Hub** to see your newly pushed image.

-------------------------------------------------------------------------------
HOW TO CONNECT TO A POD INSTANCE THROUGH VSCODE
==============================================

This tutorial explains how to connect directly to your Pod instance through VSCode, allowing you to work within your volume directory as if the files were on your local machine.

Prerequisites
-------------

- VSCode installed
- Basic command-line operations and SSH
- SSH key setup with RunPod (see [Use SSH](https://docs.runpod.io))
- A RunPod account

Create a Pod instance
---------------------

1. Navigate to **Pods** and select **+ Deploy**.
2. Choose between GPU and CPU.
3. *(Optional)* Specify a Network volume.
4. Select an instance type. For example, A40.
5. *(Optional)* Provide a template (e.g., RunPod Pytorch).
6. *(GPU only)* Specify your compute count.
7. Review your configuration and select **Deploy On-Demand**.

Establish a connection
----------------------

1. From the Pods page, select the Pod you just deployed.
2. Select **Connect** and copy the `SSH over exposed TCP: (Supports SCP & SFTP)` command. E.g.:

   ```
   ssh root@123.456.789.80 -p 12345 -i ~/.ssh/id_ed12345
   ```

3. Configure VSCode for remote development:

   - Install the **Dev Container** extension.
   - Open the Command Palette (CTRL+SHIFT+P) and choose **Remote-SSH: Add New SSH Host**.
   - Enter the copied SSH command and save to `~/.ssh/config`, like:

     ```
     Host your_pod_instance
         HostName 123.456.789.80
         User root
         Port 12345
         IdentityFile ~/.ssh/id_ed12345
     ```

   - In the Command Palette, select **Remote-SSH: Connect to Host** and choose your newly added host.

You are now connected to your Pod instance in VSCode.

-------------------------------------------------------------------------------
FINE TUNE AN LLM WITH AXOLOTL ON RUNPOD
=======================================

**note**
RunPod provides an easier method to fine tune an LLM. For more information, see *Fine tune a model*.

`axolotl` is a tool that simplifies training of large language models (LLMs). It provides a streamlined workflow for fine-tuning AI models. When combined with RunPod's GPUs, Axolotl enables efficient training of LLMs.

In this tutorial, we’ll walk through training an LLM using Axolotl on RunPod and uploading your model to Hugging Face.

Setting up the environment
--------------------------

1. **Create a Pod**:
   - Select a GPU instance.
   - Specify the Docker image:
     ```
     axolotlai/axolotl-cloud:main-latest
     ```
   - Deploy.

2. **Wait** for the Pod to start up, then connect over secure SSH.

Preparing the dataset
---------------------

You can use either:

- **Local dataset**
  - Transfer it using `runpodctl` from your local machine to RunPod.

- **Hugging Face dataset**
  - Specify its path in the `lora.yaml` configuration.

Updating requirements and preprocessing data
-------------------------------------------

```bash
git clone https://github.com/OpenAccess-AI-Collective/axolotl
cd axolotl
pip3 install packaging ninja
pip3 install -e '.[flash-attn,deepspeed]'
```

Update the `lora.yml` with your dataset path and other training settings. Then:

```bash
CUDA_VISIBLE_DEVICES=""
python -m axolotl.cli.preprocess examples/openllama-3b/lora.yml
```

Fine-tuning the LLM
-------------------

```bash
accelerate launch -m axolotl.cli.train examples/openllama-3b/lora.yml
```

Inference
---------

```bash
accelerate launch -m axolotl.cli.inference examples/openllama-3b/lora.yml --lora_model_dir="./lora-out"
```

Merge the model
---------------

```bash
python3 -m axolotl.cli.merge_lora examples/openllama-3b/lora.yml --lora_model_dir="./lora-out"
```

Upload the model to Hugging Face
--------------------------------

```bash
huggingface-cli login
huggingface-cli repo create your_model_name --type model
huggingface-cli upload your_model_name path_to_your_model
```

Conclusion
----------

By following these steps and leveraging Axolotl with RunPod, you can efficiently fine-tune LLMs for custom use cases.

-------------------------------------------------------------------------------
PYTHON EXAMPLES AND RUNPOD BACKGROUND
=====================================

Below are examples and background details on how to use RunPod with **Python**, including how to install the RunPod SDK, authenticate your requests, and interact with endpoints.

Overview
--------

Get started setting up your RunPod projects using Python. Depending on your needs, there are various ways to interact with the RunPod platform. This guide provides a straightforward approach to get you up and running.

Install the RunPod SDK
----------------------

Create a Python virtual environment to manage dependencies separately. Then install the **RunPod SDK** library.

On macOS or Linux (example):
```bash
python3 -m venv env
source env/bin/activate
python -m pip install runpod
```

On Windows (example):
```bash
python -m venv env
env\Scripts\activate
python -m pip install runpod
```

Get RunPod SDK version
----------------------

**Using pip**:
```bash
pip show runpod
# Expected output: runpod==1.x.x
```

You can find the latest RunPod Python SDK version on [GitHub](https://github.com/runpod/runpod-python).

Add your API key
----------------

```python
import runpod
import os

runpod.api_key = os.getenv("RUNPOD_API_KEY")
```

> **Note:** Use environment variables (e.g., `RUNPOD_API_KEY`) for security.

APIs and Basic Usage
--------------------

Below are some basic Python methods for working with the RunPod platform. These methods assume you have set:

```python
import runpod
import os

runpod.api_key = os.getenv("RUNPOD_API_KEY")
```

Get Endpoints
-------------

```python
endpoints = runpod.get_endpoints()
print(endpoints)
```

Create Template
---------------

```python
try:
    new_template = runpod.create_template(
        name="test",
        image_name="runpod/base:0.1.0"
    )
    print(new_template)
except runpod.error.QueryError as err:
    print(err)
    print(err.query)
```

Create Endpoint
---------------

```python
try:
    # Create a template first
    new_template = runpod.create_template(
        name="test",
        image_name="runpod/base:0.4.4",
        is_serverless=True
    )
    print(new_template)

    # Create an endpoint
    new_endpoint = runpod.create_endpoint(
        name="test",
        template_id=new_template["id"],
        gpu_ids="AMPERE_16",
        workers_min=0,
        workers_max=1
    )
    print(new_endpoint)
except runpod.error.QueryError as err:
    print(err)
    print(err.query)
```

Get GPUs
--------

```python
import json

gpus = runpod.get_gpus()
print(json.dumps(gpus, indent=2))
```

Get GPU by Id
-------------

```python
import json

gpu_info = runpod.get_gpu("NVIDIA A100 80GB PCIe")
print(json.dumps(gpu_info, indent=2))
```

These functions allow you to dynamically manage computational resources on RunPod.

---

**That concludes the Markdown reformatting with ASCII-style headings and Python-focused examples.**
```

---

That’s the entire re-formatted text in a single Markdown block. Feel free to adapt further as needed!