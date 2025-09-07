# Everything OpenStreetMaps

- [Install Postgis](#install-postgis)
- [Hosting openstreetmap in the postgres](#hosting-openstreetmap-in-the-postgres)
  - [Create osm user and a gis database in postgres](#create-osm-user-and-a-gis-database-in-postgres)
  - [Create osm system user and grant sister access to it](#create-osm-system-user-and-grant-sister-access-to-it)
  - [Get the planet into postgres (caution, not tested)](#get-the-planet-into-postgres-caution-not-tested)
  - [Optimize PostgreSQL Server Performance](#optimize-postgresql-server-performance)
  - [Import the Map Data to PostgreSQL](#import-the-map-data-to-postgresql)
- [Serving the maps](#serving-the-maps)
  - [Install Renderd and mod\_tile](#install-renderd-and-mod_tile)
  - [Generate Mapnik Stylesheet](#generate-mapnik-stylesheet)
  - [Recap](#recap)
- [Maplibre](#maplibre)
- [OSM Planet](#osm-planet)
  - [Cron job to download planet once a month](#cron-job-to-download-planet-once-a-month)
  - [Extract data fro OSM Planet to Database](#extract-data-fro-osm-planet-to-database)
  - [Get info from a PBF](#get-info-from-a-pbf)
  - [Create a database for all planet features (once)](#create-a-database-for-all-planet-features-once)
  - [Create a .pgpass file in your home folder (once)](#create-a-pgpass-file-in-your-home-folder-once)
  - [From Planet Extract all related to boundaries](#from-planet-extract-all-related-to-boundaries)
  - [Extract individual features from boundary\_administrative](#extract-individual-features-from-boundary_administrative)
  - [From Planet Extract all related to aeroway](#from-planet-extract-all-related-to-aeroway)
  - [Extract individual features from all\_aeroway](#extract-individual-features-from-all_aeroway)
  - [Convert to database](#convert-to-database)
  - [Create tables in postgres (once)](#create-tables-in-postgres-once)
  - [Delete all the rows](#delete-all-the-rows)
  - [Re insert into the database](#re-insert-into-the-database)
- [Natural Earth](#natural-earth)
  - [To find the srid of a shapefile](#to-find-the-srid-of-a-shapefile)
  - [First time creation of table from shapefile](#first-time-creation-of-table-from-shapefile)
  - [Update data into database](#update-data-into-database)
- [Timezones](#timezones)


## Install Postgis
```bash
sudo apt update; sudo apt upgrade -y
sudo apt install postgis postgresql-16-postgis-3
```

## Hosting openstreetmap in the postgres

### Create osm user and a gis database in postgres

```bash
sudo -u postgres -i
createuser osm
createdb -E UTF8 -O osm gis
psql -c "CREATE EXTENSION postgis;" -d gis
psql -c "CREATE EXTENSION hstore;" -d gis
psql -c "ALTER TABLE spatial_ref_sys OWNER TO osm;" -d gis
exit
```

### Create osm system user and grant sister access to it

```bash
sudo adduser --system --group osm
cd /home/osm/
sudo apt install acl
sudo setfacl -R -m u:pink:rwx /home/osm/
```

### Get the planet into postgres (caution, not tested)
```bash
git clone https://github.com/gravitystorm/openstreetmap-carto.git
wget -c http://download.geofabrik.de/europe/spain-latest.osm.pbf
```

Using download-osm:

```bash
sudo apt install docker.io
git clone https://github.com/openmaptiles/openmaptiles.git
sudo docker run --rm -it -v $PWD:/download openmaptiles/openmaptiles-tools \
  download-osm planet -- -d /download

osm2pgsql -c -d gis planet-230313.osm.pbf
```

### Optimize PostgreSQL Server Performance

`sudo nano /etc/postgresql/15/main/postgresql.conf`

Change `shared_buffers = 128MB` to 25% of RAM `shared_buffers = 2GB`

Also

```bash
work_mem = 1GB
maintenance_work_mem = 8GB (mine set to 2GB, check)
```

`sudo systemctl restart postgresql`

`sudo head -1 /var/lib/postgresql/15/main/postmaster.pid`

```bash
grep ^VmPeak /proc/7031/status
VmPeak:	 2173776 kB
```
```bash
cat /proc/meminfo | grep -i huge
AnonHugePages:         0 kB
ShmemHugePages:        0 kB
FileHugePages:         0 kB
HugePages_Total:       0
HugePages_Free:        0
HugePages_Rsvd:        0
HugePages_Surp:        0
Hugepagesize:       2048 kB
Hugetlb:               0 kB
```

We can calculate how many huge pages we need. Divide the VmPeak value by the size of huge page: 2173776 kB / 2048 kB = 1062. Then we need to edit the sysctl files to change Linux kernel parameters. Instead of editing the /etc/sysctl.conf file, we create a custom config file, so your custom configurations won’t be overwritten when upgrading software packages.

`sudo touch /etc/sysctl.d/60-custom.conf`

`echo "vm.nr_hugepages = 1062" | sudo tee -a /etc/sysctl.d/60-custom.conf`

`sudo sysctl -p /etc/sysctl.d/60-custom.conf`

Now 
```bash
cat /proc/meminfo | grep -i huge
AnonHugePages:         0 kB
ShmemHugePages:        0 kB
FileHugePages:         0 kB
HugePages_Total:    1062
HugePages_Free:     1062
HugePages_Rsvd:        0
HugePages_Surp:        0
Hugepagesize:       2048 kB
Hugetlb:         2174976 kB
```

`sudo systemctl restart postgresql`

###  Import the Map Data to PostgreSQL

sudo apt install osm2pgsql

sudo setfacl -R -m u:postgres:rwx /home/osm/

sudo -u postgres -i

osm2pgsql --slim -d gis --hstore --multi-geometry --keep-coastlines --number-processes 15 -O flex --tag-transform-script /home/osm/openstreetmap-carto/openstreetmap-carto.lua --style /home/osm/openstreetmap-carto/openstreetmap-carto.style -C 25000 /home/osm/europe-latest.osm.pbf


osm2pgsql --create   --style your_osm2pgsql_style_file your_osm_data_file.pbf


where

--slim: run in slim mode rather than normal mode. This option is needed if you want to update the map data using OSM change files (OSC) in the future.
-d gis: select database.
--hstore: add tags without column to an additional hstore (key/value) column to PostgreSQL tables
--multi-geometry: generate multi-geometry features in postgresql tables.
--style: specify the location of style file
--number-processes: number of CPU cores on your server. I have 2.
-C flag specifies the cache size in MegaBytes. It should be around 70% of the free RAM on your machine. Bigger cache size results in faster import speed. For example, my server has 8GB free RAM, so I can specify -C 5600. Be aware that PostgreSQL will need RAM for shared_buffers. Use this formula to calculate how big the cache size should be: (Total RAM - PostgreSQL shared_buffers) * 70%
Finally, you need to specify the location of map data file.

Once the import is complete, grant all privileges of the gis database to the osm user.

psql -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO osm;" -d gis

exit

## Serving the maps

### Install Renderd and mod_tile

sudo apt install software-properties-common

sudo add-apt-repository ppa:osmadmins/ppa

sudo apt install apache2 libapache2-mod-tile renderd


Enable tile mode  
sudo a2enmod tile

Next, create a virtual host for the tile server.  
`sudo nano /etc/apache2/sites-available/tileserver_site.conf`

Add the following lines in this file. Replace tile.your-domain.com with your real domain name and the post you will use. Don’t forget to DNS A  or CNAME record and add a UFW rule.

<VirtualHost *:80>
    ServerName tile.your-domain.com
    LogLevel info
    Include /etc/apache2/conf-available/renderd.conf
</VirtualHost>

sudo a2ensite tileserver_site.conf

sudo systemctl reload apache2

systemctl status renderd

### Generate Mapnik Stylesheet

sudo apt install -y curl unzip gdal-bin mapnik-utils libmapnik-dev python3-pip

sudo apt-get install -y nodejs




### Recap

Maputnnik - Editor estilos

Maptiler y Mapbox serve tiles



https://www.linuxbabe.com/linux-server/osm-openstreetmap-tile-server-ubuntu-22-04

## Maplibre

https://maplibre.org



Generate and serve mbtiles

https://github.com/onthegomap/planetiler/blob/main/PLANET.md

Generate contours, hillshade, Terrain RGB, and slope angle shading map tiles from Digital Elevation Models (DEMs).

https://github.com/nst-guide/terrain

https://github.com/syncpoint/terrain-rgb



Seabed data

https://www.gebco.net


Terrain data AWS https://registry.opendata.aws/terrain-tiles/


Convert to terrain-RGB
Install docker



aws s3 cp s3://raster/AW3D30/ --recursive --endpoint-url https://opentopography.s3.sdsc.edu --no-sign-request


natural earth data https://www.naturalearthdata.com

aws s3 cp --no-sign-request --recursive s3://elevation-tiles-prod-eu/geotiff geotiff


## OSM Planet
The planet is stored in `/home/osm/planet`

```bash
mv /home/osm/planet/planet-latest.osm.pbf planet-latest.osm.pbf.old
wget https://ftp5.gwdg.de/pub/misc/openstreetmap/planet.openstreetmap.org/pbf/planet-latest.osm.pbf
rm planet-latest.osm.pbf.old
```
Son 75GB approx. Unos 22 minutos, una vez al mes dia 15 a las 5am

### Cron job to download planet once a month 
```bash
0 5 15 * * mv /home/osm/planet/planet-latest.osm.pbf /home/osm/planet/planet-latest.osm.pbf.old && wget -O /home/osm/planet/planet-latest.osm.pbf https://ftp5.gwdg.de/pub/misc/openstreetmap/planet.openstreetmap.org/pbf/planet-latest.osm.pbf && rm /home/osm/planet/planet-latest.osm.pbf.old
```

### Extract data fro OSM Planet to Database
`sudo apt install osmium-tool`

1 aeroway windsock

2 aeroway aerodrome
  amenity fuel
  emergency fire_extinguisher
  emergency fire_hose
  amenity vending_machine
  amenity toilets
  amenity shower

aeroway hangar
aeroway helipad
aeroway heliport
aeroway navigationaid
aeroway runway
aeroway taxiway
emergency landing_site

Inside aeroway aerodrome polygon
amenity bar
amenity restaurant
amenity bicycle_parking
amenity motorcycle_parking
amenity parking
amenity drinking_water
building
building hangar

Near aerodrome
amenity car_rental
amenity car_sharing
amenity taxi
amenity atm


### Get info from a PBF
`osmium fileinfo -e planet-latest.osm.pbf `


### Create a database for all planet features (once)
create database planet;
CREATE EXTENSION postgis;

### Create a .pgpass file in your home folder (once)
```bash
cd
nano .pgpass
localhost:6432:planet:postgres:your_password
localhost:6432:air:postgres:your_password2
chmod 600 ~/.pgpass
```

### From Planet Extract all related to boundaries
`osmium tags-filter -v planet-latest.osm.pbf boundary=administrative -o features/boundary_administrative.pbf --overwrite`
??? minutes
1 Gb

### Extract individual features from boundary_administrative
```bash
osmium tags-filter -v /home/osm/planet/features/boundary_administrative.pbf nwr/admin_level=2 -o /home/osm/planet/features/admin2.pbf --overwrite
osmium export -v --add-unique-id=type_id -f pg /home/osm/planet/features/admin2.pbf -o /home/osm/planet/features/admin2.pg --overwrite
```
admin2.pbf 379M
admin2.pg 6G


CREATE TABLE countries (
  id            TEXT PRIMARY KEY,
  geom          GEOMETRY, -- or GEOGRAPHY
  tags          JSONB -- or JSON, or TEXT
);

psql -h localhost -p 6432 -U postgres -d planet -c "DELETE FROM countries;"

psql -h localhost -p 6432 -U postgres -d planet -c "\copy countries (id, geom, tags) FROM '/home/osm/planet/features/admin2.pg'"
Time:


### From Planet Extract all related to aeroway
`osmium tags-filter -v planet-latest.osm.pbf aeroway -o features/all_aeroway.pbf --overwrite`
9 minutes
56 Mb



### Extract individual features from all_aeroway
```bash
osmium tags-filter -v /home/osm/planet/features/all_aeroway.pbf nwr/aeroway=aerodrome -o /home/osm/planet/features/aerodrome.pbf --overwrite
osmium tags-filter -v /home/osm/planet/features/all_aeroway.pbf nwr/aeroway=windsock -o /home/osm/planet/features/windsocks.pbf --overwrite
osmium tags-filter -v /home/osm/planet/features/all_aeroway.pbf nwr/aeroway=navigationaid -o /home/osm/planet/features/navaid.pbf --overwrite
osmium tags-filter -v /home/osm/planet/features/all_aeroway.pbf nwr/aeroway=runway -o /home/osm/planet/features/runways.pbf --overwrite
osmium tags-filter -v /home/osm/planet/features/all_aeroway.pbf nwr/aeroway=taxiway -o /home/osm/planet/features/taxiways.pbf --overwrite
osmium tags-filter -v /home/osm/planet/features/all_aeroway.pbf nwr/aeroway=hangar -o /home/osm/planet/features/hangar.pbf --overwrite
osmium tags-filter -v /home/osm/planet/features/all_aeroway.pbf nwr/aeroway=helipad -o /home/osm/planet/features/helipad.pbf --overwrite
osmium tags-filter -v /home/osm/planet/features/all_aeroway.pbf nwr/aeroway=heliport -o /home/osm/planet/features/heliport.pbf --overwrite
osmium tags-filter -v /home/osm/planet/features/all_aeroway.pbf nwr/aeroway=terminal -o /home/osm/planet/features/terminal.pbf --overwrite
osmium tags-filter -v /home/osm/planet/features/all_aeroway.pbf nwr/aeroway=spaceport -o /home/osm/planet/features/spaceport.pbf --overwrite
```

### Convert to database
```bash
osmium export -v --add-unique-id=type_id -f pg /home/osm/planet/features/aerodrome.pbf -o /home/osm/planet/features/aerodrome.pg --overwrite
osmium export -v --add-unique-id=type_id -f pg /home/osm/planet/features/windsocks.pbf -o /home/osm/planet/features/windsocks.pg --overwrite
osmium export -v --add-unique-id=type_id -f pg /home/osm/planet/features/navaid.pbf -o /home/osm/planet/features/navaid.pg --overwrite
osmium export -v --add-unique-id=type_id -f pg /home/osm/planet/features/runways.pbf -o /home/osm/planet/features/runways.pg --overwrite
osmium export -v --add-unique-id=type_id -f pg /home/osm/planet/features/taxiways.pbf -o /home/osm/planet/features/taxiways.pg --overwrite
osmium export -v --add-unique-id=type_id -f pg /home/osm/planet/features/hangar.pbf -o /home/osm/planet/features/hangar.pg --overwrite
osmium export -v --add-unique-id=type_id -f pg /home/osm/planet/features/helipad.pbf -o /home/osm/planet/features/helipad.pg --overwrite
osmium export -v --add-unique-id=type_id -f pg /home/osm/planet/features/heliport.pbf -o /home/osm/planet/features/heliport.pg --overwrite
osmium export -v --add-unique-id=type_id -f pg /home/osm/planet/features/terminal.pbf -o /home/osm/planet/features/terminal.pg --overwrite
osmium export -v --add-unique-id=type_id -f pg /home/osm/planet/features/spaceport.pbf -o /home/osm/planet/features/spaceport.pg --overwrite
```


### Create tables in postgres (once)
```sql
CREATE TABLE aerodrome (
id        TEXT PRIMARY KEY,
geom      GEOMETRY, -- or GEOGRAPHY
tags      JSONB, -- or JSON, or TEXT
country_code VARCHAR(10)
);
CREATE TABLE windsocks (
  id            TEXT PRIMARY KEY,
  geom          GEOMETRY, -- or GEOGRAPHY
  tags          JSONB, -- or JSON, or TEXT
  country_code  VARCHAR(10)
);

CREATE TABLE navaid (
  id            TEXT PRIMARY KEY,
  geom          GEOMETRY, -- or GEOGRAPHY
  tags          JSONB, -- or JSON, or TEXT
  country_code  VARCHAR(10)
);

CREATE TABLE runways (
  id            TEXT PRIMARY KEY,
  geom          GEOMETRY, -- or GEOGRAPHY
  tags          JSONB, -- or JSON, or TEXT
  country_code  VARCHAR(10)
);

CREATE TABLE taxiways (
  id            TEXT PRIMARY KEY,
  geom          GEOMETRY, -- or GEOGRAPHY
  tags          JSONB, -- or JSON, or TEXT
  country_code  VARCHAR(10)
);

CREATE TABLE hangar (
  id            TEXT PRIMARY KEY,
  geom          GEOMETRY, -- or GEOGRAPHY
  tags          JSONB, -- or JSON, or TEXT
  country_code  VARCHAR(10)
);

CREATE TABLE helipad (
  id            TEXT PRIMARY KEY,
  geom          GEOMETRY, -- or GEOGRAPHY
  tags          JSONB, -- or JSON, or TEXT
  country_code  VARCHAR(10)
);

CREATE TABLE heliport (
  id            TEXT PRIMARY KEY,
  geom          GEOMETRY, -- or GEOGRAPHY
  tags          JSONB, -- or JSON, or TEXT
  country_code  VARCHAR(10)
);

CREATE TABLE terminal (
  id            TEXT PRIMARY KEY,
  geom          GEOMETRY, -- or GEOGRAPHY
  tags          JSONB, -- or JSON, or TEXT
  country_code  VARCHAR(10)
);

CREATE TABLE spaceport (
  id            TEXT PRIMARY KEY,
  geom          GEOMETRY, -- or GEOGRAPHY
  tags          JSONB, -- or JSON, or TEXT
  country_code  VARCHAR(10)
);
```
### Delete all the rows
```sql
DELETE FROM aerodrome;
DELETE FROM windsocks;
DELETE FROM navaid;
DELETE FROM runways;
DELETE FROM taxiways;
DELETE FROM hangar;
DELETE FROM helipad;
DELETE FROM heliport;
DELETE FROM terminal;
DELETE FROM spaceport;
```

In psql

```bash
psql -h localhost -p 6432 -U postgres -d planet -c "DELETE FROM aerodrome;"
psql -h localhost -p 6432 -U postgres -d planet -c "DELETE FROM windsocks;"
psql -h localhost -p 6432 -U postgres -d planet -c "DELETE FROM navaid;"
psql -h localhost -p 6432 -U postgres -d planet -c "DELETE FROM runways;"
psql -h localhost -p 6432 -U postgres -d planet -c "DELETE FROM taxiways;"
psql -h localhost -p 6432 -U postgres -d planet -c "DELETE FROM hangar;"
psql -h localhost -p 6432 -U postgres -d planet -c "DELETE FROM helipad;"
psql -h localhost -p 6432 -U postgres -d planet -c "DELETE FROM heliport;"
psql -h localhost -p 6432 -U postgres -d planet -c "DELETE FROM terminal;"
psql -h localhost -p 6432 -U postgres -d planet -c "DELETE FROM spaceport;"
```

### Re insert into the database

```bash
psql -h localhost -p 6432 -U postgres -d planet -c "\copy aerodrome (id, geom, tags) FROM '/home/osm/planet/features/aerodrome.pg'"
psql -h localhost -p 6432 -U postgres -d planet -c "\copy windsocks (id, geom, tags) FROM '/home/osm/planet/features/windsocks.pg'"
psql -h localhost -p 6432 -U postgres -d planet -c "\copy navaid (id, geom, tags) FROM '/home/osm/planet/features/navaid.pg'"
psql -h localhost -p 6432 -U postgres -d planet -c "\copy runways (id, geom, tags) FROM '/home/osm/planet/features/runways.pg'"
psql -h localhost -p 6432 -U postgres -d planet -c "\copy taxiways (id, geom, tags) FROM '/home/osm/planet/features/taxiways.pg'"
psql -h localhost -p 6432 -U postgres -d planet -c "\copy hangar (id, geom, tags) FROM '/home/osm/planet/features/hangar.pg'"
psql -h localhost -p 6432 -U postgres -d planet -c "\copy helipad (id, geom, tags) FROM '/home/osm/planet/features/helipad.pg'"
psql -h localhost -p 6432 -U postgres -d planet -c "\copy heliport (id, geom, tags) FROM '/home/osm/planet/features/heliport.pg'"
psql -h localhost -p 6432 -U postgres -d planet -c "\copy terminal (id, geom, tags) FROM '/home/osm/planet/features/terminal.pg'"
psql -h localhost -p 6432 -U postgres -d planet -c "\copy spaceport (id, geom, tags) FROM '/home/osm/planet/features/spaceport.pg'"
```

psql -h localhost -p 6432 -U postgres -d planet -c "\copy admin_0 (id, geom, tags) FROM '/home/osm/planet/features/admin_level_0.pg'"





{"ifr": "yes", "iata": "WKF", "icao": "FAWK", "name": "Air Force Base Waterkloof", "aeroway": "aerodrome", "landuse": "military", "alt_name": "Waterkloof Air Force Base", "military": "airfield", "wikidata": "Q10860394", "wikipedia": "en:Air Force Base Waterkloof", "short_name": "AFB Waterkloof", "licensed:sacaa": "no"}

## Natural Earth

> Warning: I wanted to use these to determine if a feature was inside a country but in the end the resolution is just a dratf approximation. Not really usable.


```sql
create database earth;
CREATE EXTENSION postgis;
```

adjust the .pgpass

`mkdir /home/osm/earth`

Get and unzip
```bash
wget -N https://www.naturalearthdata.com/http//www.naturalearthdata.com/download/10m/cultural/10m_cultural.zip -P /home/osm/earth/
unzip -o /home/osm/earth/10m_cultural.zip
```
De facto control country lines

```bash
/home/osm/earth/10m_cultural/ne_10m_admin_0_countries.shp
/home/osm/earth/10m_cultural/ne_10m_time_zones.shp
```

Some info about how to import countries and regions:

https://blog.devgenius.io/3-easy-ways-to-import-a-shapefile-into-a-postgresql-database-c1a4c78104af

### To find the srid of a shapefile
```bash
ogrinfo -al -so <shapefile>
ogrinfo -al -so /home/osm/earth/10m_cultural/ne_10m_admin_0_countries.shp | grep "EPSG"
ogrinfo -al -so /home/osm/earth/10m_cultural/ne_10m_time_zones.shp | grep "EPSG"
```

### First time creation of table from shapefile
```bash
shp2pgsql -I -s 4326 /home/osm/earth/10m_cultural/ne_10m_admin_0_countries.shp | psql -d earth -h localhost -U postgres -p 6432
shp2pgsql -I -s 4326 /home/osm/earth/10m_cultural/ne_10m_time_zones.shp | psql -d earth -h localhost -U postgres -p 6432
```
### Update data into database
```bash
psql -h localhost -p 6432 -U postgres -d earth -c "DELETE FROM ne_10m_admin_0_countries;"
shp2pgsql -a -s 4326 /home/osm/earth/10m_cultural/ne_10m_admin_0_countries.shp | psql -d earth -h localhost -U postgres -p 6432
psql -h localhost -p 6432 -U postgres -d earth -c "DELETE FROM ne_10m_time_zones;"
shp2pgsql -a -s 4326 /home/osm/earth/10m_cultural/ne_10m_time_zones.shp | psql -d earth -h localhost -U postgres -p 6432
```

## Timezones

Updates every 6 months approx.

wget -N https://github.com/evansiroky/timezone-boundary-builder/releases/download/2023b/timezones-with-oceans.shapefile.zip -P /home/osm/planet/timezones
unzip -o /home/osm/planet/timezones/timezones-with-oceans.shapefile.zip -d /home/osm/planet/timezones
ogrinfo -al -so /home/osm/planet/timezones/combined-shapefile-with-oceans.shp | grep "EPSG"
shp2pgsql -I -s 4326 /home/osm/planet/timezones/combined-shapefile-with-oceans.shp | psql -d planet -h localhost -U postgres -p 6432

Next time

psql -h localhost -p 6432 -U postgres -d planet -c "DELETE FROM \"combined-shapefile-with-oceans\";"
shp2pgsql -a -s 4326 /home/osm/planet/timezones/combined-shapefile-with-oceans.shp | psql -d planet -h localhost -U postgres -p 6432





wget -N https://github.com/evansiroky/timezone-boundary-builder/releases/download/2023b/timezones.shapefile.zip -P /home/osm/planet/timezones
unzip -o /home/osm/planet/timezones/timezones.shapefile.zip -d /home/osm/planet/timezones
ogrinfo -al -so /home/osm/planet/timezones/combined-shapefile.shp | grep "EPSG"
shp2pgsql -I -s 4326 /home/osm/planet/timezones/combined-shapefile.shp | psql -d planet -h localhost -U postgres -p 6432

Next time

psql -h localhost -p 6432 -U postgres -d planet -c "DELETE FROM \"combined-shapefile\";"
shp2pgsql -a -s 4326 /home/osm/planet/timezones/combined-shapefile.shp | psql -d planet -h localhost -U postgres -p 6432
