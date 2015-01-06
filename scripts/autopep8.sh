#!/bin/bash

FILES="./src/virt-service"
FILES="${FILES} $(find ./src -name '*.py' | tr '\n' ' ')"
FILES="${FILES} $(find ./integration-test -name '*.py' | tr '\n' ' ')"

autopep8 -ia --ignore=E501 ${FILES}
