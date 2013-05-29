#!/usr/bin/env python
import matplotlib.pyplot as plt
from matplotlib import mpl
import logging
import build_corr
import argparse
import fit

from fitfunctions import *  # noqa
import inspect
import sys

NBOOTSTRAPS = 100


def tmin_plot(fn, cor, tmin, tmax, filename=None, bootstraps=NBOOTSTRAPS):
    emass_dt = 3

    index = fn.parameter_names.index("mass")
    fitted_params = []
    fitted_errors = []
    qualities = []
    for t in range(tmin, tmax-1):
        params, errors, qual = fit.fit(fn, cor, t, tmax, bootstraps, return_quality=True)
        fitted_params.append(params[index])
        fitted_errors.append(errors[index])
        qualities.append(qual)

    fig = plt.figure()

    emass = cor.effective_mass(emass_dt)
    emass_errors = cor.effective_mass_errors(emass_dt).values()
    emassplot = plt.subplot(211)
    emassplot.errorbar(emass.keys(), emass.values(), yerr=emass_errors, fmt='o')
    plt.ylim([0, max(emass.values())*1.2])
    plt.xlim([0, tmax + 2])

    tminplot = plt.subplot(212)
    cmap = mpl.cm.cool
    s = tminplot.scatter(range(tmin, tmax-1), fitted_params, c=qualities, s=50, cmap=cmap)
    tminplot.errorbar(range(tmin, tmax-1), fitted_params, yerr=fitted_errors, fmt=None, zorder=0)
    plt.ylim([0, max(emass.values())*1.2])
    plt.xlim([0, tmax + 2])
    fig.colorbar(s)
    if(filename):
        plt.savefig(filename)
    else:
        plt.show()


if __name__ == "__main__":

    function_list = inspect.getmembers(sys.modules["fitfunctions"], inspect.isclass)
    functions = {name: f for name, f in function_list}

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

    cor = build_corr.corr_and_vev_from_files_pandas(corrfile, vev1, vev2)
    tmin_plot(funct, cor, args.time_start, args.time_end, bootstraps=args.bootstraps)
