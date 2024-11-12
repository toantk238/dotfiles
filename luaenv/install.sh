#!/usr/bin/env bash
#
git clone https://github.com/cehoffman/luaenv.git ~/.luaenv
# Allow to install luarocks 3.5.0
git clone -b patch-1  https://github.com/renatomaia/luaenv-luarocks.git ~/.luaenv/plugins/luaenv-luarocks
git clone https://github.com/cehoffman/lua-build.git ~/.luaenv/plugins/lua-build

luaenv install 5.1.5
luaenv global 5.1.5

luaenv luarocks 3.5.0

luarocks --local install magick
