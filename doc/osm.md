# Self hosting OpenStreetMaps

sudo apt update; sudo apt upgrade -y

sudo apt install postgis postgresql-15-postgis-3

sudo -u postgres -i

createuser osm

createdb -E UTF8 -O osm gis

psql -c "CREATE EXTENSION postgis;" -d gis
psql -c "CREATE EXTENSION hstore;" -d gis

psql -c "ALTER TABLE spatial_ref_sys OWNER TO osm;" -d gis

exit

sudo adduser --system --group osm

cd /home/osm/

sudo apt install acl
sudo setfacl -R -m u:pink:rwx /home/osm/

git clone https://github.com/gravitystorm/openstreetmap-carto.git

wget -c http://download.geofabrik.de/europe/spain-latest.osm.pbf

## Optimize PostgreSQL Server Performance

sudo nano /etc/postgresql/15/main/postgresql.conf

Change 

shared_buffers = 128MB

to 25% of RAM

shared_buffers = 2GB

Also

work_mem = 1GB
maintenance_work_mem = 8GB (mine set to 2GB, check)

sudo systemctl restart postgresql

sudo head -1 /var/lib/postgresql/15/main/postmaster.pid

grep ^VmPeak /proc/7031/status
VmPeak:	 2173776 kB

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

We can calculate how many huge pages we need. Divide the VmPeak value by the size of huge page: 2173776 kB / 2048 kB = 1062. Then we need to edit the sysctl files to change Linux kernel parameters. Instead of editing the /etc/sysctl.conf file, we create a custom config file, so your custom configurations won’t be overwritten when upgrading software packages.


sudo touch /etc/sysctl.d/60-custom.conf

echo "vm.nr_hugepages = 1062" | sudo tee -a /etc/sysctl.d/60-custom.conf

sudo sysctl -p /etc/sysctl.d/60-custom.conf

Now 
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

sudo systemctl restart postgresql

##  Import the Map Data to PostgreSQL

sudo apt install osm2pgsql

sudo setfacl -R -m u:postgres:rwx /home/osm/

sudo -u postgres -i

osm2pgsql --slim -d gis --hstore --multi-geometry --number-processes 2 --tag-transform-script /home/osm/openstreetmap-carto/openstreetmap-carto.lua --style /home/osm/openstreetmap-carto/openstreetmap-carto.style -C 5600 /home/osm/spain-latest.osm.pbf

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

## Install Renderd and mod_tile

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

## Generate Mapnik Stylesheet

sudo apt install -y curl unzip gdal-bin mapnik-utils libmapnik-dev python3-pip

sudo apt-get install -y nodejs




##

Maputnnik - Editor estilos

Maptiler y Mapbox serve tiles



https://www.linuxbabe.com/linux-server/osm-openstreetmap-tile-server-ubuntu-22-04