# Parallel Run With OpenFOAM and CalculiX #

This job runs only on two nodes, i.e.

```console
$ mpirun -np 2 python3 main.py &>info.log
```

In addition, it requires the parallel mapper that you can find [here](https://github.com/chiao45/parpydtk2) and the DTK2 that has *AWLS* extension, which you can find [here](https://github.com/unifem/DataTransferKit).

In addition, the [PBS](./seawulf.pbs.template) file is a template job file that works on seawulf cluster.
