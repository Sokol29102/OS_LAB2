#!/usr/bin/env bash
set -e
python3.10 license_replace.py \
  --dir ./src \
  --source-exemplar ./examples/gplv1_sample.c \
  --target-exemplar ./examples/gplv2_sample.c \
  --recursive \
  --threshold 0.4
