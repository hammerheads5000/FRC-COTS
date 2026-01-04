#!/bin/bash

build_path="./build"
program_basename="FRC-COTS"
version=`gawk '/version/ {gsub(/\042|,/, ""); print $2 }' ./FRC-COTS.manifest`

echo "Extracted version is $version"

"C:/Program Files/7-Zip/7z.exe" d $build_path/$program_basename.zip *

"C:/Program Files/7-Zip/7z.exe" a $build_path/$program_basename.zip LICENSE \
    *.md *.png *.html *.py *.manifest -ir!lib/* -ir!commands/* -ir!resources/* \
    -ir!spacers/* -xr!__pycache__

echo
echo
echo "Moving $build_path/$program_basename.zip to $build_path/$program_basename-$version.zip"
mv $build_path/$program_basename.zip $build_path/$program_basename-$version.zip
# echo "Moving $build_path/$program_basename-win.exe to $build_path/$program_basename-win-$version.exe"
# mv $build_path/$program_basename-win.exe $build_path/$program_basename-win-$version.exe

echo
echo "Done."