#!/bin/bash

_dir="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$_dir"

source .env
export DISCORD_TOKEN
uvicorn bot.server:app &
run-discord
