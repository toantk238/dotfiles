#! /usr/bin/env zsh

clp_content=$(lemonade paste)
# echo "clp=$clp_content"

case $clp_content in curl*)
  clp_content=${clp_content/'curl -v'/'curl'}
  hurl_converted=$(echo $clp_content | hurlfmt --in curl --out hurl)
  echo "\n$hurl_converted"
  echo "$hurl_converted" | lemonade copy
  return 0
esac
