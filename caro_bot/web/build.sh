#!/bin/sh
# Reconstruit web/index.html à partir de la page de l'application (source : blackbox/app/source.html).
# Usage : sh caro_bot/web/build.sh   (depuis la racine du dépôt)
set -e
SRC=blackbox/app/source.html
OUT=caro_bot/web/index.html
{
  printf '<!doctype html>\n<html lang="fr-CA">\n<head>\n<meta charset="utf-8">\n'
  printf '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
  printf '<meta name="apple-mobile-web-app-capable" content="yes">\n<meta name="mobile-web-app-capable" content="yes">\n'
  printf '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">\n<meta name="apple-mobile-web-app-title" content="Black Box">\n'
  printf '<meta name="theme-color" content="#06080d">\n<link rel="manifest" href="/manifest.webmanifest">\n<link rel="apple-touch-icon" href="/icon-180.png">\n'
  printf '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}[hidden]{display:none!important}</style>\n'
  printf '</head>\n<body>\n'
  cat "$SRC"
  printf '\n</body>\n</html>\n'
} > "$OUT"
cp "$OUT" blackbox/app/index.html
echo "OK : $OUT"
