#!/usr/bin/env zsh

clp_content=$(lemonade paste --host=127.0.0.1)
# echo "clp=$clp_content"

case $clp_content in curl*)
  clp_content=${clp_content/'curl -v'/'curl'}
  hurl_converted=$(printf '%s' "$clp_content" | hurlfmt --in curl --out hurl)
  # echo "\n$hurl_converted"
  printf '%s' "$hurl_converted" | lemonade copy --host=127.0.0.1
  return 0
esac

# curl_converted=$(echo "$clp_content" | hurlfmt --in hurl --out json)
# echo "\n$curl_converted"
# echo "$curl_converted" | lemonade copy
# return 0
