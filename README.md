# Willow Application Server

## Get Started

You will need to (one-time) configure, build, and flash Willow from the ```feature/was``` branch to onboard devices. Make sure to specify the WAS URL for your environment. With defaults it is ```ws://your_was_host:8502/ws```. You will need to also build and flash a dist image. From Willow:

```
./utils.sh config # Enter your WAS URL
./utils.sh build
./utils.sh dist
./utils.sh flash-dist
```

### Running WAS

```
docker run --detach --env=OTA_URL="http://my_was_host:8502/static/ota.bin" --name=willow-application-server --pull=always --network=host --restart=unless-stopped --volume=was-storage:/app/storage ghcr.io/toverainc/willow-application-server:main
```

### Building WAS
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

## OTA
For now you will need to copy ```willow.bin``` from ```build/willow.bin``` to the OTA_URL set above. We are working on manifest support.
