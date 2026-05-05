#!/usr/bin/env bash
set -euo pipefail

# verify submodules are cloned
git pull
git submodule sync --recursive && git submodule  update --init --recursive
git pull --recurse-submodules

# install qt 5.15.x if not already installed
if ! brew list qt@5 >/dev/null 2>&1; then
  echo "qt@5 not found. Installing ..."
  brew install qt@5
fi

# build for the first time
rm -rf ./build
mkdir ./build
cd ./build

qmake ../
make -j8

echo ""
echo ""
echo "QGC has built successfuly. Please open the build directory and start the application within. Once it starts, right click it on the task bar and hit keep in dock so you can use it without having to navigate here every time. QGC on the first run will take a bit to launch, be patient :)"
