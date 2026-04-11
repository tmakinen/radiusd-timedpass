#!/bin/sh

set -eu

curl \
    --fail --show-error --silent \
    -H "Accept: text/plain" \
    --unix-socket "${OTP_SOCKET:-/tmp/radiusd_otp.sock}" \
    http://localhost/otp
