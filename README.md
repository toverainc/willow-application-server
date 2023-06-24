# Willow Application Server

## Get Started

### Installation
```
git clone https://github.com/toverainc/willow-application-server.git && cd willow-application-server

./utils.sh build
```

### Configure
Edit/create ```.env``` and populate the ```OTA_URL``` with the hostname/IP address of the WAS instance that is reachable from Willow devices:

```
cat .env 
OTA_URL="http://my_was_host:8502/static/ota.bin"
```

### Start
```./utils.sh run```

## Configure and update Willow devices
Visit ```http://my_was_host:8501``` in your browser.
