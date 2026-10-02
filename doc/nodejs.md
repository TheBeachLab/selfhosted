# Node.js server

WIP. The PM2 user is covered below. The server.js example and deployment steps are still missing.

This server is useful to execute backend commands in the computer hosting a website. We will generate a `server.js` file that node will run. We will keep the server running in the background by using the process manager PM2.

- [Create a user that will run PM2](#create-a-user-that-will-run-pm2)

## Create a user that will run PM2

Create a regular user for PM2:

`sudo adduser pm2user`
