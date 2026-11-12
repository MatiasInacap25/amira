#!/bin/sh
# Use an already-installed browser; never download one during this campaign.
exec "${AMIRA_BLACKBOX_CHROMIUM_EXECUTABLE:?Set the installed Chromium executable}" "$@" \
  --proxy-server=http://127.0.0.1:9 --proxy-bypass-list=127.0.0.1,localhost \
  --disable-background-networking --disable-quic
