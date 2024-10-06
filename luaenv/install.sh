#!/usr/bin/env bash
#
git clone https://github.com/cehoffman/luaenv.git ~/.luaenv
git clone https://github.com/xpol/luaenv-luarocks.git ~/.luaenv/plugins/luaenv-luarocks
git clone https://github.com/cehoffman/lua-build.git ~/.luaenv/plugins/lua-build

luaenv install 5.1.5
luaenv global 5.1.5

luaenv luarocks 2.4.3

luarocks --local --lua-version=5.1 install magick
