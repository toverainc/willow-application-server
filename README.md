# Willow Application Server

## Get Started

We have tried to simplify the onboarding process as much as possible. It is no longer required to build Willow yourself.
All you have to do is run Willow Application Server and connect to it. From there, you will be guided to the Willow Web Flasher, which will download a Willow dist image from Github, inject your Wi-Fi credentials into the NVS partition, and flash it to your device.

### Running WAS

```
docker run --detach --name=willow-application-server --pull=always --network=host --restart=unless-stopped --volume=was-storage:/app/storage ghcr.io/toverainc/willow-application-server:main
```

### Building WAS
```
git clone https://github.com/toverainc/willow-application-server.git && cd willow-application-server

./utils.sh build
```

### Start
```./utils.sh run```

## Configure and update Willow devices
Visit ```http://my_was_host:8501``` in your browser.

## OTA
We list releases with OTA assets. Select the wanted release and click the OTA button. If the release is not already cached in WAS, WAS will download the binary from Github and cache it, then instruct Willow to start OTA with the URL of the cached asset. This makes it possible to run Willow in an isolated VLAN without Internet access.

To use a self-built binary for OTA, place it in the the ota/local directory of the was-storage volume using the following filenames:
* willow-ota-ESP32_S3_BOX.bin
* willow-ota-ESP32_S3_BOX_3.bin
* willow-ota-ESP32_S3_BOX_LITE.bin

To copy the file to the running container:
```
podman cp build/willow.bin willow-application-server:/app/storage/ota/local/willow-ota-ESP32_S3_BOX.bin
```
