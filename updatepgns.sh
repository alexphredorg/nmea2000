#!/bin/sh
mv pgns.json pgns-old.json
wget https://raw.githubusercontent.com/canboat/canboat/master/analyzer/pgns.json --output-document=pgns-full.json
./remccoms3.sed < pgns-full.json > pgns.json
