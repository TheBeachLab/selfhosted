# Minecraft server

I'm not too much in Minecraft. but both my sons are... so by popular demand...

## Java (Computer)

Check thah java is installed `java --version`.

```bash
ml@thebeachlab:~$ java --version
openjdk 11.0.9 2020-10-20
OpenJDK Runtime Environment (build 11.0.9+11-Ubuntu-0ubuntu1.20.04)
OpenJDK 64-Bit Server VM (build 11.0.9+11-Ubuntu-0ubuntu1.20.04, mixed mode, sharing)
```

 Otherwise install `sudo apt install openjdk-8-jre-headless`.

Download and configure the server

Go to <https://www.minecraft.net/en-us/download/server> and download the server

`wget https://launcher.mojang.com/v1/objects/35139deedbd5182953cf1caa23835da59ca3d7cd/server.jar`

Run it `java -Xmx1024M -Xms1024M -jar server.jar nogui` (start with 1GB RAM and max 1GB RAM) and you will see some EULA errors, that's fine. Edit `nano eula.txt` and change `eula=true`.

Now configure some settings `nano server.properties` and open ports in the firewall

## Bedrock (iPad)

This is the manual procedure of this <https://github.com/TheRemote/MinecraftBedrockServer> approach.

```bash
mkdir minecraft-bedrock
cd minecraft-bedrock
wget https://minecraft.azureedge.net/bin-linux/bedrock-server-1.16.40.02.zip
unzip bedrock-server-1.16.40.02.zip
```

Edit `server.properties`, open ports in the firewall  and run

`LD_LIBRARY_PATH=. ./bedrock_server`

### Automate the server as a service

Create `start.sh` and make it executable

```bash
#!/bin/bash
# Author: James Chambers
# Modified by Fran Sanchez
# Minecraft Bedrock server startup script using screen

# Check if server is already started
if screen -list | grep -q "servername"; then
    echo "Server is already started!  Press screen -r servername to open it"
    exit 1
fi

# Check if network interfaces are up
NetworkChecks=0
DefaultRoute=$(route -n | awk '$4 == "UG" {print $2}')
while [ -z "$DefaultRoute" ]; do
    echo "Network interface not up, will try again in 1 second";
    sleep 1;
    DefaultRoute=$(route -n | awk '$4 == "UG" {print $2}')
    NetworkChecks=$((NetworkChecks+1))
    if [ $NetworkChecks -gt 20 ]; then
        echo "Waiting for network interface to come up timed out - starting server without network connection ..."
        break
    fi
done

# Change directory to server directory
DirName=/root/minecraft-bedrock
cd $DirName

# Create backup
if [ -d "worlds" ]; then
    echo "Backing up server (to backups folder)"
    tar -pzvcf backups/$(date +%Y.%m.%d.%H.%M.%S).tar.gz worlds
fi

# Retrieve latest version of Minecraft Bedrock dedicated server
echo "Checking for the latest version of Minecraft Bedrock server ..."

# Test internet connectivity first
wget --spider --quiet https://minecraft.net/en-us/download/server/bedrock/
if [ "$?" != 0 ]; then
    echo "Unable to connect to update website (internet connection may be down).  Skipping update ..."
else
    # Download server index.html to check latest version
    wget -O downloads/version.html https://minecraft.net/en-us/download/server/bedrock/
    DownloadURL=$(grep -o 'https://minecraft.azureedge.net/bin-linux/[^"]*' downloads/version.html)
    DownloadFile=$(echo "$DownloadURL" | sed 's#.*/##')

    # Download latest version of Minecraft Bedrock dedicated server if a new one is available
    if [ -f "downloads/$DownloadFile" ]
    then
        echo "Minecraft Bedrock server is up to date..."
    else
        echo "New version $DownloadFile is available.  Updating Minecraft Bedrock server ..."
        wget -O "downloads/$DownloadFile" "$DownloadURL"
        unzip -o "downloads/$DownloadFile" -x "*server.properties*" "*permissions.json*" "*whitelist.json*"
    fi
fi

echo "Starting Minecraft server.  To view window type screen -r servername"
echo "To minimize the window and let the server run in the background, press Ctrl+A then Ctrl+D"
screen -L -Logfile logs/$(date +%Y.%m.%d.%H.%M.%S).log -dmS servername /bin/bash -c "LD_LIBRARY_PATH=$DirName $DirName/bedrock_server"
```

Create `stop.sh` and make it executable

```bash
#!/bin/bash
# James Chambers
# Minecraft Server stop script - primarily called by minecraft service but can be ran manually

# Check if server is running
if ! screen -list | grep -q "servername"; then
  echo "Server is not currently running!"
  exit 1
fi

# Get an optional custom countdown time (in minutes)
CountdownTime=0
while getopts ":t" opt; do
  case $opt in
    t)
      case $string in
        ''|*[!0-9]*) 
          echo "Countdown time must be a whole number in minutes."
          exit 1
          ;;
        *) 
          CountdownTime=$OPTARG >&2 
          ;;
      esac
      ;;
    \?)
      echo "Invalid option: -$OPTARG; countdown time must be a whole number in minutes." >&2
      ;;
  esac
done

# Stop the server
while [ $CountdownTime -gt 0 ]; do
  if [ $CountdownTime -eq 1 ]; then
    screen -Rd servername -X stuff "say Stopping server in 60 seconds...$(printf '\r')"
    sleep 30;
    screen -Rd servername -X stuff "say Stopping server in 30 seconds...$(printf '\r')"
    sleep 20;
    screen -Rd servername -X stuff "say Stopping server in 10 seconds...$(printf '\r')"
    sleep 10;
  else
    screen -Rd servername -X stuff "say Stopping server in $CountdownTime minutes...$(printf '\r')"
    sleep 60;
  fi
  echo "Waiting for $CountdownTime more minutes ..."
done
echo "Stopping Minecraft server ..."
screen -Rd servername -X stuff "say Stopping server (stop.sh called)...$(printf '\r')"
screen -Rd servername -X stuff "stop$(printf '\r')"

# Wait up to 20 seconds for server to close
StopChecks=0
while [ $StopChecks -lt 20 ]; do
  if ! screen -list | grep -q "servername"; then
    break
  fi
  sleep 1;
  StopChecks=$((StopChecks+1))
done

# Force quit if server is still open
if screen -list | grep -q "servername"; then
  echo "Minecraft server still hasn't stopped after 20 seconds, closing screen manually"
  screen -S servername -X quit
fi

echo "Minecraft server stopped."
```

Create `restart.sh` and make it executable

```bash
#!/bin/bash
# James Chambers
# Minecraft Bedrock Server restart script

# Check if server is started
if ! screen -list | grep -q "servername"; then
    echo "Server is not currently running!"
    exit 1
fi

echo "Sending restart notifications to server..."

# Start countdown notice on server
screen -Rd servername -X stuff "say Server is restarting in 30 seconds! $(printf '\r')"
sleep 23s
screen -Rd servername -X stuff "say Server is restarting in 7 seconds! $(printf '\r')"
sleep 1s
screen -Rd servername -X stuff "say Server is restarting in 6 seconds! $(printf '\r')"
sleep 1s
screen -Rd servername -X stuff "say Server is restarting in 5 seconds! $(printf '\r')"
sleep 1s
screen -Rd servername -X stuff "say Server is restarting in 4 seconds! $(printf '\r')"
sleep 1s
screen -Rd servername -X stuff "say Server is restarting in 3 seconds! $(printf '\r')"
sleep 1s
screen -Rd servername -X stuff "say Server is restarting in 2 seconds! $(printf '\r')"
sleep 1s
screen -Rd servername -X stuff "say Server is restarting in 1 second! $(printf '\r')"
sleep 1s
screen -Rd servername -X stuff "say Closing server...$(printf '\r')"
screen -Rd servername -X stuff "stop$(printf '\r')"

echo "Closing server..."
# Wait up to 30 seconds for server to close
StopChecks=0
while [ $StopChecks -lt 30 ]; do
  if ! screen -list | grep -q "servername"; then
    break
  fi
  sleep 1;
  StopChecks=$((StopChecks+1))
done

if screen -list | grep -q "servername"; then
    # Server still hasn't stopped after 30s, tell Screen to close it
    echo "Minecraft server still hasn't closed after 30 seconds, closing screen manually"
    screen -S servername -X quit
    sleep 10
fi

# Start server
/bin/bash /root/minecraft-bedrock/start.sh
```

Create `minecraft.service`

```bash
[Unit]
Description=minecraft server
After=network-online.target

[Service]
User=root
WorkingDirectory=/root/minecraft-bedrock
Type=forking
ExecStart=/bin/bash /root/minecraft-bedrock/start.sh
ExecStop=/bin/bash /root/minecraft-bedrock/stop.sh
ExecRestart=/bin/bash /root/minecraft-bedrock/restart.sh
GuessMainPID=no
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
```

And link it in systemd, and reload, enable, start the service:

```bash
ln -s /root/minecraft-bedrock/minecraft.service /etc/systemd/system/minecraft.service`
systemctl daemon-reload
systemctl enable minecraft
systemctl start minecraft
```

Create a cron to restart the server everyday at 4 am, which also creates a backup. Check the status

```
# restart minecraft at 4am
0 4 * * * /usr/bin/systemctl restart minecraft
```
