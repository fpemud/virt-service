#!/bin/bash

FILES="$(find ./src -name '*.py' | tr '\n' ' ')"

autopep8 -ia --ignore=E501 ${FILES}
