from pyccx import *
import numpy as np
from interface import DynamicUnderRelaxation, InterfaceData, RelativeCovergenceMonitor
import pyofm as ofm
import sys
# construct mapper
from parpydtk2 import *
import scipy.io as sio

ccx_logoff = True
if ccx_logoff:
    import logging
    logger = logging.getLogger('PYCCX')
    logger.setLevel(logging.CRITICAL)

use_relax = True
under_relax_obj = DynamicUnderRelaxation
init_omega = 1.0

tol = 5e-4
if tol > 1e-1:
    print('The tolerance is too large, this may lead to instability or low quality results')

# fluid solver must be initialized first, and parallel must be set to True
solverF = ofm.make_solver(
    'buoyantPimpleFoam', exec_name=sys.argv[0], kase='fluid', parallel=True)
solverF.create_fields()
solverF.initialize()
solverF.enable_backup_restore()
dt = solverF.init_dt()
iface = ofm.iface.InterfaceAdapter(solverF, 'interface')
fnodes = iface.extract_centres()
ftempAdap = ofm.CHT.TemperatureAdapter(iface)
ffluxAdap = ofm.CHT.HeatFluxAdapter(iface)

# use the comm wrapped in pyofm
comm = ofm.MPI.COMM_WORLD
comm_rank = comm.rank
comm_size = comm.size

if comm_size != 2:
    print('This job must run on 2 processes', file=sys.stderr)
    sys.exit(1)

# compute the global ids, since we know foam is fv codes and it uses
# domain decom, we can simply compute the ids, 1-based
g_size = iface.g_size()
f_size = iface.size()

# init solid on master process
if comm_rank == 0:
    run_solid = True
else:
    run_solid = False

if run_solid:
    jobname = 'solid/solidNbi1'
    output = 'asc'
    prob = Problem(jobname=jobname, output=output)
    msolver = prob.get_solver()
    msolver.initailize()
    # since we know there is one step
    # we stop b4 it
    msolver.solve(stopb4step=1)
    nlgeom = msolver.get_nlgeomsolver()
    nlgeom.initialize()

    # initialize our interface set
    iset = nlgeom.get_set(
        set_name='Interface',
        set_type='sfelem',
        is_surface=True
    )
    nset = nlgeom.get_set(
        set_name='Inodes',
        set_type='node',
        is_surface=True
    )

    # retrieve geometry data
    snodes = nset.coordinates()
    scents = iset.extract_face_centers()
    kon = iset.localize_mesh().reshape(-1, 3)  # we know only linear tris

    # create cht adapter
    solverS = CHTAdapter(nlgeom=nlgeom)
    solverS.add_interface(set_acc=nset, is_settable=False,
                          itype=CHTAdapter.TEMP)
    solverS.add_interface(set_acc=iset, is_settable=True,
                          itype=CHTAdapter.DFLUX)


# put a barrier here for extra safety
comm.barrier()

f_size = fnodes.shape[0]
freal_size = f_size
# print(f_size, comm_rank)
# sys.exit(status=0)
# hard-code, simple collective can do this in runtime through...
gid_rank = [[1, 80], [81, 161]]
gids = np.arange(gid_rank[comm_rank][0],
                 gid_rank[comm_rank][1] + 1, dtype='int32')

blue = IMeshDB()
green = IMeshDB()

# use blue for fluid
Tf = 'Tf'
Ff = 'Ff'

# rotate the plane
fnodes[:, 1] = fnodes[:, 2]
fnodes[:, 2] = 0.0

blue.begin_create()
blue.create_vertices(fnodes)
blue.assign_gids(gids)
blue.finish_create(False)

blue.create_field(Tf)
blue.create_field(Ff)

# use green for solid
green.begin_create()
# only assign nodes on master rank
if run_solid:
    snodes[:, 1] = snodes[:, 2]
    snodes[:, 2] = 0.0
    green.create_vertices(snodes)
# we use trivial global ids, since ccx is serial code
green.finish_create()

# NOTE to support collective comm, we have to create fields on all cores
Ts = 'Ts'
Fs = 'Fs'
green.create_field(Ts)
green.create_field(Fs)

mapper = Mapper(blue=blue, green=green)

# some parameters
mapper.dimension = 2
mapper.awls_conf(ref_r_b=0.1, ref_r_g=0.1)

mapper.begin_initialization()
mapper.register_coupling_fields(bf=Ff, gf=Fs, direct=B2G)
mapper.register_coupling_fields(bf=Tf, gf=Ts, direct=G2B)
mapper.end_initialization()

# interface data
fluxF = InterfaceData(size=freal_size, value=0.0)
fluxF_dup = InterfaceData(size=f_size, value=0.0)
tempF = InterfaceData(size=freal_size, value=1000.0)
tempF_dup = InterfaceData(size=f_size, value=1000.0)
if run_solid:
    fluxS = InterfaceData(size=scents.shape[0], value=0.0)
    tempS = InterfaceData(size=snodes.shape[0], value=800.0)  # initial guess

# NOTE we pass in comm for the under relaxation and conv monitor
# so that the behavior is consistent
under_relax = under_relax_obj(init_omega=init_omega, comm=comm)
conv_mntr = RelativeCovergenceMonitor(tol=tol, comm=comm)

# maximum pc steps allowed
max_pc_steps = 200

if comm_rank == 0:
    flog = open('FDSNpar.log', mode='w')
    flog.write('Fluid Dirichlet with solid Neumann setting\n')

t = 0.0
step = 0
tF = 0.3
DT = 10.0 * dt


# I am not fully sure whether the time is consistent in foam, let's comm
def get_dt(dt_):
    return np.min(comm.allgather(dt_))


DT = get_dt(DT)

comm.barrier()

while t <= tF - 1e-6:
    t += DT

    pc_counts = 0

    # backup solutions
    solverF.backup_state()
    if run_solid:
        solverS.backup_state()

    if run_solid:
        green.assign_field(Ts, tempS.curr)
    green.resolve_empty_partitions(Ts)
    mapper.begin_transfer()
    mapper.transfer_data(bf=Tf, gf=Ts, direct=G2B, resolve_disc=True)

    tempF.curr[:] = blue.extract_field(Tf)

    # update fluid interface temperature
    ftempAdap.assign(tempF.curr)

    while True:
        # back up previous interface value
        tempF.backup()

        # advance fluid
        solverF.subcycle(DT)
        # retrieve fluid interface flux
        fluxF.curr[:] = ffluxAdap.extract()

        #fluxF_dup.curr[:] = dup_fluid_solu(fluxF.curr, fluid_dup_copy)

        blue.assign_field(Ff, fluxF.curr)
        mapper.transfer_data(bf=Ff, gf=Fs, direct=B2G, resolve_disc=True)

        if run_solid:
            sflux = green.extract_field(Fs)

            # interpolate to centres
            fluxS.curr[:] = (sflux[kon[:, 0]] +
                             sflux[kon[:, 1]] + sflux[kon[:, 2]]) / 3.0
            # update the distributed heat fluxes on solid interface
            solverS['Interface', SET].set_dfluxes(fluxS.curr)

            # advance solid
            solverS.adjust_timesize(DT)
            solverS.increment()
            tempS.curr[:] = solverS['Inodes', GET].get_temperatures()

            # assign values
            green.assign_field(Ts, tempS.curr)
        green.resolve_empty_partitions(Ts)

        # TODO can we remove this
        comm.barrier()
        mapper.transfer_data(bf=Tf, gf=Ts, direct=G2B, resolve_disc=True)

        tempF.curr[:] = blue.extract_field(Tf)

        # update residual
        tempF.update_res()

        # NOTE is_conv is consistent
        is_conv = conv_mntr.determine_convergence(tempF)
        if is_conv or pc_counts >= max_pc_steps:
            if run_solid:
                solverS.finish_increment()
            solverF.advance()
            dt = solverF.dt()
            DT = get_dt(10.0 * dt)
            break
        else:
            # if not converge, then underrelaxation and update to fluid then restore
            if use_relax:
                under_relax.determine_omega(tempF, step, pc_counts)
                under_relax.update_solution(tempF)
            solverF.restore_state()
            ftempAdap.assign(tempF.curr)
            if run_solid:
                solverS.restore_state()
                solverS.finish_increment()
            pc_counts = pc_counts + 1
            if pc_counts > 20 and pc_counts % 5 == 0 and comm_rank == 0:
                print('WARNING too slow convergence for step %d with correction iterations %d...' % (
                    step + 1, pc_counts))
    mapper.end_transfer()
    step += 1
    if comm_rank == 0:
        msg = 'step=%d: coupling_dt=%f, time=%f, pc_iterations=%i.' % (
            step, DT, t, pc_counts)
        print(comm_rank, msg)
        flog.write(msg + '\n')
        flog.flush()  # we can keep tracking the latest info in the log file through tail

# finalize
if run_solid:
    nlgeom.finalize()
    msolver.solve(skipsolve=True)
    msolver.finalize()

solverF.finalize()

if comm_rank == 0:
    flog.close()

# write data
sio.savemat(
    'fluid_interface%i.mat' % comm_rank,
    {'itr_sol': tempF.curr, 'grid': fnodes}
)
