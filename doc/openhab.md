# OpenHab Server
[OpenHab](https://www.openhab.org) is an agnostic open source automation software to control your smart devices at home.

- [Install](#install)


## Install
```bash
wget -qO - 'https://openhab.jfrog.io/artifactory/api/gpg/key/public' | sudo apt-key add -
echo 'deb https://openhab.jfrog.io/artifactory/openhab-linuxpkg stable main' | sudo tee /etc/apt/sources.list.d/openhab.list
sudo apt update
sudo apt install openhab
```

Start and enable the services

```bash
sudo systemctl start openhab.service
sudo systemctl status openhab.service
sudo systemctl daemon-reload
sudo systemctl enable openhab.service
```

Create an account at http://openhab-device:8080