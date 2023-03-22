# Nodejs server

This server is useful to execute backend commands in the computer hosting a website. We will generate a `server.js` file that node will run. We will keep the server running in the background by using the process manager PM2.

## Create a user that will run PM2

It is generally recommended to run PM2 as a regular user rather than as the root user. This is because running processes as the root user can pose a security risk and may cause issues with file permissions and other system resources.

`sudo adduser pm2user`
