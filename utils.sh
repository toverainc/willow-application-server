#!/usr/bin/env bash
set -e
WAS_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$WAS_DIR"

# Test for local environment file and use any overrides
if [ -r .env ]; then
    echo "Using configuration overrides from .env file"
    . .env
else
    echo "Using default configuration values"
    touch .env
fi

#Import source the .env file
set -a
source .env

# Which docker image to run
IMAGE=${IMAGE:-willow-application-server}

# UI Listen port
UI_LISTEN_PORT=${UI_LISTEN_PORT:-8501}

# API Listen Port
API_LISTEN_PORT=${API_LISTEN_PORT:-8502}

# Log level - acceptable values are debug, info, warning, error, critical. Suggest info or debug.
LOG_LEVEL=${LOG_LEVEL:-info}

# Listen IP
LISTEN_IP=${LISTEN_IP:-0.0.0.0}

TAG=${TAG:-latest}

# Torture delay
TORTURE_DELAY=${TORTURE_DELAY:-300}

# Web ui branch
WEB_UI_BRANCH="main"

# Local working directory for web ui
WEB_UI_DIR="willow-application-server-ui"

# Web ui URL
WEB_UI_URL="https://github.com/HeyWillow/willow-application-server-ui.git"

# Reachable WAS IP for the "default" interface
if command -v ip &> /dev/null; then
    # Linux 
    WAS_IP=$(ip route get 1.1.1.1 | grep -o 'src [0-9.]*' | cut -d' ' -f2)
else
    # macOS 
    WAS_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -n 1)
fi

# Get WAS version
export WAS_VERSION=$(git describe --always --dirty --tags)

set +a

if [ -z "$WAS_IP" ]; then
    echo "Could not determine WAS IP address - you will need to add it to .env"
    exit 1
else
    echo "WAS Web UI URL is http://$WAS_IP:$API_LISTEN_PORT"
fi

set +a

dep_check() {
    return
}

freeze_requirements() {
    if [ ! -f /.dockerenv ]; then
        echo "This script is meant to be run inside the container - exiting"
        exit 1
    fi

    # Freeze
    pip freeze > requirements.txt
}

build-docker() {
    docker build --build-arg "WAS_VERSION=$WAS_VERSION" -t "$IMAGE":"$TAG" .
}

build-web-ui() {
    mkdir -p "$WAS_DIR"/work
    cd "$WAS_DIR"/work
    if [ -d "$WEB_UI_DIR/node_modules" ]; then
        echo "Existing web ui working dir found, we need sudo to remove it because of docker"
        sudo rm -rf willow-application-server-ui
    fi
    git clone "$WEB_UI_URL"
    cd willow-application-server-ui
    git checkout "$WEB_UI_BRANCH"
    ./utils.sh build-docker
    ./utils.sh install
    # WAS_DIR is already set
    export WAS_DIR
    ./utils.sh build
}

shell() {
    docker run -it -v $WAS_DIR:/app -v $WAS_DIR/cache:/root/.cache -v willow-application-server_was-storage:/app/storage "$IMAGE":"$TAG" \
        /usr/bin/env bash
}

case $1 in

build-docker|build)
    build-docker
;;

build-web-ui)
    build-web-ui
;;

freeze-requirements)
    freeze_requirements
;;

start|run|up)
    dep_check
    shift
    docker compose up --remove-orphans "$@"
;;

stop|down)
    dep_check
    shift
    docker compose down "$@"
;;

shell|docker)
    shell
;;

test)
    dep_check
    docker run --rm -it --env PYTHONPATH=/app --volume="${WAS_DIR}:/app" "$IMAGE":"$TAG" pytest
;;

torture)
    echo "Starting WAS device torture test"
    docker compose down
    while true; do
        docker compose up -d
        echo "Sleeping for $TORTURE_DELAY"
        sleep $TORTURE_DELAY
        docker compose down
        "Sleeping for $TORTURE_DELAY"
        sleep $TORTURE_DELAY
    done
;;

*)
    dep_check
    echo "Passing unknown argument directly to docker compose"
    docker compose "$@"
;;

esac
