#!/usr/bin/env python
import matplotlib.pyplot as plt
import matplotlib as mpl
import logging
import argparse
from matplotlib.widgets import CheckButtons
from compiler.ast import flatten
import os
import pandas as pd
from operator_tranlator import translate
import math

from fitfunctions import *  # noqa
from cStringIO import StringIO

import build_corr
import pandas_reader as pr
import plot_helpers
from plot_helpers import print_paren_error

import re

pair = re.compile(r'\(([^,\)]+),([^,\)]+)\)')


def parse_pair(s):
    if s:
        return complex(*map(float, pair.match(s).groups()))
    else:
        return ""


def lines_without_comments(filename, comment="#"):
    s = StringIO()
    with open(filename) as f:
        for line in f:
            if not line.startswith(comment):
                s.write(line)
    s.seek(0)
    return s


def myconverter(s):
    try:
        return np.float(s.strip(','))
    except:
        return np.nan


def removecomma(s):
    return int(s.strip(','))


def determine_type(txt):
    firstline = txt.readline()
    txt.seek(0)
    if "(" in firstline and ")" in firstline:
        return "paren_complex"
    if "," in firstline:
        return "comma"
    return "space_seperated"

def read_full_correlator(filename, emass=None, eamp=False, symmetric=False):
    logging.info("reading file {}".format(filename))
    cor = build_corr.corr_and_vev_from_pickle(filename, None, None)
    logging.info("File read.")

    if symmetric:
        corsym = cor.determine_symmetry()
        if corsym is None:
            logging.error("called with symmetric but correlator isnt")
            raise RuntimeError("called with symmetric but correlator isnt")
        logging.info("correlator found to be {}".format(corsym))
        cor.make_symmetric()

        cor.prune_invalid(delete=False, sigma=2.0)

    if emass:
        emasses = cor.periodic_effective_mass(1, fast=False, period=emass)
        #emasses = cor.periodic_effective_mass(1, fast=False, period=emass)
        #emasses = cor.effective_mass(1)
        times = emasses.keys()
        data = [emasses[t] for t in times]
        #errs = cor.periodic_effective_mass_errors(1, fast=False, period=emass)
        errs = cor.periodic_effective_mass_errors(1, fast=False, period=emass)
        #errs = cor.effective_mass_errors(1)
        errors = [errs[t]  for t in times]
        logging.debug("emasses {}".format(emasses))
        logging.debug("errs {}".format(errs))
    elif eamp:
        eamps = cor.periodic_effective_amp(1, len(cor.times), cor.periodic_effective_mass(1)[32] )
        times = eamps.keys()
        data = [eamps[t] for t in times]
        errors = [0  for t in times]
    else:
        times = cor.times
        data = [cor.average_sub_vev()[t] for t in times]
        errors = [cor.jackknifed_errors()[t]  for t in times]

    d = {"time": times, "correlator": data, "error": errors, "quality": [float('NaN') for t in times]}
    df = pd.DataFrame(d)
    return df

def read_file(filename, columns=None):
    if columns is None:
        columns = ["time", "correlator", "error", "quality"]

    txt = lines_without_comments(filename)
    filetype = determine_type(txt)
    if filetype == "paren_complex":
        df = pd.read_csv(txt, delimiter=' ', names=columns,
                         converters={1: parse_pair, 2: parse_pair})
    if filetype == "comma":
        # df = pd.read_csv(txt, sep=",", delimiter=",",
        #                  names=columns, skipinitialspace=True,
        #                  delim_whitespace=True, converters={0: removecomma, 1: myconverter, 2: myconverter})
        df = pd.read_csv(txt, sep=",", delimiter=",",
                         names=columns, skipinitialspace=True)
    if filetype == "space_seperated":
        df = pd.read_csv(txt, delimiter=' ', names=columns)
    return df


def get_fit(filename, noexcept=False):
    with open(filename) as f:
        for line in f:
            if line.startswith("#fit"):
                logging.debug("found fit info: {}".format(line.strip()))
                function, tmin, tmax, params, errors, Nt = line.split(",")
                fittype = function.split(" ")[0].strip()
                fn = function.split(" ")[1].strip()
                tmin = int(tmin.strip(" (),."))
                tmax = int(tmax.strip(" (),."))
                params = [float(i) for i in params.strip(" []\n").split()]
                errors = [float(i) for i in errors.strip(" []\n").split()]
                Nt = int(Nt)
                return (fittype, fn, tmin, tmax, params, errors, Nt)
    if noexcept:
        return ("single_exp", 0, 1, [0.0, 0.0], [0.0, 0.0])
    raise RuntimeError("No fit info")

def allEqual(lst):
     return not lst or lst.count(lst[0]) == len(lst)


def label_names_from_filelist(filelist):
    names = filelist
    logging.debug("first going to try matching level??")
    levelsearch = [re.search("level\d+", filename) for filename in names]
    if all(levelsearch):
        return [s.group(0) for s in levelsearch]

    basenames = [os.path.basename(filename) for filename in names]
    names = basenames
    if any(basenames.count(x) > 1 for x in basenames):
        logging.debug("two files with same basename, cant use basenames")
        names = filelist

    if "/" in names[0]:
        splitnames = [n.split("/") for n in names]
        if allEqual([len(s) for s in splitnames]):
            length = len(splitnames[0])
            newnames = [""] * len(names)
            logging.info("removing common strings")
            for i in range(length):
                nth = [s[i] for s in splitnames]
                pruned = remove_common_prepost(nth)
                newnames = [o+p for o,p in zip(newnames,pruned)]
            names = newnames

    names = remove_common_prepost(names)
    names = remove_common_segments(names)
    return names

def remove_common_segments(names, delim="_"):
    splitnames = [n.split("_") for n in names]
    if  not allEqual([len(s) for s in splitnames]):
        return names
    length = len(splitnames[0])
    newnames = [""] * len(names)
    for i in range(length):
        nth = [s[i] for s in splitnames]
        if not allEqual(nth):
            newnames = [o+n for o,n in zip(newnames,nth)]
    return newnames

def remove_common_prepost(names):
    if len(names) < 2:
        return names
    prefix = os.path.commonprefix(names)
    if len(prefix) > 1:
        names = [n[len(prefix):] for n in names]
    postfix = os.path.commonprefix([n[::-1] for n in names])
    if len(postfix) > 1:
        names = [n[:-len(postfix)] for n in names]
    names = [(n.strip(" _") if n != "" else "base") for n in names]
    return names


def add_fit_info(filename, ax=None):
    if not ax:
        ax = plt
    funmap = {"two_exp": two_exp, "single_exp": single_exp, "periodic_two_exp": periodic_two_exp,
              "fwd-back-exp": periodic_exp, "periodic_two_exp_const": periodic_two_exp_const, "fwd-back-exp_const": periodic_exp_const}
    try:
        fittype, function, tmin, tmax, fitparams, fiterrors, Nt = get_fit(filename)
        fun = funmap[function](Nt)
        massindex = fun.parameter_names.index("mass")
        mass = fitparams[massindex]
        masserror = fiterrors[massindex]
        if fittype == "#fit":
            logging.info("correlator fit info")
            xpoints = np.arange(tmin, tmax, 0.3)
            fitpoints = fun.formula(fitparams, xpoints)
            ax.plot(xpoints, fitpoints, ls="dashed", color="r", lw=2, zorder=5)
            if args.fitfunction:
                return fun.template.format(*fitparams)
        if fittype == "#fit_emass":
            xpoints = np.arange(tmin, tmax+1, 1.0)
            fitpoints = fun.formula(fitparams, xpoints)
            emassfit = []
            dt = 3
            for i in range(len(fitpoints))[:-dt]:
                try:
                    #emass = (1.0 / float(dt)) * np.log(fitpoints[i] / fitpoints[i + dt])
                    emass = (1.0 / float(dt)) * math.acosh((fitpoints[i+dt] + fitpoints[i-dt])/(2.0*fitpoints[i]))
                    emassfit.append(emass)
                except:
                    emassfit.append(np.nan)

            if args.fit_errors:
                ax.plot(xpoints[:-dt], np.full_like(xpoints[:-dt],mass+masserror), ls="--", color="k", lw=2, zorder=50)
                ax.plot(xpoints[:-dt], np.full_like(xpoints[:-dt],mass-masserror), ls="--", color="k", lw=2, zorder=50)
            else:
                ax.plot(xpoints[:-dt], emassfit, ls="dashed", color="r", lw=2, zorder=5)
        if masserror == 0:
            return "{}".format(mass)
        digits = -1.0*round(math.log10(masserror))
        formated_error = int(round(masserror * (10**(digits + 1))))
        formated_mass = "{m:.{d}f}".format(d=int(digits) + 1, m=mass)
        #return "{m}({e})".format(m=formated_mass, e=formated_error)
        return print_paren_error(mass, masserror)
    except RuntimeError:
        logging.error("File {} had no fit into".format(filename))


def add_function_plot(function_params, xmin, xmax):
    logging.debug("adding function with parameters {}".format(function_params))
    print function_params
    function = function_params[0]
    params = map(float,function_params[1:])
    print function, params

    plot_options = dict(lw=8)

    if function == "constant":
        plt.plot([xmin,xmax],[params[0],params[0]], **plot_options)
        return
    if function == "exp":
        t = np.arange(xmin,xmax)
        amp, mass = params
        cor = amp*(np.exp(-1.0*mass*t))
        plt.plot(t,cor, **plot_options)
        return
    if function == "periodic-exp":
        t = np.arange(xmin,xmax)
        amp, mass, period = params
        cor = amp*(np.exp(-1.0*mass*t) + np.exp(-1.0*mass*(period-t)))
        plt.plot(t,cor, **plot_options)
        return
    if function == "tanh":
        t = np.arange(xmin,xmax)
        amp, mass, period = params
        cor = amp*((np.exp(-1.0*mass*t) - np.exp(-1.0*mass*(period-t))) / (np.exp(-1.0*mass*t) + np.exp(-1.0*mass*(period-t))))
        plt.plot(t,cor, **plot_options)
        return



def plot_files(files, output_stub=None, yrange=None, xrang=None, cols=-1, fit=False, real=False, title=None):
    markers = ['o', "D", "^", "<", ">", "v", "x", "p", "8"]
    # colors, white sucks
    # colors = sorted([c for c in mpl.colors.colorConverter.colors.keys() if c != 'w' and c != "g"])
    colors = ['b', 'c', 'm', 'r', 'k', 'y']
    plots = {}
    tmin_plot = {}
    has_colorbar = False
    labels = label_names_from_filelist(files)
    fontsettings = dict(fontweight='bold', fontsize=18)
    if args.translate:
        labels = [translate(l) for l in labels]
    seperate = cols > 0
    ymin, ymax = 1000, None
    xmin, xmax = 1000, None
    rows = int(math.ceil(float(len(labels))/cols))
    if seperate:
        f, layout = plt.subplots(nrows=rows, ncols=cols, sharey=True, sharex=True, squeeze=False)
    else:
        f, axe = plt.subplots(1)
        axe.tick_params(axis='both', which='major', labelsize=20)
        axe.set_xlabel("time", **fontsettings)
    for i in range(cols):       # Set bottom row to have xlabels
        layout[rows-1][i].set_xlabel("time", **fontsettings)
    for index, label, filename in zip(range(len(files)), labels, files):
        i = (index)/cols
        j = (index) % cols
        if seperate:
            axe = layout[i][j]
        if j == 0:
            if "cor" in filename:
                axe.set_ylabel("Correlator", **fontsettings)
                if args.emass:
                    logging.warn("EMASS flag set but filename indicates a correlator file!")
            if "emass" in filename or args.emass:
                if args.scalefactor:
                    axe.set_ylabel("${\mathrm{\mathbf{m}_{eff}}}$ [MeV]", **fontsettings)
                else:
                    axe.set_ylabel("${\mathrm{\mathbf{m}_{eff}}}$", **fontsettings)

            if args.rel_error:
                axe.set_ylabel("Relative Error", **fontsettings)


        if fit:
            if seperate:
                fitstring = add_fit_info(filename, ax=axe)
            else:
                fitstring = add_fit_info(filename)
            if fitstring:
                if args.fit_only:
                    logging.info("setting label to {}".format(fitstring))
                    label = fitstring
                else:
                    label += " $m_{fit}=$" + fitstring

        mark = markers[index % len(markers)]
        color = colors[index % len(colors)]
        df = read_file(filename)
        if len(df.time) > len(set(df.time)):
            df = read_full_correlator(filename, args.emass, args.eamp, args.symmetric)

        if args.rel_error:
            df["correlator"] = df["error"]/df["correlator"]
            df["error"] = 0.0

        time_offset = df.time.values+(index*0.1)
        time_offset = df.time.values
        if seperate:
            time_offset = df.time.values
        logging.debug("%s %s %s", df.time.values, df.correlator.values, df.error.values)

        plotsettings = dict(linestyle="none", c=color, marker=mark, label=label, ms=5, elinewidth=2, capsize=5,
                            capthick=2, mec=color, aa=True)
        if args.rel_error:
            plotsettings["elinewidth"] = 0
            plotsettings["capthick"] = 0
        if seperate:
            logging.info("plotting {}  {}, {}".format(label, i, j))
            #axe.set_title(label)
            axe.legend(fancybox=True, shadow=True, loc=0)
        # Do a Tmin plot

        if args.scalefactor:
            scale = args.scalefactor
        else:
            scale = 1.0

        if any(df["quality"].notnull()):
            logging.info("found 4th column, plotting as quality")
            cmap = mpl.cm.cool
            plots[label] = axe.errorbar(time_offset, scale*df.correlator.values, yerr=scale*df.error.values, fmt=None,
                                        zorder=0, **plotsettings)
            tmin_plot[label] = axe.scatter(time_offset, scale*df.correlator.values, c=df.quality.values,
                                           s=50, cmap=cmap, marker=mark)
            tmin_plot[label].set_clim(0, 1)
            if seperate:
                has_colorbar = True
            if not has_colorbar and not seperate:
                cb = plt.colorbar(tmin_plot[label])  # noqa
                cb.set_label("Quality of fit", **fontsettings)
                axe.set_xlabel("tmin", **fontsettings)
                axe.set_ylabel("Fit Value", **fontsettings)
                has_colorbar = True

        else:                   # Not a tmin plot!
            if np.iscomplexobj(df.correlator.values):
                plots[label] = axe.errorbar(time_offset, scale*np.real(df.correlator.values), yerr=scale*np.real(df.error.values),
                                            **plotsettings)
                if not real:
                    plots["imag"+label] = axe.errorbar(time_offset, scale*np.imag(df.correlator.values),
                                                       yerr=scale*np.imag(df.error.values), markerfacecolor='none',
                                                       **plotsettings)
            else:
                plots[label] = axe.errorbar(time_offset, scale*df.correlator.values, yerr=scale*df.error.values, **plotsettings)

        if not yrange:
            ymin = min(ymin, min(df.correlator.fillna(1000)))
            ymax = max(ymax, max(df.correlator.fillna(0)))
            logging.debug("ymin {} ymax {}".format(ymin, ymax))
        if not xrang:
            xmin = min(xmin, min(df.time)-1)
            xmax = max(xmax, max(df.time)+1)
            logging.debug("xmin {} xmax {}".format(xmin, xmax))

        axe.legend(fancybox=True, shadow=True, loc=0)

    if args.plotfunction:
        add_function_plot(args.plotfunction, xmin,xmax)

    if not args.logarithm:
        if yrange:
            plt.ylim(yrange)
        else:
            plt.ylim(plot_helpers.auto_fit_range(scale*ymin,scale*ymax))
    if xrang:
        plt.xlim(xrang)
    else:
        plt.xlim(xmin, xmax)

    if args.logarithm:
        plt.yscale('log')

    if args.constant:
        bignum = 1000000
        plt.plot([-1*bignum,bignum],[args.constant,args.constant])


    if title:
        f.suptitle(title.replace("_", " "), **fontsettings)

    f.canvas.set_window_title(files[0])

    if seperate:
        plt.tight_layout(pad=0.0, h_pad=0.0, w_pad=0.0)
        if has_colorbar:
            f.subplots_adjust(right=0.95)
            cbar_ax = f.add_axes([0.96, 0.05, 0.01, 0.9])
            f.colorbar(tmin_plot[label], cax=cbar_ax)
    else:
        if not args.nolegend:
            leg = plt.legend(fancybox=True, shadow=True, loc=0)



    if(output_stub):
        width = 10.0
        f.set_size_inches(width, width*args.aspect)
        # plt.rcParams.update({'font.size': 20})
        # plt.tight_layout(pad=2.0, h_pad=1.0, w_pad=2.0)
        plt.tight_layout()
        plt.subplots_adjust(top=0.90)
        if args.eps:
            logging.info("Saving plot to {}".format(output_stub+".eps"))
            plt.savefig(output_stub+".eps")
        else:
            logging.info("Saving plot to {}".format(output_stub+".png"))
            plt.savefig(output_stub+".png", dpi=400)
        return

    def toggle_errorbar_vis(ebarplot):
        for i in flatten(ebarplot):
            if i:
                i.set_visible(not i.get_visible())

    def func(label):
        toggle_errorbar_vis(plots[label])
        if label in tmin_plot.keys():
            tmin_plot[label].set_visible(not tmin_plot[label].get_visible())
        plt.draw()

    if not seperate and not args.nolegend:
        rax = plt.axes([0.9, 0.8, 0.1, 0.15])
        check = CheckButtons(rax, plots.keys(), [True]*len(plots))
        check.on_clicked(func)
        # if not args.nolegend and len(plots) > 1:
        #     leg.draggable()

    plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="plot a set of data files")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="increase output verbosity")
    parser.add_argument("-f", "--include-fit", action="store_true",
                        help="check file for fit into, add it to plots")
    parser.add_argument("-fe", "--fit-errors", action="store_true",
                        help="put bands for the error on the fit")
    parser.add_argument("-e", "--eps", action="store_true",
                        help="save as eps not png")
    parser.add_argument("-nl", "--nolegend", action="store_true",
                        help="Don't plot the legend")
    parser.add_argument("-fo", "--fit_only", action="store_true",
                        help="replace_labels with fit info")
    parser.add_argument("-ff", "--fitfunction", action="store_true",
                        help="replace_labels with fit function")
    parser.add_argument("-r", "--real", action="store_true",
                        help="don't include the imgainry part'")
    parser.add_argument("-s", "--sort", action="store_true",
                        help="attempt to sort them first")
    parser.add_argument("-c", "--columns", type=int, required=False,
                        help="number of columns to make the plot", default=None)
    parser.add_argument("-n", "--number", type=int, required=False,
                        help="number of correlators to include per plot", default=10000)
    parser.add_argument("-t", "--title", type=str, required=False,
                        help="plot title", default=None)
    parser.add_argument("-tr", "--translate", action="store_true", required=False,
                        help="Attempt to translate the names (of operators)")
    parser.add_argument("-l", "--logarithm", action="store_true", required=False,
                        help="take the log on the y axis")
    parser.add_argument("-pf", "--plotfunction", type=str, required=False, nargs="+",
                        help="add a plot of a correlator with AMP and MASS")
    parser.add_argument("--constant", type=float, required=False, nargs=1,
                        help="add a constant line")
    parser.add_argument("-y", "--yrange", type=float, required=False, nargs=2,
                        help="set the yrange of the plot", default=None)
    parser.add_argument("-x", "--xrang", type=float, required=False, nargs=2,
                        help="set the xrang of the plot", default=None)
    parser.add_argument("-o", "--output-stub", type=str, required=False,
                        help="stub of name to write output to")
    # parser.add_argument('files', metavar='f', type=argparse.FileType('r'), nargs='+',
    #                     help='files to plot')
    parser.add_argument("--emass", metavar="Nt", type=float, default=None, required=False,
                        help="plot emasses not correlators, requires Nt the period in time")
    parser.add_argument("--scalefactor", type=float, default=None, required=False,
                        help="multiply by a scale factor")
    parser.add_argument("--symmetric", action="store_true",
                        help="make the correlator symmetric")
    parser.add_argument("--rel_error", action="store_true",
                        help="plot the relative error instead")
    parser.add_argument("--eamp", action="store_true",
                        help="plot eamps not correlators")
    parser.add_argument('files', metavar='f', type=str, nargs='+',
                        help='files to plot')
    parser.add_argument("--aspect", type=float, default=1.0, required=False,
                        help="determine the plot aspect ratio")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)
        logging.debug("Verbose debuging mode activated")
    else:
        logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)


    if args.output_stub is not None:
        root = logging.getLogger()
        errfilename = args.output_stub+".err"
        errfilehandler = logging.FileHandler(errfilename, delay=True)
        errfilehandler.setLevel(logging.WARNING)
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        errfilehandler.setFormatter(formatter)
        root.addHandler(errfilehandler)
        logfilename = args.output_stub+".log"
        logfilehandler = logging.FileHandler(logfilename, delay=True)
        logfilehandler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        logfilehandler.setFormatter(formatter)
        root.addHandler(logfilehandler)


    if args.sort:
        try:
            if args.fit_only:
                fitvalues = [get_fit(i, noexcept=True)[4][0] for i in args.files]
                s = [x[1] for x in sorted(zip(fitvalues, args.files), key=lambda t: float(t[0]))]
            else:
                s = [x[1] for x in sorted(zip(label_names_from_filelist(args.files), args.files),
                                          key=lambda t: int(re.search("\d+", t[0]).group(0)))]
            args.files = s
        except Exception as e:
            logging.warn("sorting failed")
            logging.error(e)
            exit()
        else:
            logging.info("level sorting worked")

    def chunks(l, n):
        """ Yield successive n-sized chunks from l.
        """
        for i in xrange(0, len(l), n):
            yield l[i:i+n]

    for index, chunk in enumerate(chunks(args.files, args.number)):
        ostub = args.output_stub
        if args.output_stub and len(args.files) > args.number:
            ostub = "{}_{}".format(args.output_stub, index)
        if args.columns:
            logging.info("Plotting each file as a seperate plot")
            plot_files(chunk, output_stub=ostub, cols=args.columns, yrange=args.yrange, xrang=args.xrang,
                       fit=args.include_fit, real=args.real, title=args.title)
        else:
            plot_files(chunk, output_stub=ostub,
                       yrange=args.yrange, xrang=args.xrang, fit=args.include_fit, real=args.real, title=args.title)
