# PostgreSQL

- [Install](#install)
- [Upgrade](#upgrade)
- [Remote connection](#remote-connection)
- [Common psql commands](#common-psql-commands)
- [Create a new role](#create-a-new-role)
- [Create a new database](#create-a-new-database)
- [Open a postgres prompt with `iot` role](#open-a-postgres-prompt-with-iot-role)
- [TimescaleDB](#timescaledb)
- [Create a hypertable in `iot` database](#create-a-hypertable-in-iot-database)
- [Managing PostgreSQL with pgAdmin](#managing-postgresql-with-pgadmin)
  - [Install pgadmin4](#install-pgadmin4)
  - [Apache and nginx together](#apache-and-nginx-together)
  - [Creating a subdomain (optional)](#creating-a-subdomain-optional)
  - [Securing pgadmin with https (optional)](#securing-pgadmin-with-https-optional)
  - [Configure pgadmin](#configure-pgadmin)
  - [Running pgadmin](#running-pgadmin)
  - [Reset pgadmin password](#reset-pgadmin-password)
  - [unlock pgadmin account](#unlock-pgadmin-account)
  - [pgadmin storage](#pgadmin-storage)
- [SQL Tips and tricks](#sql-tips-and-tricks)
  - [Create a readonly user](#create-a-readonly-user)
  - [For every table](#for-every-table)
  - [Autoupdate the modified timestamp when a record is updated](#autoupdate-the-modified-timestamp-when-a-record-is-updated)
  - [New table from existing table](#new-table-from-existing-table)
  - [Add new column to existing table](#add-new-column-to-existing-table)
  - [Add one to many](#add-one-to-many)
  - [Create a JSON from a table](#create-a-json-from-a-table)


## Install

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
```

Check

```bash
pink@thebeachlab:~$ sudo -u postgres psql
psql (12.4 (Ubuntu 12.4-0ubuntu0.20.04.1))
Type "help" for help.

postgres=#
```

Exit with `\q`

## Upgrade

Check version running `sudo -u postgres psql -c 'SELECT version();'`

Output if you are currently runnin 12:

```bash
 PostgreSQL 12.12 (Ubuntu 12.12-0ubuntu0.20.04.1) on x86_64-pc-linux-gnu, compiled by gcc (Ubuntu 9.4.0-1ubuntu1~20.04.1) 9.4.0, 64-bit
(1 row)
```

Check what postgres versions you have installed `pg_lsclusters`  

```bash
Ver Cluster       Port Status Owner    Data directory                       Log file
12  main          5432 online postgres /var/lib/postgresql/12/main          /var/log/postgresql/postgresql-12-main.log
14  main          5434 online postgres /var/lib/postgresql/14/main          /var/log/postgresql/postgresql-14-main.log
```

Please be aware that the installation of postgresql-14 will automatically create a default cluster 14/main. If you want to upgrade the 12/main cluster, you need to remove the already existing 14 cluster:

`sudo pg_dropcluster --stop 14 main`

Use `dpkg -l | grep postgresql` to check which postgres packages are installed:

```
ii  postgresql                            14+238                                  all          object-relational SQL database (supported version)
ii  postgresql-12                         12.12-0ubuntu0.20.04.1                  amd64        object-relational SQL database, version 12 server
ii  postgresql-14                         14.6-0ubuntu0.22.04.1                   amd64        The World's Most Advanced Open Source Relational Database
ii  postgresql-client-12                  12.12-0ubuntu0.20.04.1                  amd64        front-end programs for PostgreSQL 12
ii  postgresql-client-14                  14.6-0ubuntu0.22.04.1                   amd64        front-end programs for PostgreSQL 14
ii  postgresql-client-common              238                                     all          manager for multiple PostgreSQL client versions
ii  postgresql-common                     238                                     all          PostgreSQL database-cluster manager
ii  postgresql-contrib                    14+238                                  all          additional facilities for PostgreSQL (supported version)
ii  timescaledb-loader-postgresql-12      1.7.5~ubuntu20.04                       amd64        The loader for TimescaleDB to load individual versions.
ii  timescaledb-postgresql-12             1.7.5~ubuntu20.04                       amd64        An open-source time-series database based on PostgreSQL, as an extension.
```

> Somehow my timescaledb was broken after upgrading to Ubuntu 22 so I had to reinstall it. In any case you have to make sure you have already the version according to postgres before migrating the data.  
`curl -s https://packagecloud.io/install/repositories/timescale/timescaledb/script.deb.sh | sudo bash`  
`sudo apt install timescaledb-2-postgresql-14`

Now start with the data migration

`sudo pg_upgradecluster 12 main`

After this process 12 is down and 14 is up. Now tune timescale:

```
sudo apt install timescaledb-tools
sudo timescaledb-tune
```

> When I upgraded to Ubuntu 22 I also had to reinstall pgadmin4 and rerun `sudo /usr/pgadmin4/bin/setup-web.sh` but normally that is not required

Now drop the old database `sudo pg_dropcluster 12 main` and purge old packages `sudo apt-get purge postgresql-12 postgresql-client-12`

## Remote connection

- Add a firewall rule `sudo ufw allow 5432 comment 'postgres'`and `sudo ufw reload`
- Listen connections in `/etc/postgresql/14/main/postgresql.conf`

```bash
listen_addresses = '*' 
```

- Accept connections on `/etc/postgresql/14/main/pg_hba.conf` from local network `192.168.1.0/24`

```
# IPv4 local connections:
host    all             all             127.0.0.1/32            scram-sha-256
host    all             all             192.168.1.0/24          scram-sha-256
```

- On remote (arch) install `postgresql-libs` package
- Test `psql -h 192.168.1.50 -U postgres`

## Common psql commands

- List databases `\l`
- List databases with size, tablespace and description `\l+`
- Connect to database `\c database`
- Display tables `\dt` and `\dt+`
- Display users `\du`

## Create a new role

```bash
pink@thebeachlab:~$ sudo -u postgres createuser --interactive
Enter name of role to add: iot
Shall the new role be a superuser? (y/n) y
```

## Create a new database

A postgres assumption is that a role will have a database with the same name which it can access. That means `iot` role will attempt to connect to `iot` database by default. So let's create `iot` database.

`sudo -u postgres createdb iot`

## Open a postgres prompt with `iot` role

Due to the ident based authentication, you need a Linux user with the same name as your postgres role and database.

`sudo adduser iot`

Now you can connect to the `iot` database with

`sudo -u iot psql`

Check your connection with `\connifo`

```bash
iot=# \conninfo
You are connected to database "iot" as user "iot" via socket in "/var/run/postgresql" at port "5432"
```

Exit with `\q`. A role can also connect to a different database

```bash
pink@thebeachlab:~$ sudo -u iot psql -d postgres
psql (12.4 (Ubuntu 12.4-0ubuntu0.20.04.1))
Type "help" for help.

postgres=# \conninfo
You are connected to database "postgres" as user "iot" via socket in "/var/run/postgresql" at port "5432".
```

## TimescaleDB

IoT stores huge time series data. Relational databases can be used to store the data but processing can be slow. TimescaleDB is an NoSQL database optimized to store time-series data. It is implemented as an extension of PostgreSQL combining the ease of use of relational databases and the speed of NoSQL databases.

Install

```bash
sudo add-apt-repository ppa:timescale/timescaledb-ppa
sudo apt update
sudo apt install timescaledb-postgresql-12
```

Configure and optimize

```bash
pink@thebeachlab:~$ sudo timescaledb-tune
Using postgresql.conf at this path:
/etc/postgresql/12/main/postgresql.conf

Is this correct? [(y)es/(n)o]: y
Writing backup to:
/tmp/timescaledb_tune.backup202010261003

shared_preload_libraries needs to be updated
Current:
#shared_preload_libraries = ''
Recommended:
shared_preload_libraries = 'timescaledb'
Is this okay? [(y)es/(n)o]: y
success: shared_preload_libraries will be updated

Tune memory/parallelism/WAL and other settings? [(y)es/(n)o]: y
Recommendations based on 7.74 GB of available memory and 4 CPUs for PostgreSQL 12

Memory settings recommendations
Current:
shared_buffers = 128MB
#effective_cache_size = 4GB
#maintenance_work_mem = 64MB
#work_mem = 4MB
Recommended:
shared_buffers = 1981MB
effective_cache_size = 5944MB
maintenance_work_mem = 1014453kB
work_mem = 5072kB
Is this okay? [(y)es/(s)kip/(q)uit]: y
success: memory settings will be updated

Parallelism settings recommendations
Current:
missing: timescaledb.max_background_workers
#max_worker_processes = 8
#max_parallel_workers_per_gather = 2
#max_parallel_workers = 8
Recommended:
timescaledb.max_background_workers = 8
max_worker_processes = 15
max_parallel_workers_per_gather = 2
max_parallel_workers = 4
Is this okay? [(y)es/(s)kip/(q)uit]: y
success: parallelism settings will be updated

WAL settings recommendations
Current:
#wal_buffers = -1
min_wal_size = 80MB
Recommended:
wal_buffers = 16MB
min_wal_size = 512MB
Is this okay? [(y)es/(s)kip/(q)uit]: y
success: WAL settings will be updated

Miscellaneous settings recommendations
Current:
#default_statistics_target = 100
#random_page_cost = 4.0
#checkpoint_completion_target = 0.5
#max_locks_per_transaction = 64
#autovacuum_max_workers = 3
#autovacuum_naptime = 1min
#effective_io_concurrency = 1
Recommended:
default_statistics_target = 500
random_page_cost = 1.1
checkpoint_completion_target = 0.9
max_locks_per_transaction = 64
autovacuum_max_workers = 10
autovacuum_naptime = 10
effective_io_concurrency = 200
Is this okay? [(y)es/(s)kip/(q)uit]: y
success: miscellaneous settings will be updated
Saving changes to: /etc/postgresql/12/main/postgresql.conf
```

If you are going to say yes to all you could also do `sudo timescaledb-tune --quiet --yes`. Now restart postpres

`sudo systemctl restart postgresql.service`

## Create a hypertable in `iot` database

First connect to `iot`

`sudo -u iot psql`

Enable the TimescaleDB extension

```bash
iot=# CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
WARNING:
WELCOME TO
 _____ _                               _     ____________
|_   _(_)                             | |    |  _  \ ___ \
  | |  _ _ __ ___   ___  ___  ___ __ _| | ___| | | | |_/ /
  | | | |  _ ` _ \ / _ \/ __|/ __/ _` | |/ _ \ | | | ___ \
  | | | | | | | | |  __/\__ \ (_| (_| | |  __/ |/ /| |_/ /
  |_| |_|_| |_| |_|\___||___/\___\__,_|_|\___|___/ \____/
               Running version 1.7.4
For more information on TimescaleDB, please visit the following links:

 1. Getting started: https://docs.timescale.com/getting-started
 2. API reference documentation: https://docs.timescale.com/api
 3. How TimescaleDB is designed: https://docs.timescale.com/introduction/architecture

Note: TimescaleDB collects anonymous reports to better understand and assist our users.
For more information and how to disable, please see our docs https://docs.timescaledb.com/using-timescaledb/telemetry.

CREATE EXTENSION
```

Disable telemetry (sending data to Timescale) and restart postgres

```bash
pink@thebeachlab:~$ sudo -u postgres psql
psql (12.4 (Ubuntu 12.4-0ubuntu0.20.04.1))
Type "help" for help.

postgres=# ALTER SYSTEM SET timescaledb.telemetry_level=off
postgres-# \q
pink@thebeachlab:~$ sudo systemctl restart postgresql.service
```

> To be continued...

## Managing PostgreSQL with pgAdmin

### Install pgadmin4

```bash
#
# Setup the repository
#

# Install the public key for the repository (if not done previously):
sudo curl https://www.pgadmin.org/static/packages_pgadmin_org.pub | sudo apt-key add

# Create the repository configuration file:
sudo sh -c 'echo "deb https://ftp.postgresql.org/pub/pgadmin/pgadmin4/apt/$(lsb_release -cs) pgadmin4 main" > /etc/apt/sources.list.d/pgadmin4.list && apt update'

#
# Install pgAdmin
#
# Install for web mode only:
sudo apt install pgadmin4-web
```

### Apache and nginx together

To avoid both web servers listening to the same port change the default listening port from 80 to 5050 and 443 to 8090 in `/etc/apache2/ports.conf`

```apache
Listen 5050

<IfModule ssl_module>
        Listen 8090
</IfModule>

<IfModule mod_gnutls.c>
        Listen 8090
</IfModule>
```

and `sudo nano /etc/apache2/sites-available/000-default.conf` and set

```apache
<VirtualHost *:5050>
```

Then reload the service `sudo systemctl restart apache2` and verify Apache is listening to 8080 `sudo netstat -tlpn`

Also create the ufw rules `sudo ufw allow 5050 comment 'apache pgadmin'` and `sudo ufw reload`

pgadmin will be located at `http://server-address:5050/pgadmin4`

### Creating a subdomain (optional)

I created and enabled `/etc/nginx/sites-available/postgres.beachlab.org` with this content

```nginx
server {
        listen 80;
        listen [::]:80;
        server_name postgres.beachlab.org;
        return 301 http://beachlab.org:5050/pgadmin4;
}
```

If you don't require https that's all.

### Securing pgadmin with https (optional)

NOT WORKING YET. Check modules /etc/apache2/ports.conf and files in /etc/apache2/sites-enabled then change redisect in /etc/nginx/sites-available/postgres.beachlab.org (and remove ufw apache full rules?)

`sudo certbot certonly --standalone -d postgres.beachlab.org` which creates certificates in `/etc/letsencrypt/live/postgres.beachlab.org/`. Certificates will renew automatically.

Set

```bash
ServerName beachlab.org
ServerAlias postgres.beachlab.org
```

in `/etc/apache2/sites-available/000-default.conf`. Check syntax `sudo apache2ctl configtest` and `sudo systemctl reload apache2`

Install certbot apache plugin `sudo apt install certbot python3-certbot-apache` and run `sudo certbot --apache` but not redirect`


### Configure pgadmin

Run `/usr/pgadmin4/bin/setup-web.sh`

### Running pgadmin

Go to `http://server-ip:5050/pgadmin4`

### Reset pgadmin password
if you don't remember the credentials `mv /var/lib/pgadmin/pgadmin4.db /var/lib/pgadmin/pgadmin4.db.backup` and run `/usr/pgadmin4/bin/setup-web.sh` again.

Add a server and enter the connection details. You might have to connect to `sudo -u postgres psql` and `ALTER USER postgres PASSWORD 'mynewpassword';` if you don't remember your credentials.

### unlock pgadmin account
After 3 unsuccessful login attempts your account will be locked. Install `sudo apt install sqlite3` and run as root `sqlite3 pgadmin4.db "UPDATE USER SET LOCKED = false, LOGIN_ATTEMPTS = 0 WHERE USERNAME = 'user@domain.com';" ".exit"`

### pgadmin storage
ERD and other files are stored in `/var/lib/pgadmin/storage/email_account.org/`

## SQL Tips and tricks

### Create a readonly user

```sql
CREATE USER readonly WITH PASSWORD 'your_password';
\c air
GRANT CONNECT ON DATABASE air TO readonly;
GRANT USAGE ON SCHEMA public TO readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;
```

### For every table

- create a column named `id` with `bigint` or `int` datatype and IDENTITY. This will be the primary key. Enroll tables, also known as join tables will have more records than other records.
- create a column named `created` of `timestamp with timezone` datatype and default value `now()`
- create a column named `modified` of `timestamp with timezone` datatype and default value `now()`

Probably best to set all these in a table template.

### Autoupdate the modified timestamp when a record is updated

Using pgadmin query tool create a function `update_timestamp_modified_column()`

```sql
CREATE OR REPLACE FUNCTION update_timestamp_modified_column()
RETURNS TRIGGER AS $$
BEGIN
  CASE WHEN OLD.* IS DISTINCT FROM NEW.* THEN
    NEW.modified = NOW();
    RETURN NEW;
  ELSE
    RETURN OLD;
  END CASE;
END;
$$ LANGUAGE 'plpgsql';
```

This function will appear under `trigger functions`. Now, for every table, we create a trigger for each table

```sql
CREATE TRIGGER update_modified
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE PROCEDURE update_timestamp_modified_column();
```

### New table from existing table

```sql
CREATE TABLE template (LIKE users INCLUDING ALL);
```

Does not copy triggers. You will have to do this manually

### Add new column to existing table

Here adding a foreign key

```sql
ALTER TABLE interests ADD COLUMN IF NOT EXISTS interest_group_id INTEGER NOT NULL;
```

### Add one to many

Altered table has the many, select the foreign key. The reference table and (id) has the one

```sql
ALTER TABLE public.interests
    ADD FOREIGN KEY (interest_group_id)
    REFERENCES public.interest_group (id)
    NOT VALID;
```

### Create a JSON from a table

```sql
SELECT json_agg(row_to_json(t))
FROM (
  SELECT *
  FROM your_table
) t
```

