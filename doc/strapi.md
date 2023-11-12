# Install
Create database sisterapi in postgres
```
CREATE USER strapi_user WITH PASSWORD 'whatever';
GRANT ALL PRIVILEGES ON DATABASE sisterapi TO strapi_user;
GRANT ALL PRIVILEGES ON SCHEMA public TO strapi_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO strapi_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO strapi_user;
```
Create a strapi user in Linux
```
sudo adduser --system --group --shell /bin/bash strapi
sudo mkdir -p /var/www/strapi
sudo chown strapi:strapi /var/www/strapi
```

Install node 20 LTS
```
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
NODE_MAJOR=20
echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | sudo tee /etc/apt/sources.list.d/nodesource.list
sudo apt-get update
sudo apt-get install nodejs -y
```

Install Yarn (optional but recommended): Yarn is often used as the package manager for Strapi:
`sudo npm install --global yarn`

Install Strapi: Switch to the strapi user and install Strapi using either npx or yarn:
```
sudo -i -u strapi
cd /var/www/strapi
yarn create strapi-app sisterapi
```

Follow instructions and give database user details created before.

Set up a process manager: To ensure that Strapi stays running, you should use a process manager like pm2. Install and set it up as follows:
```
mkdir ~/.npm-global
npm config set prefix '~/.npm-global'
export PATH=~/.npm-global/bin:$PATH
exit
sudo -i -u strapi
cd /var/www/strapi
npm install pm2@latest -g
cd /var/www/strapi/sisterapi
pm2 start npm --name sisterapi -- run start
pm2 startup
```

Then with sister user run:
```
sudo env PATH=$PATH:/usr/bin /home/strapi/.npm-global/lib/node_modules/pm2/bin/pm2 startup systemd -u strapi --hp /home/strapi
sudo chown -R strapi:strapi /var/www/strapi/sisterapi
```

Open ports
```
sudo ufw allow 1337 comment 'Strapi'
sudo ufw reload
sudo ufw status
```

Strapi user: `pm2 save`


