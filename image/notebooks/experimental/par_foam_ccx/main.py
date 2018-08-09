from pyccx import *
import numpy as np
from interface import DynamicUnderRelaxation, InterfaceData, RelativeCovergenceMonitor, AbsCovergenceMonitor, ConstantUnderRelaxation
import pyofm as ofm
import sys
# construct mapper
from parpydtk2 import *
import scipy.io as sio

# local support radius
fluid_r = 0.02
solid_r = 0.02

ccx_logoff = True
if ccx_logoff:
    import logging
    logger = logging.getLogger('PYCCX')
    logger.setLevel(logging.CRITICAL)

use_relax = True
under_relax_obj = DynamicUnderRelaxation
init_omega = 0.95
fluid_dup_copy = 3  # for each side

tol = 1e-3
if tol > 1e-1:
    print('The tolerance is too large, this may lead to instability or low quality results')


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

comm = ofm.MPI.COMM_WORLD
comm_rank = comm.rank
comm_size = comm.size

if comm_size != 2:
    print('This job must run on 2 processes', file=sys.stderr)
    sys.exit(-1)

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

def dup_fluid_mesh(fnodes, dist, copy):
    """This is for duplicating the fluid mesh in z-direction for supporting interpolation"""
    n = fnodes.shape[0]
    dist_ = fnodes[0, 2] #  input original z position
    temp = fnodes.copy()
    for i in range(2*copy):
        temp = np.concatenate((temp, fnodes), axis=0)
    for i in range(copy):
        temp[(i+1)*n:(i+2)*n, 2] = dist_+(i+1)*dist
        temp[(copy+i+1)*n:(copy+i+2)*n, 2] = dist_-(i+1)*dist
    return n, temp

def dup_fluid_solu(solu, copy):
    """assume scalar field"""
    n = solu.size
    my_solu = np.empty((2*copy+1)*n, dtype=float)
    for i in range(2*copy+1):
        my_solu[i*n:(i+1)*n]=solu
    return my_solu

(freal_size, fnodes) = dup_fluid_mesh(fnodes, 0.002, fluid_dup_copy)
f_size = fnodes.shape[0]
# NOTE since we know the two parts are equal in size
# in general, we need to communicate
gids = np.arange(comm_rank*f_size+1, (comm_rank+1)*f_size+1, dtype='int32')

mapper = Mapper()
blue = mapper.blue_mesh
green = mapper.green_mesh

# use blue for fluid
Tf = 'Tf'
Ff = 'Ff'

blue.begin_create()
blue.create_vertices(fnodes)
blue.assign_gids(gids)
blue.create_field(Tf)
blue.create_field(Ff)
blue.finish_create(False)

# use green for solid
green.begin_create()
# only assign nodes on master rank
if run_solid:
    green.create_vertices(snodes)
# NOTE to support collective comm, we have to create fields on all cores
Ts = 'Ts'
Fs = 'Fs'
green.create_field(Ts)
green.create_field(Fs)
# we use trivial global ids, since ccx is serial code
green.finish_create()

# some parameters
mapper.radius_b = fluid_r
mapper.radius_g = solid_r

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
else:
    fluxS = InterfaceData(size=1, value=0.0)
    tempS = InterfaceData(size=1, value=800.0)  # initial guess

under_relax = under_relax_obj(init_omega=init_omega)
# NOTE we pass in comm, so that the convergence can be determined consistently
conv_mntr = RelativeCovergenceMonitor(tol=tol, comm=comm)

# maximum pc steps allowed
max_pc_steps = 200

if comm_rank == 0:
    flog = open('FDSNpar.log', mode='w')
    flog.write('Fluid Dirichlet with solid Neumann setting\n')

t = 0.0
step = 0
tF = 0.15
DT = 10.0*dt

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
    # else:
    #     # assign value for dup node
    #     green.assign_field(Ts, tempS.curr[:1])
    mapper.begin_transfer()
    mapper.transfer_data(bf=Tf, gf=Ts, direct=G2B)

    tempF_dup.curr[:] = blue.extract_field(Tf)
    tempF.curr[:] = tempF_dup.curr[0:freal_size]

    # update fluid interface temperature
    ftempAdap.assign(tempF.curr)

    while True:
        # back up previous interface value
        tempF.backup()

        # advance fluid
        solverF.subcycle(DT)
        # retrieve fluid interface flux
        fluxF.curr[:] = ffluxAdap.extract()

        fluxF_dup.curr[:] = dup_fluid_solu(fluxF.curr, fluid_dup_copy)

        blue.assign_field(Ff, fluxF_dup.curr)
        mapper.transfer_data(bf=Ff, gf=Fs, direct=B2G)

        if run_solid:
            sflux = green.extract_field(Fs)

            # interpolate to centres
            fluxS.curr[:] = (sflux[kon[:, 0]] +
                             sflux[kon[:, 1]]+sflux[kon[:, 2]])/3.0
            # update the distributed heat fluxes on solid interface
            solverS['Interface', SET].set_dfluxes(fluxS.curr)

            # advance solid
            solverS.adjust_timesize(DT)
            solverS.increment()
            tempS.curr[:] = solverS['Inodes', GET].get_temperatures()

            # assign values
            green.assign_field(Ts, tempS.curr)

        # TODO can we remove this
        comm.barrier()
        mapper.transfer_data(bf=Tf, gf=Ts, direct=G2B)

        tempF_dup.curr[:] = blue.extract_field(Tf)
        tempF.curr[:] = tempF_dup.curr[0:freal_size]

        # update residual
        tempF.update_res()

        # NOTE is_conv is consistent
        is_conv = conv_mntr.determine_convergence(tempF)
        if is_conv or pc_counts >= max_pc_steps:
            if run_solid:
                solverS.finish_increment()
            solverF.advance()
            dt = solverF.dt()
            DT = get_dt(10.0*dt)
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
                    step+1, pc_counts))
    mapper.end_transfer()
    step += 1
    if comm_rank == 0:
        msg = 'step=%d: coupling_dt=%f, time=%f, pc_iterations=%i.' % (
            step, DT, t, pc_counts)
        print(comm_rank, msg)
        flog.write(msg+'\n')

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
    {'itr_sol': tempF.curr}
)
