#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Compatibility entrypoint; all build guards and stages live in one place.
exec bash "$(dirname "${BASH_SOURCE[0]}")/server_build.sh" "$@"
