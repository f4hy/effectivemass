#!/usr/bin/env python
import matplotlib.pyplot as plt
import numpy as np
import logging
import correlator
import build_corr
import pylab
import argparse
from fitfunctions import *
import inspect, sys

from scipy import linalg
from scipy.special import gammaincc
from scipy.optimize import leastsq
from scipy.optimize import fmin
# from scipy.optimize import minimize
Nt = 128
NBOOTSTRAPS = 100

def fit(fn, cor, tmin, tmax, bootstraps=NBOOTSTRAPS):
    logging.info("Fitting data to {} from t={} to t={} using {} bootstrap smaples".format(fn.description, tmin, tmax, bootstraps))

    tmax = tmax+1 # I use ranges, so this needs to be offset by one
    fun = lambda v, mx, my: (fn.formula(v, mx) - my)

    initial_guess = fn.starting_guess
    x = np.array(range(tmin,tmax))
    ave_cor = cor.average_sub_vev()
    y = [ave_cor[t] for t in range(tmin, tmax)]
    original_ensamble_params, success = leastsq(fun, initial_guess, args=(x, y), maxfev=100000)
    if not success:
        raise ValueError()
    initial_guess = original_ensamble_params

    def cov_fit(correlator,guess):
        ave_cor = correlator.average_sub_vev()
        y = [ave_cor[t] for t in range(tmin, tmax)]
        cov = covariance_matrix(correlator, tmin, tmax)
        inv_cov = bestInverse(cov)
        start_time = correlator.times[0]
        aoc = np.fromiter(ave_cor.values(),np.float)[tmin-start_time:tmax-start_time]

        def cov_fun(g):
            """ Function to be minizied. computed using matrix mult"""
            vect = aoc - fn.formula(g,x)
            return vect.dot(inv_cov).dot(vect)
        uncorrelated_fit_values, success = leastsq(fun, guess, args=(x, y), maxfev=100000)
        if not success:
            raise ValueError()

        guess = uncorrelated_fit_values
        #would like to use minimize, but seems to be not installed
        results = fmin(cov_fun, guess, ftol=1.E-7, maxfun=1000000, full_output=1, disp=0, retall=0)
        covariant_fit, fit_info, flag = results[0], results[1:-1], results[-1]
        # covariant_fit = minimize(cov_fun, initial_guess)
        logging.debug("Fit results: f() ={}, Iterations={}, Function evaluations={}".format(*fit_info))
        if flag:
            logging.error("Fitter flag set to {}. Error!")
            raise RuntimeError("Fitter failed")

        logging.debug("Covariant fit {}, regular fit {}".format(repr(covariant_fit),
                                                                repr(uncorrelated_fit_values)))

        return(covariant_fit)

    boot_masses = []
    boot_amps = []
    for strap in bootstrap_ensamble(cor,N=bootstraps):
        fitted_params = cov_fit(strap, original_ensamble_params)
        boot_masses.append(fitted_params[0])
        boot_amps.append(fitted_params[1])

    original_ensamble_correlatedfit = cov_fit(cor, original_ensamble_params)

    print 'fit range', x
    print 'Uncorelated total fit: ', original_ensamble_params
    print 'Correlated total fit:  ', original_ensamble_correlatedfit
    print 'boot parameter masses: ', np.mean(boot_masses), np.var(boot_masses)

    v = (np.mean(boot_masses), np.mean(boot_amps))
    cov = covariance_matrix(cor, tmin, tmax)
    inv_cov = bestInverse(cov)
    chi_sqr = np.sum(((ave_cor[t] - fn.formula(v, t)) * inv_cov[t - tmin][tp - tmin] * (ave_cor[tp] - fn.formula(v, tp))
                      for t in range(tmin, tmax) for tp in range(tmin, tmax)))

    dof = len(x) - 2
    print u'\u03c7\u00b2 ={},   \u03c7\u00b2 / dof = {}, Qual {}'.format(
        chi_sqr,chi_sqr/dof, quality_of_fit(dof, chi_sqr))

    return (v, boot_masses)


def quality_of_fit(degrees_of_freedom, chi_sqr):
    dof = degrees_of_freedom
    return gammaincc(dof/2.0, chi_sqr / 2.0)

def plot_fit(fn, cor, tmin, tmax, filename=None, bootstraps=NBOOTSTRAPS):
    X = np.linspace(tmin, tmax, 200 * 5)
    fitted_params, boot_masses = fit(fn, cor, tmin, tmax, bootstraps)

    plt.figure()
    corplot = plt.subplot(211)

    corplot.errorbar(cor.times, cor.average_sub_vev().values(), yerr=cor.jackknifed_errors(), fmt='o')
    corplot.plot(cor.times, cor.average_sub_vev().values(), 'ro', X, fn.formula(fitted_params, X))
    plt.ylim([0, max(cor.average_sub_vev().values())])
    emass = cor.effective_mass(3)
    emass_errors = cor.effective_mass_errors(3).values()
    emassplot = plt.subplot(212)
    dataplt = emassplot.errorbar(emass.keys(), emass.values(), yerr=emass_errors, fmt='o')
    fitplt = emassplot.errorbar(X, np.mean(boot_masses) * np.ones_like(X), yerr=np.std(boot_masses))
    plt.legend([dataplt, fitplt], ["data", u"fit m={:.5f}\xb1{:.5f}".format(np.mean(boot_masses), np.std(boot_masses))])
    plt.ylim([0, 1])
    plt.xlim([0, tmax + 2])
    if(filename):
        plt.savefig(filename)
    else:
        plt.show()


def make_fake_cor():
    cfgs = list(range(50))
    times = list(range(16))
    data = {}
    vev = {}
    for c in cfgs:
        vev[c] = 0.0
        tmp = {}
        for t in times:
            tmp[t] = 5.0 * np.exp((-0.5) * t) + 6.0 * np.exp((-1.5) * t)
            tmp[t] += (pylab.rand() * 0.001) * tmp[t]
        data[c] = tmp

    return correlator.Correlator.fromDataDicts(data, vev, vev)


def bootstrap_cfgs(cor):
    return np.random.choice(cor.configs, size=len(cor.configs))


def bootstrap(cor):
    newcfgs = bootstrap_cfgs(cor)
    newcor = {i: cor.get(config=c) for i, c in enumerate(newcfgs)}
    # print cor.vev1
    newvev1 = {i: cor.vev1[c] for i, c in enumerate(newcfgs)}
    newvev2 = {i: cor.vev2[c] for i, c in enumerate(newcfgs)}
    return correlator.Correlator.fromDataDicts(newcor, newvev1, newvev2)


def bootstrap_ensamble(cor, N=NBOOTSTRAPS):
    return [bootstrap(cor) for i in range(N)]


def covariance_matrix(cor, tmin, tmax):
    nm1 = (1.0 / (len(cor.configs) - 1))
    nm0 = 1.0 / (len(cor.configs))
    mymat = np.zeros(((tmax - tmin),(tmax - tmin)))
    start_time = cor.times[0]
    aoc = np.fromiter(cor.average_over_configs().values(),np.float)[tmin-start_time:tmax-start_time]
    for v in cor.data.values():
        b = np.fromiter(v.values(), np.float)[tmin-start_time:tmax-start_time] - aoc
        # b = np.array(v.values()[tmin-start_time:tmax-start_time]).flat-aoc
        mymat += np.outer(b,b)
    return mymat*nm1*nm0

def CholeskyInverse(t):
    """
    Computes inverse of matrix given its Cholesky upper Triangular
    decomposition t.
    """
    nrows = len(t)
    B = np.zeros_like(t)

    # Backward step for inverse.
    for j in reversed(range(nrows)):
        tjj = t[j][j]
        S = np.sum([t[j][k] * B[j][k] for k in range(j + 1, nrows)])
        B[j][j] = 1.0 / tjj**2 - S / tjj  # flake8: noqa
        for i in reversed(range(j)):
            B[j][i] = B[i][j] = -np.sum([t[i][k] * B[k][j] for k in range(i + 1, nrows)]) / t[i][i]
    return B

class InversionError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


def bestInverse(M):
    TOLERANCE = 1.E-5

    def invert_error(i):
        return np.max(np.abs((np.dot(M, i) - np.identity(len(i)))))

    inv = linalg.inv(M)         # Will raise error if singular
    error = invert_error(inv)

    try:
        chol = linalg.cholesky(M, check_finite=False )
    except np.linalg.linalg.LinAlgError:
        logging.error("Not positive definite!")

    else:
        chol_inv = CholeskyInverse(chol)
        chol_error = invert_error(chol_inv)

        logging.debug("Inversions errors were inv={}, chol={}".format(error, chol_error))

        if chol_error > TOLERANCE and error > TOLERANCE:
            raise InversionError("Could not invert within tolerance")

        if chol_error < error:
            logging.debug("Using choleskey inverse")
            inv = chol_inv
        else:
            logging.debug("Using standard inverse")
    return inv

args = None



if __name__ == "__main__":

    function_list = inspect.getmembers(sys.modules["fitfunctions"], inspect.isclass)
    functions = {name: f for name,f in function_list}

    parser = argparse.ArgumentParser(description="compute fits")
    parser.add_argument("-i", "--inputfile", type=str, required=True,
                        help="Correlator file to read from")
    parser.add_argument("-v1", "--vev", type=str, required=False,
                        help="vev file to read from")
    parser.add_argument("-v2", "--vev2", type=str, required=False,
                        help="vev2 file to read from")
    parser.add_argument("-ts", "--time-start", type=int, required=True,
                        help="first time slice to start a fit")
    parser.add_argument("-te", "--time-end", type=int, required=True,
                        help="last time slice to fit")
    parser.add_argument("-b", "--bootstraps", type=int, required=False, default=NBOOTSTRAPS,
                        help="Number of straps")
    parser.add_argument("-p", "--plot", action="store_true", required=False,
                        help="Plot the resulting fit")
    parser.add_argument("-Nt", "--period", type=int, required=False,
                        help="Period in time direction (not required for all functions)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="increase output verbosity")
    parser.add_argument("-f", "--function", choices=functions.keys(),
                        required=False, default="cosh", help="function to fit to")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)
        logging.debug("Verbose debuging mode activated")
    else:
        logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)

    funct = functions[args.function](Nt=args.period)

    corrfile = args.inputfile
    vev1 = args.vev
    vev2 = vev1
    if args.vev2:
        vev2 = args.vev2

    cor = build_corr.corr_and_vev_from_files(corrfile, vev1, vev2, cfgs=347, ts=24)
    if args.plot:
        plot_fit(funct, cor, args.time_start, args.time_end, bootstraps=args.bootstraps)
    else:
        fit(funct, cor, args.time_start, args.time_end, bootstraps=args.bootstraps)
