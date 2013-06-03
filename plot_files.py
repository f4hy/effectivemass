#!/usr/bin/env python
import matplotlib.pyplot as plt
from matplotlib import mpl
import logging
import argparse
from matplotlib.widgets import CheckButtons
from compiler.ast import flatten
import os
import pandas as pd

from fitfunctions import *  # noqa
from cStringIO import StringIO

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


def determine_type(txt):
    firstline = txt.readline()
    if "(" in firstline and ")" in firstline:
        return "paren_complex"
    if "," in firstline:
        return "comma"
    return "space_seperated"


def read_file(filename):
    txt = lines_without_comments(filename)
    filetype = determine_type(txt)
    if filetype == "paren_complex":
        df = pd.read_csv(txt, delimiter=' ', names=["time", "correlator", "error", "quality"],
                         converters={1: parse_pair, 2: parse_pair})
    if filetype == "comma":
        df = pd.read_csv(txt, delimiter=',', names=["time", "correlator", "error", "quality"])
    if filetype == "space_seperated":
        df = pd.read_csv(txt, delimiter=' ', names=["time", "correlator", "error", "quality"])

    return df


def plot_files(files):
    markers = ['o', "D", "^", "<", ">", "v", "x", "p", "8"]
    # colors, white sucks
    colors = [c for c in mpl.colors.colorConverter.colors.keys() if c != 'w']
    print files
    plots = {}
    tmin_plot = {}
    has_colorbar = False
    for index, filename in enumerate(files):
        label = os.path.basename(filename)
        mark = markers[index % len(markers)]
        color = colors[index % len(colors)]
        df = read_file(filename)
        time_offset = df.time.values+(index*0.1)
        print df.head(20)
        print df.time.values, df.correlator.values, df.error.values
        if any(df["quality"].notnull()):
            logging.info("found 4th column, plotting as quality")
            cmap = mpl.cm.cool
            plots[label] = plt.errorbar(time_offset, df.correlator.values, yerr=df.error.values,
                                        linestyle="none", c=color, marker=mark, label=label,
                                        fmt=None, zorder=0)
            tmin_plot[label] = plt.scatter(time_offset, df.correlator.values, c=df.quality.values,
                                           s=50, cmap=cmap, marker=mark)
            plt.clim(0, 1)
            if not has_colorbar:
                cb = plt.colorbar(tmin_plot[label])
                has_colorbar = True
        else:
            plots[label] = plt.errorbar(time_offset, df.correlator.values, yerr=df.error.values,
                                        linestyle="none", c=color, marker=mark, label=label)

    print len(colors), len(markers)
    leg = plt.legend(fancybox=True, shadow=True)

    def toggle_errorbar_vis(ebarplot):
        for i in flatten(ebarplot):
            if i:
                i.set_visible(not i.get_visible())

    def func(label):
        toggle_errorbar_vis(plots[label])
        if label in tmin_plot.keys():
            tmin_plot[label].set_visible(not tmin_plot[label].get_visible())
        plt.draw()


    rax = plt.axes([0.85, 0.8, 0.1, 0.15])
    print [os.path.basename(f) for f in args.files]
    check = CheckButtons(rax, [os.path.basename(f) for f in args.files], [True]*len(plots))
    check.on_clicked(func)

    plt.show()



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="compute fits")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="increase output verbosity")
    # parser.add_argument('files', metavar='f', type=argparse.FileType('r'), nargs='+',
    #                     help='files to plot')
    parser.add_argument('files', metavar='f', type=str, nargs='+',
                        help='files to plot')
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)
        logging.debug("Verbose debuging mode activated")
    else:
        logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)

    plot_files(args.files)
