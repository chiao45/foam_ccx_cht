import numpy as np


class InterfaceData(object):
    """Assume scalars for now"""

    def __init__(self, size, value, **kwargs):
        self.curr = np.ones(size, dtype=np.float64) * value
        self.prev = self.curr.copy()
        self.res = np.zeros(size, dtype=np.float64)
        self.res_prev = self.res.copy()
        self.tag = kwargs.pop('tag', None)

    def backup(self):
        self.prev[:] = self.curr

    def update_res(self):
        self.res_prev[:] = self.res
        self.res[:] = self.curr - self.prev


class DynamicUnderRelaxation(object):
    def __init__(self, init_omega, **kwargs):
        if init_omega < 0.0 or init_omega > 1.0:
            self.omega = 1.0
        else:
            self.omega = init_omega

    def determine_omega(self, idata, step, pc):
        assert isinstance(idata, InterfaceData)
        if step == 0 and pc == 0:
            return
        omega = self.omega
        bot = np.linalg.norm(idata.res - idata.res_prev)**2
        if bot <= 1e-24:
            self.omega = 1.0
        else:
            self.omega = -omega * \
                np.dot(idata.res_prev, idata.res - idata.res_prev) / bot
#         if self.omega > 1.0:
#             self.omega = 1.0

    def update_solution(self, idata):
        assert isinstance(idata, InterfaceData)
        idata.curr[:] = (1.0 - self.omega) * idata.prev + \
            self.omega * idata.curr


class ConstantUnderRelaxation(DynamicUnderRelaxation):
    def determine_omega(self, idata, step, pc):
        pass


class RelativeCovergenceMonitor(object):
    def __init__(self, tol, **kwargs):
        if tol <= 0.0:
            self.tol = 1e-6
        else:
            self.tol = tol
        self.comm = kwargs.get('comm', None)
        if self.comm is not None:
            self.size = self.comm.size
            self.rank = self.comm.rank

    def determine_convergence(self, idata):
        assert isinstance(idata, InterfaceData)
        bot = np.linalg.norm(idata.curr)
        if bot <= 1e-12:
            bot = 1.0
        err1 = np.linalg.norm(idata.res)
        if self.comm is None:
            err = err1 / bot
            return err <= self.tol
        # let's do all
        sent = np.asarray([err1, bot], dtype=float)
        buffer = self.comm.allgather(sent)
        Bot = 0.0
        Err = 0.0
        for i in range(self.size):
            Err += buffer[i][0]**2
            Bot += buffer[i][1]**2
        err = np.sqrt(Err/Bot)
        return err <= self.tol


class AbsCovergenceMonitor(object):
    def __init__(self, tol, **kwargs):
        if tol <= 0.0:
            self.tol = 1e-6
        else:
            self.tol = tol

    def determine_convergence(self, idata):
        assert isinstance(idata, InterfaceData)
        err = max(abs(idata.res))
        return err <= self.tol
