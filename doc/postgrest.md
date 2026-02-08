# PostgREST

- [PostgREST](#postgrest)
  - [Prepare firewall](#prepare-firewall)
  - [Install](#install)
  - [Create roles](#create-roles)
  - [Check permissions of readonly](#check-permissions-of-readonly)
  - [JWT (TODO)](#jwt-todo)
  - [Configure](#configure)
  - [Create service](#create-service)
  - [Make calls](#make-calls)
  - [Create web proxy](#create-web-proxy)


## Prepare firewall
```bash
sudo ufw allow 3000 comment 'PostgREST API'
sudo ufw reload
sudo ufw status
```
Do the same for other ports.

## Install

```bash
sudo apt update && sudo apt upgrade -y
curl -L -o postgrest.tar.xz https://github.com/PostgREST/postgrest/releases/download/v13.0.7/postgrest-v13.0.7-linux-static-x86-64.tar.xz
 tar -xf postgrest.tar.xz
sudo mv postgrest /usr/local/bin/
sudo chmod +x /usr/local/bin/postgrest
postgrest --version
```

## Create roles

You’ll run these as a superuser (e.g. postgres)

Create a group role `web_anon` for the server
```sql
-- Create the anonymous group role (no login)
CREATE ROLE web_anon NOLOGIN;

-- Create a login role for PostgREST to connect with
-- (choose your own password)
CREATE ROLE readonly LOGIN PASSWORD 'change_me' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

-- Make readonly a member of web_anon (so PostgREST can SET ROLE web_anon)
GRANT web_anon TO readonly;
```
Grant permissions

```sql
GRANT USAGE ON SCHEMA public TO web_anon;

-- Existing tables (read-only)
GRANT SELECT ON TABLE public.my_table1, public.my_table2 TO web_anon;

-- Or if you want read on ALL existing tables in public:
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO web_anon;

-- Grant for specific sequences if those tables use them:
-- GRANT USAGE, SELECT ON SEQUENCE public.my_table1_id_seq, public.my_table2_id_seq TO web_anon;

-- Or blanket for all existing sequences in public:
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO web_anon;

-- For future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO web_anon;

-- For future sequences
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT USAGE, SELECT ON SEQUENCES TO web_anon;

-- (Optional but smart) Tighten public schema permissions
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
-- (Keep USAGE granted to web_anon as above)

```

## Check permissions of readonly

```sql
-- Who can do what (roles + membership)
\du+ readonly
\du+ web_anon

-- Table privileges (look for SELECT for web_anon; readonly inherits membership)
\dp public.my_table1
\dp public.my_table2

-- Schema permissions
\dn+ public
```

Try to SELECT (should work) and INSERT (should fail) as readonly.

```sql
# change connection details as needed
psql "postgres://readonly:change_me@localhost:5432/postgres" -c "SELECT * FROM public.my_table1 LIMIT 1;"

# This should fail with permission denied
psql "postgres://readonly:change_me@localhost:5432/postgres" -c "INSERT INTO public.my_table1 DEFAULT VALUES;"
```

## JWT (TODO)

## Configure
Create a conf file for each database `nano postgrest_db1.conf`

```bash
db-uri = "postgres://readonly:uri_encoded_password@localhost:5432/your_database_db1"
db-schemas = "public"
db-anon-role = "web_anon"
server-port = 3000
```

## Create service
Create a script postgrest_script.sh. This script uses the trap command to set up a cleanup function that will be executed when the script exits. The cleanup function sends termination signals to the PostgREST instances using pkill. The EXIT signal ensures that the cleanup function is called on script exit.

```bash
#!/bin/bash

# Function to clean up on script exit
cleanup() {
    echo "Script interrupted. Cleaning up..."
    
    # Terminate both PostgREST instances
    pkill -f "/home/sister/postgrest /home/sister/postgrest_db1.conf"
    pkill -f "/home/sister/postgrest /home/sister/postgrest_db2.conf"
    
    exit
}

# Trap the exit signal and call the cleanup function
trap cleanup EXIT

# Start PostgREST instances in the background
/home/sister/postgrest /home/sister/postgrest_db1.conf &
/home/sister/postgrest /home/sister/postgrest_db2.conf &

# Wait for both background processes to finish
wait
```

Make it executable `chmod +x postgrest_script.sh`.

Create a file named `postgrest.service` in the /`etc/systemd/system/` directory:

```bash
[Unit]
Description=PostgREST Service
After=network.target

[Service]
User=sister
ExecStart=/home/sister/postgrest_script.sh
Restart=always

[Install]
WantedBy=default.target
```

Activate the service
```bash
sudo systemctl daemon-reload
sudo systemctl start postgrest
sudo systemctl enable postgrest
```
## Make calls

All rows  
http://192.168.1.51:3000/ccaa

Rows with certain value  
http://192.168.1.51:3000/ccaa?ccaa_code=gte.10

| Abbreviation | PostgreSQL Equivalent | Meaning |
|---|---|---|
| eq | = | equals |
| gt | > | greater than |
| gte | >= | greater than or equal |
| lt | < | less than |
| lte | <= | less than or equal |
| neq | <> or != | not equal |
| like | LIKE | LIKE operator (to avoid URL encoding you can use * as an alias of the percent sign % for the pattern) |
| ilike | ILIKE | ILIKE operator (to avoid URL encoding you can use * as an alias of the percent sign % for the pattern) |
| match | ~ | ~ operator, see Pattern Matching |
| imatch | ~* | ~* operator, see Pattern Matching |
| in | IN | one of a list of values, e.g. `?a=in.(1,2,3)` – also supports commas in quoted strings like `?a=in.("hi,there","yes,you")` |
| is | IS | checking for exact equality (null, true, false, unknown) |
| isdistinct | IS DISTINCT FROM | not equal, treating NULL as a comparable value |
| fts | @@ | Full-Text Search using to_tsquery |
| plfts | @@ | Full-Text Search using plainto_tsquery |
| phfts | @@ | Full-Text Search using phraseto_tsquery |
| wfts | @@ | Full-Text Search using websearch_to_tsquery |
| cs | @> | contains e.g. `?tags=cs.{example, new}` |
| cd | <@ | contained in e.g. `?values=cd.{1,2,3}` |
| ov | && | overlap (have points in common), e.g. `?period=ov.[2017-01-01,2017-06-30]` – also supports array types, use curly braces instead of square brackets e.g. `code: ?arr=ov.{1,3}` |
| sl | << | strictly left of, e.g. `?range=sl.(1,10)` |
| sr | >> | strictly right of |
| nxr | &< | does not extend to the right of, e.g. `?range=nxr.(1,10)` |
| nxl | &> | does not extend to the left of |
| adj | |-| | is adjacent to, e.g. `?range=adj.(1,10)` |
| not | NOT | negates another operator, see Logical operators |
| or | OR | logical OR, see Logical operators |
| and | AND | logical AND, see Logical operators |
| all | ALL | comparison matches all the values in the list, see Logical operators |
| any | ANY | comparison matches any value in the list, see Logical operators |

Ranges  
http://192.168.1.51:3000/ccaa?or=(ccaa_code.gte.18,ccaa_code.lt.4)

Some columns only  
http://192.168.1.51:3000/ccaa?select=ccaa_code,ccaa_es

Rename columns  
http://192.168.1.51:3000/ccaa?select=ccaaCode:ccaa_code,nameES:ccaa_es

Cast columns  
http://192.168.1.51:3000/ccaa?select=ccaa_code::text

Order. If you care where nulls are sorted, add `.nullsfirst` or `.nullslast`  
http://192.168.1.51:3000/ccaa?select=ccaa_code,ccaa_es&order=ccaa_es.desc

Limits and offsets  
http://192.168.1.51:3000/ccaa?select=ccaa_code,ccaa_es&limit=5&offset=2

## Create web proxy

Create CNAME api pointing to beachlab.org, update `/etc/hosts`

Create `/etc/nginx/sites-available/api.beachlab.org` with

```nginx
server {
    listen 80;
    server_name api.beachlab.org;
    default_type text/plain;  # Set the default content type

    location /location1/ {
        proxy_pass http://192.168.1.51:3000/;  # Replace with the actual IP or domain
        proxy_redirect off;
    }

    # Add more locations only when upstream services actually exist.

    # Reject all other requests with a 403 Forbidden status
    location / {
        return 403;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/api.beachlab.org /etc/nginx/sites-enabled/
nginx -t
sudo systemctl restart nginx
```
