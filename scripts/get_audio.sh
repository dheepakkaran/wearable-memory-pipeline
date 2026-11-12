#!/usr/bin/env bash
# Download AMI Mix-Headset audio (CC BY 4.0) for the chosen meetings, in parallel.
cd "$(dirname "$0")/../data/raw"
for m in "$@"; do
  [ -f "$m.wav" ] && continue
  ( curl -sfL -o "$m.wav.part" "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/$m/audio/$m.Mix-Headset.wav" && mv "$m.wav.part" "$m.wav" ) &
done
wait
