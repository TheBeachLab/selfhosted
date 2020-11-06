# GPU server for machine learning

<!-- vim-markdown-toc GFM -->

* [Install necessary packages](#install-necessary-packages)
* [Allow SSH UDP](#allow-ssh-udp)
* [Nvidia and Cuda](#nvidia-and-cuda)
* [Python](#python)
* [Create ML user](#create-ml-user)
* [Install jupyterlab and pytorch](#install-jupyterlab-and-pytorch)
* [Open a remote jupyterlab session](#open-a-remote-jupyterlab-session)
* [Mount remote folder via SSHFS](#mount-remote-folder-via-sshfs)

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

This is just in case you need gpu accelerated encoders or decoders for video server. [Remove the nouveau kernel](https://tutorials.technology/tutorials/85-How-to-remove-Nouveau-kernel-driver-Nvidia-install-error.html) then download and install cuda and the driver. Check version `nvcc --version`.

```bash
sudo apt install nvidia-driver-455
sudo apt install cuda
```

Add the following to the end of `.bashrc` and `source .bashrc`

```bash
export CUDA_PATH=/usr
export PATH=$PATH:/usr/local/cuda-11.1/bin
```

## Python

```bash
sudo apt update
sudo apt install python3-pip python3-dev python-is-python3
sudo -H pip3 install virtualenv
```

## Create ML user

```bash
sudo adduser mlgpu
sudo usermod -a -G sudo mlgpu
mkdir .ssh
chmod 700 .ssh/
touch .ssh/authorized_keys
chmod 600 .ssh/authorized_keys
ssh-import-id gh:thebeachlab
```

If you want to disable 2FA for this user, edit `sudo nano /etc/pam.d/sshd` and add

`auth [success=done default=ignore] pam_succeed_if.so user ingroup mlgpu`

before `auth required pam_google_authenticator.so`. Make sure you reload the ssh daemon `sudo service sshd restart`

Check the connection `ssh -p 22 mlgpu@beachlab.org`

## Install jupyterlab and pytorch

```bash
su mlgpu
pip3 install torch torchvision
```

Check that pytorch with cuda is accessible

```bash
mlgpu@thebeachlab:~$ python
Python 3.8.5 (default, Jul 28 2020, 12:59:40)
[GCC 9.3.0] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> import torch
>>> print (torch.rand(5,3))
tensor([[0.8937, 0.2411, 0.1159],
        [0.9376, 0.5696, 0.0137],
        [0.7617, 0.7618, 0.3687],
        [0.1805, 0.9064, 0.2470],
        [0.9646, 0.5219, 0.2525]])
>>> torch.cuda.is_available()
True
```

Install jupyterlab `pip3 install jupyterlab`

> Note: Multiple warnings about `/home/ml/.local/bin` not in your lab.

## Open a remote jupyterlab session

From your laptop `ssh -p 22 -CL 8899:localhost:8899 mlgpu@beachlab.org` or add an `ml` alias to connect to the server and then start jupyter lab

- `-C` for data compression
- `-L listen-port:host:port` for port forwarding

`jupyter lab --no-browser --port=8899` or `jl` if you create an `alias jl="jupyter lab --no-browser --port=8899` in the mlgpu `.bash_aliases`

Then in your laptop browser open the notebook with the provided token:

`http://localhost:8899/?token=LOTS-OF-NUMBERS-AND-LETTERS`

To **access without token** generate a config file `jupyter lab --generate-config` and set a password  `jupyter notebook password`. Then modify `nano ~/.jupyter/jupyter_notebook_config.py` to set an empty token `c.NotebookApp.token = ''`

## Mount remote folder via SSHFS

In your laptop install `sshfs`, then add a `fuse` group and add yourself to that group

```bash
[unix ~]$ sudo groupadd fuse
[unix ~]$ sudo usermod -a -G fuse unix
```

Logout and login for the changes to apply. Now you can create the mount point and mount the `mlgpu` home folder

```bash
sudo mkdir /mnt/mlgpu
sudo sshfs -p 22 -o allow_other,workaround=rename,noexec,idmap=user,uid=$(id -u),gid=$(id -g),default_permissions,IdentityFile=/home/unix/.ssh/id_rsa ml@beachlab.org:/home/mlgpu /mnt/mlgpu
```

And you will see that the files are mounted as if you were the owner

```bash
[unix /mnt/mlgpu]$ ls -l
total 4.0K
drwxrwxr-x 1 unix users 4.0K Nov  6 10:54 data
```

And in the remote server

```bash
mlgpu@thebeachlab:~$ ls -l
total 4
drwxrwxr-x 3 ml ml 4096 Nov  6 09:54 data
```

Unmount when not needed `sudo umount /mnt/mlgpu/`
