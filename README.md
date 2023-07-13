# Willow Application Server

## Get Started

We have tried to simplify the onboarding process as much as possible. It is no longer required to build Willow yourself.
All you have to do is run Willow Application Server and connect to it. From there, you will be guided to the Willow Web Flasher, which will download a Willow dist image from Github, inject your Wi-Fi credentials into the NVS partition, and flash it to your device.

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
