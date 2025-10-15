# GPU server for machine learning

<!-- vim-markdown-toc GFM -->

- [Install necessary packages](#install-necessary-packages)
- [Allow SSH UDP](#allow-ssh-udp)
- [Nvidia and Cuda](#nvidia-and-cuda)
- [Python](#python)
- [Create ML user](#create-ml-user)
- [Install JupyterLab and PyTorch](#install-jupyterlab-and-pytorch)
- [Open a remote jupyterlab session](#open-a-remote-jupyterlab-session)
- [Mount remote folder via SSHFS in Linux](#mount-remote-folder-via-sshfs-in-linux)
- [Mount remote folder via SSHFS (macOS)](#mount-remote-folder-via-sshfs-macos)

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
sudo apt install ubuntu-drivers autoinstall
```

## Python

```bash
sudo apt update
sudo apt install python3-pip python3-dev python-is-python3
sudo -H pip3 install virtualenv
```

## Create ML user

```bash
sudo adduser ml
sudo usermod -a -G sudo ml
sudo -u ml mkdir /home/ml/.ssh
sudo -u ml chmod 700 /home/ml/.ssh
sudo -u ml touch /home/ml/.ssh/authorized_keys
sudo -u ml chmod 600 /home/ml/.ssh/authorized_keys
sudo -u ml ssh-import-id gh:thebeachlab
```

If you want to disable 2FA for this user, edit `sudo nano /etc/pam.d/sshd` and add

`auth [success=done default=ignore] pam_succeed_if.so user ingroup ml`

before `auth required pam_google_authenticator.so`. Make sure you reload the ssh daemon `sudo service sshd restart`

Check the connection `ssh -p 22 ml@beachlab.org`

## Install JupyterLab and PyTorch

```bash
sudo -u ml -i
pip3 install torch torchvision
```

Check that pytorch with cuda is accessible

```bash
ml@thebeachlab:~$ python
Python 3.10.12 (main, Aug 15 2025, 14:32:43) [GCC 11.4.0] on linux
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

Install jupyterlab `pip3 install jupyterlab ipywidgets`

## Open a remote jupyterlab session

From your **laptop** `ssh -p 22 -CL 8899:localhost:8899 ml@beachlab.org` to connect to the server user ml. Recommended to add an `ml` alias to do so.

- `-C` for data compression
- `-L listen-port:host:port` for port forwarding

Start Jupyter Lab

`jupyter lab --no-browser --port=8899` or `jl` if you create an `alias jl="jupyter lab --no-browser --port=8899` in the ml `.bash_aliases`

Then **in your laptop browser** open the notebook with the provided token:

`http://localhost:8899/?token=LOTS-OF-NUMBERS-AND-LETTERS`

To **access without token** generate a config file `jupyter lab --generate-config` and set a password  `jupyter notebook password`. Then modify `nano ~/.jupyter/jupyter_notebook_config.py` to set an empty token `c.NotebookApp.token = ''`

## Mount remote folder via SSHFS in Linux

In your laptop install `sshfs`, then add a `fuse` group and add yourself to that group

```bash
[unix ~]$ sudo groupadd fuse
[unix ~]$ sudo usermod -a -G fuse unix
```

Logout and login for the changes to apply. Now you can create the mount point and mount the `ml` home folder

```bash
sudo mkdir /mnt/ml
sudo sshfs -p 622 -o allow_other,workaround=rename,noexec,idmap=user,uid=$(id -u),gid=$(id -g),default_permissions,IdentityFile=/home/unix/.ssh/id_rsa ml@beachlab.org:/home/ml /mnt/ml
```

And you will see that the files are mounted as if you were the owner

```bash
[unix /mnt/ml]$ ls -l
total 4.0K
drwxrwxr-x 1 unix users 4.0K Nov  6 10:54 data
```

And in the remote server

```bash
ml@thebeachlab:~$ ls -l
total 4
drwxrwxr-x 3 ml ml 4096 Nov  6 09:54 data
```

Unmount when not needed `sudo umount /mnt/ml/`

## Mount remote folder via SSHFS (macOS)

In your Mac, install **macFUSE** and **sshfs-mac** via Homebrew:

```bash
brew install --cask macfuse
# Approve the system extension in System Settings → Privacy & Security, then reboot.
brew install gromgit/fuse/sshfs-mac
```

Now create the mount point and mount the remote ml home folder:

```bash
mkdir -p ~/mnt/ml
sshfs -p 622 \
  -o allow_other,workaround=rename,noexec,idmap=user,uid=$(id -u),gid=$(id -g),reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,IdentityFile=~/.ssh/id_rsa \
  ml@beachlab.org:/home/ml ~/mnt/ml
```

You’ll now see the files as if you were the owner.

Unmount when not needed:

```bash
umount ~/mnt/ml
# or:
diskutil unmount force ~/mnt/ml
```

