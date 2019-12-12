# -*- coding: utf-8 -*-

# This code is part of Qiskit.
#
# (C) Copyright IBM 2019.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""
Fitters for hamiltonian parameters
"""

import numpy as np
import scipy.linalg as la
from qiskit.ignis.characterization import CharacterizationError
from qiskit import QiskitError

from .. import BaseCoherenceFitter, BaseHamiltonianFitter


class ZZFitter(BaseCoherenceFitter):
    """
    ZZ fitter
    """

    def __init__(self, backend_result, xdata,
                 qubits, spectators,
                 fit_p0, fit_bounds,
                 time_unit='micro-seconds'):

        circuit_names = []
        for cind, _ in enumerate(xdata):
            circuit_names.append('zzcircuit_%d_' % cind)

        self._spectators = spectators

        BaseCoherenceFitter.__init__(self, '$ZZ$',
                                     backend_result, xdata,
                                     qubits,
                                     self._osc_nodecay_fit_fun,
                                     fit_p0, fit_bounds, circuit_names,
                                     series=['0', '1'], expected_state='0',
                                     time_index=1, time_unit=time_unit)

    def ZZ_rate(self, qind=-1):

        """
        Return the ZZ rate from the fit of the two curves

        Args:
            qind: qubit index to return (-1 return all)

        return a list of zz_rates
        """

        freq0 = self._get_param(1, qind, series='0', err=False)
        freq1 = self._get_param(1, qind, series='1', err=False)

        return np.array(freq1)-np.array(freq0)

    def plot_ZZ(self, qind, ax=None, show_plot=False):

        """
        Plot ZZ data. Will plot both traces on the plot.

        Args:
            qind: qubit index to plot
            ax: plot axes
            show_plot: call plt.show()

        Returns:
            the axes object
        """

        from matplotlib import pyplot as plt

        if ax is None:
            plt.figure()
            ax = plt.gca()

        pltc = ['b', 'g']
        linec = ['r', 'black']

        for seriesind, series in enumerate(['0', '1']):

            ax.errorbar(self._xdata, self._ydata[series][qind]['mean'],
                        self._ydata[series][qind]['std'],
                        marker='.', markersize=9,
                        c=pltc[seriesind], linestyle='')
            ax.plot(self._xdata, self._fit_fun(self._xdata,
                                               *self._params[series][qind]),
                    c=linec[seriesind], linestyle='--',
                    label='Q%d in state %s' %
                    (self._spectators[qind], series))

        ax.tick_params(axis='x', labelsize=14, labelrotation=70)
        ax.tick_params(axis='y', labelsize=14)
        ax.set_xlabel('Time [' + self._time_unit + ']', fontsize=16)
        ax.set_ylabel('Ground state population', fontsize=16)
        ax.set_title(self._description + ' for qubit ' +
                     str(self._qubits[qind]), fontsize=18)
        ax.legend(fontsize=12)
        ax.grid(True)
        if show_plot:
            plt.show()

        return ax


class CrossResonanceHamiltonianFitter(BaseHamiltonianFitter):
    """
    Cross resonance Hamiltonian fitter.
    """

    def __init__(self, backend_result, xdata, qubits, fit_p0, fit_bounds):
        """ Create new fitter.

        The fitter estimates CR Hamiltonian composed of XI, YI, ZI, ZX, ZY and ZZ
        interaction terms. Qubits are ordered in little endian convention: |target, control>.
        You can refer to the article below for the details.

        Sheldon, S., Magesan, E., Chow, J. M. & Gambetta, J. M.
        Procedure for systematically tuning up cross-talk in the cross-resonance gate.
        Phys. Rev. A 93, 060302 (2016).

        Args:
            backend_result: a qiskit.result or list of results
            xdata: an array of the independent parameter generated by ``cr_tomography_schedules``.
            qubits: target qubit index to analyze partial CR Rabi oscillation.
            fit_p0: initial parameter guess.
            fit_bounds: boundary of fit parameters.
        """

        circuit_names = []
        for cind in range(len(xdata)):
            circuit_names.append('cr_ham_tomo_sched_%d' % cind)

        BaseHamiltonianFitter.__init__(self, 'CR', backend_result,
                                       xdata, qubits,
                                       self._bloch_equation_fit_fun, fit_p0,
                                       fit_bounds, circuit_names,
                                       series=['0', '1'], dim=2)

    def _calc_data(self):
        """
        Take count dictionary from the results, retrieve eigenvalues of
        each measurement basis and create a bloch vector for each CR duration.
        Load into the ``ydata`` which gives the partial CR rabi oscillation
        in Pauli basis. Note that vector is flattened to generate
        1-d array for fitting of vector function.

        Overloaded from ``BaseFitter._calc_data``.
        """
        meas_basis = 'x', 'y', 'z'

        self._ydata = {}
        for serieslbl in self._series:
            self._ydata[serieslbl] = []

            for qind in range(len(self.measured_qubits)):
                self._ydata[serieslbl].append({'mean': None, 'std': None})
                bloch_vecs = []
                for circname in self._circuit_names:
                    temp_bloch_vec = []
                    for axis in meas_basis:
                        expname = '%s_%s_%s' % (circname, axis, serieslbl)
                        counts = {}
                        for result in self._backend_result_list:
                            try:
                                counts = result.get_counts(expname)
                            except (QiskitError, KeyError):
                                pass
                        # convert count into eigenvalue
                        expv = 0
                        for bits, count in counts.items():
                            if bits[::-1][qind] == '1':
                                expv -= count
                            else:
                                expv += count
                        expv /= sum(counts.values())
                        temp_bloch_vec.append(expv)
                    bloch_vecs.append(temp_bloch_vec)
                bloch_vecs_flatten = np.array(bloch_vecs).T.ravel()
                self._ydata[serieslbl][qind]['mean'] = bloch_vecs_flatten

    def plot_rabi(self, qind=0, axs=None, show_plot=True):
        """
        Plot CR Rabi and fit result.

        Args:
            qind: qubit index to plot
            axs: tuple of axes to plot CR rabi on x, y, z measurement basis.
            show_plot: call ``plt.show()``

        Returns:
            The axes object
        """
        try:
            from matplotlib import pyplot as plt
        except ImportError:
            raise CharacterizationError('matplotlib is not installed.')

        if axs is None:
            fig = plt.figure(figsize=(15, 3))
            ax_1 = fig.add_subplot(131)
            ax_2 = fig.add_subplot(132)
            ax_3 = fig.add_subplot(133)
        else:
            ax_1, ax_2, ax_3 = axs

        # experimental data
        cr0_x, cr0_y, cr0_z = np.split(self.ydata['0'][qind]['mean'], 3)
        cr1_x, cr1_y, cr1_z = np.split(self.ydata['1'][qind]['mean'], 3)

        xdata_ns = self.xdata * 1e9
        ax_1.scatter(xdata_ns, cr0_x, color='b', label='|00>')
        ax_1.scatter(xdata_ns, cr1_x, color='r', label='|01>')
        ax_2.scatter(xdata_ns, cr0_y, color='b', label='|00>')
        ax_2.scatter(xdata_ns, cr1_y, color='r', label='|01>')
        ax_3.scatter(xdata_ns, cr0_z, color='b', label='|00>')
        ax_3.scatter(xdata_ns, cr1_z, color='r', label='|01>')

        # overwrite fitting results
        xdata_interp = np.linspace(0, max(self.xdata), 1000)

        fit_params0 = self.params['0'][qind]
        fit_params1 = self.params['1'][qind]

        fit_cr0 = self._bloch_equation_fit_fun(xdata_interp, *fit_params0)
        fit_cr1 = self._bloch_equation_fit_fun(xdata_interp, *fit_params1)

        fit_cr0_x, fit_cr0_y, fit_cr0_z = np.split(fit_cr0, 3)
        fit_cr1_x, fit_cr1_y, fit_cr1_z = np.split(fit_cr1, 3)

        xdata_interp_ns = xdata_interp * 1e9
        ax_1.plot(xdata_interp_ns, fit_cr0_x, 'b:')
        ax_1.plot(xdata_interp_ns, fit_cr1_x, 'r:')
        ax_2.plot(xdata_interp_ns, fit_cr0_y, 'b:')
        ax_2.plot(xdata_interp_ns, fit_cr1_y, 'r:')
        ax_3.plot(xdata_interp_ns, fit_cr0_z, 'b:')
        ax_3.plot(xdata_interp_ns, fit_cr1_z, 'r:')

        # format
        ax_1.set_xlim(0, max(xdata_ns))
        ax_2.set_xlim(0, max(xdata_ns))
        ax_3.set_xlim(0, max(xdata_ns))

        ax_1.set_ylim(-1, 1)
        ax_2.set_ylim(-1, 1)
        ax_3.set_ylim(-1, 1)

        ax_1.set_title(r'$\langle X \rangle$')
        ax_2.set_title(r'$\langle Y \rangle$')
        ax_3.set_title(r'$\langle Z \rangle$')

        ax_1.set_xlabel('ns')
        ax_2.set_xlabel('ns')
        ax_3.set_xlabel('ns')

        ax_1.legend()
        ax_2.legend()
        ax_3.legend()

        if show_plot:
            plt.show()

        return ax_1, ax_2, ax_3

    def plot_bloch(self, qind=0, axs=None, show_plot=True):
        """
        Plot CR Rabi and fit result.

        Args:
            qind: qubit index to plot
            axs: tuple of axes to plot bloch vector trajectory from |00> and |01>.
            show_plot: call ``plt.show()``

        Returns:
            The axes object
        """
        try:
            from matplotlib import pyplot as plt
            from matplotlib import cm
        except ImportError:
            raise CharacterizationError('matplotlib is not installed.')

        if axs is None:
            fig = plt.figure(figsize=(10, 5))
            ax_1 = fig.add_subplot(121, projection='3d')
            ax_2 = fig.add_subplot(122, projection='3d')
        else:
            ax_1, ax_2 = axs

        from qiskit.visualization.bloch import Bloch

        # experimental data
        cr0_x, cr0_y, cr0_z = np.split(self.ydata['0'][qind]['mean'], 3)
        cr1_x, cr1_y, cr1_z = np.split(self.ydata['1'][qind]['mean'], 3)

        # colors
        tone = np.linspace(0, 1, len(cr0_x))
        cmap = [cm.winter(val) for val in tone]

        pb0 = Bloch(axes=ax_1)
        pb0.point_color = cmap
        pb0.add_points((cr0_x, cr0_y, cr0_z), meth='l')
        pb0.add_points((cr0_x, cr0_y, cr0_z), meth='m')
        pb0.render(title='Initial state |00>')

        pb1 = Bloch(axes=ax_2)
        pb1.point_color = cmap
        pb1.add_points((cr1_x, cr1_y, cr1_z), meth='l')
        pb1.add_points((cr1_x, cr1_y, cr1_z), meth='m')
        pb1.render(title='Initial state |01>')

        if show_plot:
            plt.show()

        return ax_1, ax_2

    @staticmethod
    def _bloch_equation_fit_fun(x, omega_x, omega_y, delta):
        """
        Function to fit bloch equation.

        See the equations 4 and 5 of reference article.
        """
        # initial bloch vector |0>
        vec_r_t0 = np.matrix([0, 0, 1]).T

        # rotation generator
        mat_a = np.matrix([[0, delta, omega_y],
                           [-delta, 0, -omega_x],
                           [-omega_y, omega_x, 0]])

        # bloch vector at each time
        vec_ts = list(map(lambda t: la.expm(mat_a * t) * vec_r_t0, x))

        return np.array(vec_ts).T.ravel()

    @property
    def hamiltonian(self):
        """
        Return CR Hamiltonian.
        """
        for qid in self.measured_qubits:
            fit_params0 = self.params['0'][self.measured_qubits.index(qid)]
            fit_params1 = self.params['1'][self.measured_qubits.index(qid)]

            self._hamiltonian[qid]['XI'] = (fit_params0[0] + fit_params1[0]) / 2
            self._hamiltonian[qid]['YI'] = (fit_params0[1] + fit_params1[1]) / 2
            self._hamiltonian[qid]['ZI'] = (fit_params0[2] + fit_params1[2]) / 2
            self._hamiltonian[qid]['XZ'] = (fit_params0[0] - fit_params1[0]) / 2
            self._hamiltonian[qid]['YZ'] = (fit_params0[1] - fit_params1[1]) / 2
            self._hamiltonian[qid]['ZZ'] = (fit_params0[2] - fit_params1[2]) / 2

        return self._hamiltonian
