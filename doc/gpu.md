# GPU server for machine learning

**Author:** Fran

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


## eGPU stability (Thunderbolt / Razer Core X)

**Author:** Mr. Watson 🦄
**Date:** 2026-03-03

### Historical Xid notes, not a confirmed root cause

Older internal notes attribute the runtime failure to a GSP firmware crash. That
attribution is not externally verified and must not be treated as a diagnosis:
Xid values are diagnostic starting points, not root-cause identifiers. NVIDIA
documents Xid 154 as a report of the recovery action required by another Xid,
and recommends preserving an `nvidia-bug-report` for driver investigation.
Sources: [NVIDIA Xid error guide](https://docs.nvidia.com/deploy/xid-errors/working-with-xid-errors.html) and
[NVIDIA GPU debug guidelines](https://docs.nvidia.com/deploy/gpu-debug-guidelines/index.html).

The known operational symptom is narrower: the RTX 2070 Super in the Razer Core
X enumerates and works after boot, then may hang or disappear after minutes or
hours of GPU workload. The enclosure being powered off currently is expected;
`boltctl: disconnected` in that state is not failure evidence.

Signature in `dmesg`/`journalctl -k`:

```
NVRM: Xid 62   — GPU error event
NVRM: Xid 119  — GSP RPC timeout after 45s
NVRM: Xid 154  — GPU Reset Required (reset fails, GPU stuck)
```

Check current GPU state:

```bash
nvidia-smi
# ERR! in temperature/util columns = GPU needs reboot
sudo journalctl -k | grep -i "NVRM\|Xid"
```

### Existing setting 1: keep GPU awake (`nvidia-persistenced`)

The host has this setting. It keeps the driver state initialized between jobs,
but it has not been proven to prevent the runtime failure and cannot repair a
lost PCIe/Thunderbolt link:

```bash
sudo mkdir -p /etc/systemd/system/nvidia-persistenced.service.d
sudo tee /etc/systemd/system/nvidia-persistenced.service.d/override.conf << 'CONF'
[Unit]
StopWhenUnneeded=false

[Service]
ExecStart=
ExecStart=/usr/bin/nvidia-persistenced --user nvidia-persistenced --verbose

[Install]
WantedBy=multi-user.target
CONF

sudo systemctl daemon-reload
sudo systemctl enable nvidia-persistenced
sudo systemctl restart nvidia-persistenced
nvidia-smi -q | grep "Persistence Mode"   # should show: Enabled
```

### Existing setting 2: disable GSP firmware

The host already has this setting in `/etc/modprobe.d/nvidia-no-gsp.conf`. It
must be verified with the Core X online after each driver change. Do not claim
that it eliminates a particular Xid or that it fixes a bus-loss event without a
reproduced before/after test:

```bash
echo 'options nvidia NVreg_EnableGpuFirmware=0' | sudo tee /etc/modprobe.d/nvidia-no-gsp.conf
sudo update-initramfs -u
sudo reboot
```

Verify the module setting after reboot while the Core X is online. The absence of
a particular Xid is not proof that the setting fixed the runtime failure.

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ERR!` in `nvidia-smi` | Driver reports an unhealthy GPU | Preserve the first Xid/AER evidence, then reset or reboot as required |
| `nvidia-smi` returns `[N/A]` / `[GPU requires reset]` | GPU recovery is required | Preserve the first Xid/AER evidence, then reset or reboot as required |
| Xid 119 recurring | Driver/GSP event; root cause unproven here | Preserve `nvidia-bug-report` and correlate with kernel/PCIe logs |
| GPU goes to sleep between jobs, won't wake | Persistence mode off | Enable `nvidia-persistenced` and retest |
| `boltctl` reports the enclosure as disconnected and `lspci` has no NVIDIA device | Thunderbolt/PCIe link is not established; NVIDIA cannot initialize a device that PCIe does not expose | Check firmware, BIOS Thunderbolt settings, cable and enclosure power before changing NVIDIA drivers |

### Thunderbolt link diagnosis

When the enclosure is disconnected in `boltctl` and no NVIDIA device appears in
`lspci`, treat `nvidia-smi` failure as a downstream symptom. Driver changes will
not repair a missing PCIe device.

An operator check on 2026-06-13 found the installed firmware newer than the
proposed downgrade target and found no newer system firmware through the host's
normal update service. This is an internal observation, not externally verified
evidence about the cause. Do not downgrade solely to troubleshoot this symptom.

Follow the vendor's current guidance instead:

- [ASUS NUC BIOS update and recovery instructions](https://www.asus.com/support/faq/1052506/)
- [ASUS NUC Thunderbolt device troubleshooting](https://www.asus.com/support/faq/1052760/)

ASUS advises against BIOS downgrades and recommends checking that the
Thunderbolt controller is enabled, using current firmware and drivers, and
testing with a certified short Thunderbolt cable.

### Current research and runtime stability test (2026-08-04)

**Externally verified:** ASUS still lists BIOS Full Package Update `0078`
(2024-10-28) as the newest BIOS package for `NUC11TNKi3`; do not search for or
install a newer BIOS as an eGPU remedy. The newer `NUC Firmware Integrator
Tool` shown on the same support page is a tool for building custom firmware
images, not a newer system or Thunderbolt controller firmware release.
Source: [ASUS NUC11TNKi3 BIOS and firmware support](https://www.asus.com/us/supportonly/nuc11tnki3/helpdesk_bios/).

**Verified on the host (2026-08-04; internal operational observation):**

- BIOS is `TNTGL357.0078.2024.0930.2018`.
- The running kernel command line includes both `pcie_port_pm=off` and
  `pcie_aspm=off`.
- Both Thunderbolt domains report `security=none`; the Linux kernel defines
  this as automatic device connection, so authorization is not currently
  blocking PCIe tunneling. At the time of this observation the Core X was
  deliberately powered off, so its absence from the live Thunderbolt topology,
  `boltctl` reporting it as `disconnected`, and the lack of an NVIDIA PCIe
  device are expected and are **not diagnostic evidence of a current fault**.

The Linux meaning of `security=none` is documented in
[USB4 and Thunderbolt](https://docs.kernel.org/admin-guide/thunderbolt.html).
Do not change the BIOS security level to `DP++ only`: the Visual BIOS glossary
states that it disables PCIe tunneling, which an eGPU requires. Source:
[Intel NUC Visual BIOS Glossary](https://kmpic.asus.com/images/nuc/NUC-Visual-BIOS-Glossary.pdf).

**Operator correction (2026-08-04; internal operational observation):** the
eGPU reliably enumerates and starts working after boot. The failure occurs only
after minutes or hours of GPU use, when the GPU hangs or disappears. This is a
runtime stability problem, not an initial-detection problem. A `disconnected`
result while the Core X is powered off must not be used as failure evidence.

The next test must therefore reproduce the normal GPU workload and preserve
the first kernel evidence of the failure. The eGPU reportedly ran reliably for
an extended period, so a later kernel or NVIDIA driver regression is plausible
but unverified.

#### Kernel/NVIDIA regression test

**Internal package-history evidence (not externally verified as a root
cause):**

| Date | Change | What it proves |
|---|---|---|
| 2026-06-10 | NVIDIA `595.71.05` installed | A local restore record from the same day says `595.71.05`, the Core X, and `nvidia-smi` worked. This is a useful baseline, not proof that every later failure is a driver regression. |
| 2026-06-12 | HWE kernel `6.8.0-124` installed | The host moved from the 5.15 GA series to HWE 6.8. |
| 2026-07-10 | HWE kernel `6.8.0-134` installed | This kernel and its matching NVIDIA 595 module remain installed. |
| 2026-07-24 | NVIDIA `595.71.05` -> `595.84` and HWE `6.8.0-134` -> `6.8.0-136` | Two variables changed together, so the history cannot identify a culprit. |

Ubuntu describes `595.84` only as a new upstream NVIDIA release; no official
release note found in this research ties it to a Core X, Tiger Lake, or
Thunderbolt regression. Source:
[Ubuntu Jammy change notice for 595.84](https://lists.ubuntu.com/archives/jammy-changes/2026-July/047368.html).
This absence is not proof that the package is sound on this host.

Test the still-installed `6.8.0-134-generic` before downgrading NVIDIA:

1. With the Core X powered and attached before boot, establish a baseline on
   the default `6.8.0-136-generic` boot. Record the start time, confirm that
   the GPU is initially healthy, then run the same ComfyUI, Whisper, RAG, or
   TTS workload that normally triggers the failure:

```bash
start=$(date --iso-8601=seconds)
uname -r
nvidia-smi
lspci -nn | grep -i nvidia
```

2. At the first hang or loss of GPU access, preserve the evidence before
   rebooting:

```bash
nvidia-smi
journalctl -k -b --since "$start" --no-pager | grep -Ei 'NVRM|Xid|fallen off|thunderbolt|pciehp|Link Down'
sudo nvidia-bug-report.sh --safe-mode --extra-system-data
```

`nvidia-bug-report.sh` can take up to an hour; it is the NVIDIA-recommended
collection for a driver issue. The current journal keeps only recent boots, so
copy the resulting archive off the host before rebooting. A historical telemetry
cut between 2026-06-14 21:35 and 21:53 UTC is insufficient to identify the
cause: it has no retained Xid/AER record, and the Core X may have been powered
off or disconnected during that interval.

The current telemetry publisher calls `/usr/local/bin/nvidia-smi-safe.sh`. That
wrapper times out `nvidia-smi` after five seconds and emits `gpu: null` both
when the enclosure is intentionally off and when the driver query fails. Treat
`gpu: null` as a prompt to inspect `lspci`, `boltctl`, and the kernel log; it is
not by itself evidence of a runtime eGPU fault.

3. Reboot once into `Advanced options for Ubuntu` ->
   `Ubuntu, with Linux 6.8.0-134-generic`; this keeps NVIDIA `595.84` fixed
   and changes only the kernel. The normal default remains `6.8.0-136`, so a
   later ordinary reboot returns to the current kernel.
4. Repeat the same workload and capture sequence, not merely the initial
   `nvidia-smi` check.

Interpretation:

- `6.8.0-134` survives a workload that reproducibly hangs `6.8.0-136`: a
  6.8.136 regression or its interaction with this host is plausible. Keep
  6.8.134 only after confirming the A/B result, then report it to Ubuntu with
  both boot logs.
- both initially work but both hang with the same kernel evidence: kernel
  6.8.136 alone is not implicated. Plan a controlled NVIDIA `595.71.05`
  rollback next, using a matched package set and preserving the failure logs.
- neither hangs during equivalent workload: no persistent regression is
  demonstrated. Retain the current packages and capture the first future
  failure before rebooting.

Do not downgrade NVIDIA before this A/B test: the current APT sources offer
only `595.84`, so rolling back to `595.71.05` would require deliberately
obtaining and pinning a matched package set. That is a larger, separate change
and should be done only if the kernel test does not explain the issue.

Only if a future cold boot fails to enumerate the eGPU at all, reset and test
the physical Thunderbolt chain:

1. Shut down the NUC completely. Do not hot-unplug/hot-replug while Linux is
   running.
2. Switch off the Razer Core X, unplug its mains cable, and leave both systems
   off for at least 30 seconds. Razer specifies this power cycle to refresh
   detection after Thunderbolt problems. Source:
   [Razer Core power-cycle instructions](https://mysupport.razer.com/app/answers/detail/a_id/1924/).
3. Reconnect power to the Core X, connect it to the NUC before boot, wait a few
   seconds, then power on the NUC. Use a certified Thunderbolt 3 cable no
   longer than 60 cm; the supplied Core X cable is 500 mm. Sources:
   [ASUS NUC Thunderbolt troubleshooting](https://www.asus.com/ca-en/support/faq/1052760/) and
   [Razer Core X specifications](https://mysupport.razer.com/app/answers/detail/a_id/3778/).
4. In Visual BIOS, confirm `Advanced > Devices > Onboard Devices > Thunderbolt
   Controller` is enabled. Do not alter the security level if Linux continues
   to show `security=none`; it is already the auto-connect setting.
5. After boot, verify in this order:

```bash
boltctl list
lspci -nn | grep -i nvidia
nvidia-smi
```

If step 3 still leaves the Core X `disconnected`, repeat the same cold-boot
test with the other Thunderbolt port and a known-good certified short cable.
That port/cable recommendation is an inference from the verified fact that no
live Thunderbolt device is detected; it is not an ASUS model-specific repair
procedure. If the Core X still works with macOS but neither NUC port sees it
after this controlled test, the remaining likely fault domain is the NUC
Thunderbolt hardware/firmware path and ASUS support is the appropriate
escalation.
