# Parallel Run With OpenFOAM and CalculiX through Socket #

This job runs only on two nodes, i.e.

## Run CCX as a subprocess of the master process in OpenFOAM ##

In this case, you need to run script [main.py](./main.py). You can simply do:

```console
$ mpiexec -np 2 python3 main.py &>info.log
```

## Run CCX and OpenFOAM independently on different groups of nodes ##

For this case, you need to `qsub` two jobs. Currently, the `driver` side must be invoked first so that a control file containing host/port will be generated. Then the `solver` side, i.e. CCX, can be submitted, and it can then read the control file and request connection to the `driver` server.

Login `seawulf`, modify the two template PBS files to load the correct environment variables. In most cases, if you have a proper configuration of login shell, you just need to source the `$HOME/.bashrc` file.

**Submit the `driver` (coupler with fluid (pyofm) portal)**:

```console
$ qsub coupler.pbs
```

**Monitor the job process**:

```console
$ qstat -u <user>
```

Once the job is running or you see the `couplingFDSN.ini` file is created, it's safe to submit the solid job, i.e. `solver` side:

```console
$ qsub ccx.pbs
```

Wait until finish...
