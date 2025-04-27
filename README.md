# Willow Application Server

## Get Started

We have tried to simplify the onboarding process as much as possible. It is no longer required to build Willow yourself.
All you have to do is run Willow Application Server and connect to it. From there, you will be guided to the Willow Web Flasher, which will download a Willow release image from Github, inject your Wi-Fi credentials and WAS URL into the NVS partition, and flash it to your device.

### Running WAS

```
docker run --detach --name=willow-application-server --pull=always --network=host --restart=unless-stopped --volume=was-storage:/app/storage ghcr.io/HeyWillow/willow-application-server
```

### Building WAS
```
git clone https://github.com/HeyWillow/willow-application-server.git && cd willow-application-server

./utils.sh build
```

### Start
```./utils.sh run```

## Configure and Upgrade Willow Devices
Visit ```http://my_was_host:8502``` in your browser.

## Upgrading "Over the Air" (OTA)

OTA upgrades allow you to update Willow devices without having to re-connect them to your computer to flash. It's a very safe process with a great deal of verification, automatic rollbacks on upgrade failure, etc.

We list published releases with OTA assets. Select the desired release and click the "Upgrade" button. If the release is not already cached in WAS, WAS will download the binary from Github and cache it, then instruct the target Willow device to start the upgrade from your running WAS instance. Alternatively, you can just upgrade the device from the clients page and WAS will cache it automatically on first request. This makes it possible to run Willow in an isolated VLAN without Internet access.

### Upgrade with your own Willow builds

After building with Willow you can provide your build to WAS to upgrade your local devices using OTA.

Make sure you select the appropriate target hardware from the "Audio HAL" section during build. Then run `./utils.sh build` as you normally would.

To use your custom binary for OTA place `build/willow.bin` from your Willow build directory in the `ota/local` directory of the was-storage volume using the following filenames:

* ESP32-S3-BOX-3.bin
* ESP32-S3-BOX.bin
* ESP32-S3-BOX-LITE.bin

To copy the file to your WAS instance:
```
docker cp build/willow.bin willow-application-server:/app/storage/ota/local/ESP32-S3-BOX-3.bin
```

Your provided build will now be available as the "local" release under the various upgrade options available in the Willow Web UI. You can copy new builds and upgrade however you see fit as you do development and create new Willow builds. If you run into a boot loop, bad flash, etc you can always recover your device from the Willow Web Flasher or Willow build system and try again.
