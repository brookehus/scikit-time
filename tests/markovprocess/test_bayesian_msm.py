# This file is part of PyEMMA.
#
# Copyright (c) 2015, 2014 Computational Molecular Biology Group, Freie Universitaet Berlin (GER)
#
# PyEMMA is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import unittest
import numpy as np


from sktime.markovprocess import BayesianMSM, BayesianMSMPosterior, MarkovStateModel

from pyemma.util.statistics import confidence_interval


def bayesian_markov_model(dtrajs, lag, **kwargs) -> BayesianMSMPosterior:
    est = BayesianMSM(lagtime=lag, **kwargs)
    est.fit(dtrajs)
    model = est.fetch_model()
    return model


class TestBMSM(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # load observations
        import pyemma.datasets
        data = pyemma.datasets.load_2well_discrete()
        obs_micro = data.dtraj_T100K_dt10

        # stationary distribution
        pi_micro = data.msm.stationary_distribution
        pi_macro = np.zeros(2)
        pi_macro[0] = pi_micro[0:50].sum()
        pi_macro[1] = pi_micro[50:].sum()

        # coarse-grain microstates to two metastable states
        cg = np.zeros(100, dtype=int)
        cg[50:] = 1
        obs_macro = cg[obs_micro]

        # hidden states
        cls.nstates = 2
        # samples
        cls.nsamples = 100

        cls.lag = 100
        cls.bmsm_rev = bayesian_markov_model(obs_macro, cls.lag, dt_traj='4 fs',
                                             reversible=True, nsamples=cls.nsamples)
        cls.bmsm_revpi = bayesian_markov_model(obs_macro, cls.lag, dt_traj='4 fs',
                                               reversible=True, statdist_constraint=pi_macro,
                                               nsamples=cls.nsamples)

    def test_class_hierarchy(self):
        """ensure that the composite model has the right types """
        assert isinstance(self.bmsm_rev.prior, MarkovStateModel)
        assert all(isinstance(s, MarkovStateModel) for s in self.bmsm_rev.samples)

    def test_reversible(self):
        self._reversible(self.bmsm_rev)
        self._reversible(self.bmsm_revpi)

    def _reversible(self, msm):
        assert msm.prior.is_reversible
        assert all(s.is_reversible for s in msm.samples)

    def test_lag(self):
        self._lag(self.bmsm_rev)
        self._lag(self.bmsm_revpi)

    def _lag(self, msm):
        assert msm.prior.lagtime == self.lag
        assert all(s.lagtime == self.lag for s in msm.samples)

    def test_nstates(self):
        self._nstates(self.bmsm_rev)
        self._nstates(self.bmsm_revpi)

    def _nstates(self, msm):
        assert msm.prior.nstates == self.nstates
        assert all(s.nstates == self.nstates for s in msm.samples)

    def test_transition_matrix_samples(self):
        self._transition_matrix_samples(self.bmsm_rev, given_pi=False)
        self._transition_matrix_samples(self.bmsm_revpi, given_pi=True)

    def _transition_matrix_samples(self, msm, given_pi):
        Psamples = [s.transition_matrix for s in msm.samples]
        # shape
        assert np.array_equal(np.shape(Psamples), (self.nsamples, self.nstates, self.nstates))
        # consistency
        import msmtools.analysis as msmana
        for P in Psamples:
            assert msmana.is_transition_matrix(P)
            try:
                assert msmana.is_reversible(P)
            except AssertionError:
                # re-do calculation msmtools just performed to get details
                from msmtools.analysis import stationary_distribution
                mu = stationary_distribution(P)
                X = mu[:, np.newaxis] * P
                np.testing.assert_allclose(X, np.transpose(X), atol=1e-12,
                                           err_msg="P not reversible, given_pi={}".format(given_pi))

    def test_transition_matrix_stats(self):
        self._transition_matrix_stats(self.bmsm_rev)
        self._transition_matrix_stats(self.bmsm_revpi)

    def _transition_matrix_stats(self, msm):
        import msmtools.analysis as msmana
        # mean
        Ps = np.array([s.transition_matrix for s in msm.samples])
        Pmean = Ps.mean(axis=0)
        # test shape and consistency
        assert np.array_equal(Pmean.shape, (self.nstates, self.nstates))
        assert msmana.is_transition_matrix(Pmean)
        # std
        Pstd = Ps.std(axis=0)
        # test shape
        assert np.array_equal(Pstd.shape, (self.nstates, self.nstates))
        # conf
        L, R = confidence_interval(Ps)
        # test shape
        assert np.array_equal(L.shape, (self.nstates, self.nstates))
        assert np.array_equal(R.shape, (self.nstates, self.nstates))
        # test consistency
        assert np.all(L <= Pmean)
        assert np.all(R >= Pmean)

    def test_eigenvalues_samples(self):
        self._eigenvalues_samples(self.bmsm_rev)
        self._eigenvalues_samples(self.bmsm_revpi)

    def _eigenvalues_samples(self, msm):
        samples = np.array([s.eigenvalues() for s in msm.samples])
        # shape
        self.assertEqual(np.shape(samples), (self.nsamples, self.nstates))
        # consistency
        for ev in samples:
            assert np.isclose(ev[0], 1)
            assert np.all(ev[1:] < 1.0)

    def test_eigenvalues_stats(self):
        self._eigenvalues_stats(self.bmsm_rev)
        self._eigenvalues_stats(self.bmsm_revpi)

    def _eigenvalues_stats(self, msm, tol=1e-12):
        # mean
        samples = np.array([s.eigenvalues() for s in msm.samples])
        mean = samples.mean(axis=0)
        # test shape and consistency
        assert np.array_equal(mean.shape, (self.nstates,))
        assert np.isclose(mean[0], 1)
        assert np.all(mean[1:] < 1.0)
        # std
        std = samples.std(axis=0)
        # test shape
        assert np.array_equal(std.shape, (self.nstates,))
        # conf
        L, R = confidence_interval(samples)
        # test shape
        assert np.array_equal(L.shape, (self.nstates,))
        assert np.array_equal(R.shape, (self.nstates,))
        # test consistency
        assert np.all(L - tol <= mean)
        assert np.all(R + tol >= mean)

    def test_eigenvectors_left_samples(self):
        self._eigenvectors_left_samples(self.bmsm_rev)
        self._eigenvectors_left_samples(self.bmsm_revpi)

    def _eigenvectors_left_samples(self, msm):
        samples = np.array([s.eigenvectors_left() for s in msm.samples])
        # shape
        np.testing.assert_equal(np.shape(samples), (self.nsamples, self.nstates, self.nstates))
        # consistency
        for evec in samples:
            assert np.sign(evec[0, 0]) == np.sign(evec[0, 1])
            assert np.sign(evec[1, 0]) != np.sign(evec[1, 1])

    def test_eigenvectors_left_stats(self):
        self._eigenvectors_left_stats(self.bmsm_rev)
        self._eigenvectors_left_stats(self.bmsm_revpi)

    def _eigenvectors_left_stats(self, msm, tol=1e-12):
        # mean
        samples = np.array([s.eigenvectors_left() for s in msm.samples])
        mean = samples.mean(axis=0)
        # test shape and consistency
        assert np.array_equal(mean.shape, (self.nstates, self.nstates))
        assert np.sign(mean[0, 0]) == np.sign(mean[0, 1])
        assert np.sign(mean[1, 0]) != np.sign(mean[1, 1])
        # std
        std = samples.std(axis=0)
        # test shape
        assert np.array_equal(std.shape, (self.nstates, self.nstates))
        # conf
        L, R = confidence_interval(samples)
        # test shape
        assert np.array_equal(L.shape, (self.nstates, self.nstates))
        assert np.array_equal(R.shape, (self.nstates, self.nstates))
        # test consistency
        assert np.all(L - tol <= mean)
        assert np.all(R + tol >= mean)

    def test_eigenvectors_right_samples(self):
        self._eigenvectors_right_samples(self.bmsm_rev)
        self._eigenvectors_right_samples(self.bmsm_revpi)

    def _eigenvectors_right_samples(self, msm):
        samples = np.array([s.eigenvectors_right() for s in msm.samples])
        # shape
        np.testing.assert_equal(np.shape(samples), (self.nsamples, self.nstates, self.nstates))
        # consistency
        for evec in samples:
            assert np.sign(evec[0, 0]) == np.sign(evec[1, 0])
            assert np.sign(evec[0, 1]) != np.sign(evec[1, 1])

    def test_eigenvectors_right_stats(self):
        self._eigenvectors_right_stats(self.bmsm_rev)
        self._eigenvectors_right_stats(self.bmsm_revpi)

    def _eigenvectors_right_stats(self, msm, tol=1e-12):
        samples = np.array([s.eigenvectors_right() for s in msm.samples])
        # mean
        mean = samples.mean(axis=0)
        # test shape and consistency
        np.testing.assert_equal(mean.shape, (self.nstates, self.nstates))
        assert np.sign(mean[0, 0]) == np.sign(mean[1, 0])
        assert np.sign(mean[0, 1]) != np.sign(mean[1, 1])
        # std
        std = samples.std(axis=0)
        # test shape
        assert np.array_equal(std.shape, (self.nstates, self.nstates))
        # conf
        L, R = confidence_interval(samples)
        # test shape
        assert np.array_equal(L.shape, (self.nstates, self.nstates))
        assert np.array_equal(R.shape, (self.nstates, self.nstates))
        # test consistency
        assert np.all(L - tol <= mean)
        assert np.all(R + tol >= mean)

    def test_stationary_distribution_samples(self):
        self._stationary_distribution_samples(self.bmsm_rev)

    def _stationary_distribution_samples(self, msm):
        samples = np.array([s.stationary_distribution for s in msm.samples])
        # shape
        assert np.array_equal(np.shape(samples), (self.nsamples, self.nstates))
        # consistency
        for mu in samples:
            assert np.isclose(mu.sum(), 1.0)
            assert np.all(mu > 0.0)

    def test_stationary_distribution_stats(self):
        self._stationary_distribution_stats(self.bmsm_rev)
        self._stationary_distribution_stats(self.bmsm_revpi)

    def _stationary_distribution_stats(self, msm, tol=1e-12):
        samples = np.array([s.stationary_distribution for s in msm.samples])
        # mean
        mean = samples.mean(axis=0)
        # test shape and consistency
        assert np.array_equal(mean.shape, (self.nstates,))
        assert np.isclose(mean.sum(), 1.0)
        assert np.all(mean > 0.0)
        assert np.max(np.abs(mean[0] - mean[1])) < 0.05
        # std
        std = samples.std(axis=0)
        # test shape
        assert np.array_equal(std.shape, (self.nstates,))
        # conf
        L, R = confidence_interval(samples)
        # test shape
        assert np.array_equal(L.shape, (self.nstates,))
        assert np.array_equal(R.shape, (self.nstates,))
        # test consistency
        assert np.all(L - tol <= mean)
        assert np.all(R + tol >= mean)

    def test_timescales_samples(self):
        self._timescales_samples(self.bmsm_rev)
        self._timescales_samples(self.bmsm_revpi)

    def _timescales_samples(self, msm):
        samples = np.array([s.timescales() for s in msm.samples])
        # shape
        np.testing.assert_equal(np.shape(samples), (self.nsamples, self.nstates - 1))
        # consistency
        for l in samples:
            assert np.all(l > 0.0)

    def test_timescales_stats(self):
        self._timescales_stats(self.bmsm_rev)
        self._timescales_stats(self.bmsm_revpi)

    def _timescales_stats(self, msm):
        samples = np.array([s.timescales() for s in msm.samples])
        # mean
        mean = samples.mean(axis=0)
        # test shape and consistency
        assert np.array_equal(mean.shape, (self.nstates - 1,))
        assert np.all(mean > 0.0)
        # std
        std = samples.std(axis=0)
        # test shape
        assert np.array_equal(std.shape, (self.nstates - 1,))
        # conf
        L, R = confidence_interval(samples)
        # test shape
        assert np.array_equal(L.shape, (self.nstates - 1,))
        assert np.array_equal(R.shape, (self.nstates - 1,))
        # test consistency
        assert np.all(L <= mean)
        assert np.all(R >= mean)


if __name__ == "__main__":
    unittest.main()