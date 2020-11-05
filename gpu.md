# GPU server for machine learning

<!-- vim-markdown-toc GFM -->

* [Install necessary packages](#install-necessary-packages)
* [Allow SSH UDP](#allow-ssh-udp)
* [Nvidia and Cuda](#nvidia-and-cuda)
* [Python](#python)

<!-- vim-markdown-toc -->

## Install necessary packages

```bash
sudo apt update
sudo apt -y upgrade
sudo apt -y install build-essential gcc g++ make binutils
sudo apt -y install software-properties-common git
sudo apt -y install cmake pkg-config
```

## Allow SSH UDP

Replace with your actual SSH port `sudo ufw allow 22/udp comment "ML"` and `sudo ufw reload`


## Nvidia and Cuda

This is just in case you need gpu accelerated encoders or decoders for video server. [Remove the nouveau kernel](https://tutorials.technology/tutorials/85-How-to-remove-Nouveau-kernel-driver-Nvidia-install-error.html) then download and install cuda and the driver from nvidia page. Check version `nvcc --version`.

## Python

```bash
sudo apt update
sudo apt install python3-pip python3-dev
sudo -H pip3 install virtualenv
```

TODO 
Create ML user
Install jupyterlab and pytorch


