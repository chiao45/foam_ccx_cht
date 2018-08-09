#!/bin/bash

cd ${0%/*} || exit 1

echo ""
echo "This task runs on two cores..."
echo ""

mpiexec -np 2 python3 main.py > main.log 2>&1 &
PID=$!

span="/-\|"

printf "The job is still running..."

while [ -d /proc/$PID ]
do
    printf "\b${span:i++%${#span}:1}"
    sleep "0.7"
done

if [ $? -ne 0 ]; then
    echo ""
    echo "Simulation failed, check main.log file..."
    exit 1
else
    echo ""
    echo "Simulation has finished! The log information can be obtained in main.log."
    exit 0
fi


