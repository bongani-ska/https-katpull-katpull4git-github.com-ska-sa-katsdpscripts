#!/usr/bin/python
# Read in the results produced by analyse_point_source_scans.py
# Perform gain curve calculations and produce plots for report.
# T Mauch 24-10-2009, adapted from code originally written by S. Goedhardt

import os.path
import sys
import logging
import optparse
import glob

import numpy as np
import numpy.lib.recfunctions as nprec
import matplotlib.pyplot as plt
import matplotlib.widgets as widgets
from matplotlib.backends.backend_pdf import PdfPages
from scipy import optimize

import scape
import katpoint

# These fields in the csv contain strings, while the rest of the fields are assumed to contain floats
STRING_FIELDS = ['dataset', 'target', 'timestamp_ut', 'data_unit']

def parse_arguments():
    parser = optparse.OptionParser(usage="%prog [opts] <directories or files>",
                               description="This fits gain curves to the results of analyse_point_source_scans.py")
    parser.add_option("-o", "--output", dest="outfilebase", type="string", default='gain_curve',
                  help="Base name of output files (*.png for plots and *_results.txt for messages)")
    parser.add_option("-p", "--polarisation", type="string", default="I", 
                  help="Polarisation to analyse, options are I, HH or VV. Default is I.")
    parser.add_option("-t", "--targets", default=None, help="Comma separated list of targets to use from the input csv file. Default is all of them.")
    parser.add_option("--tsys_lim", type="float", default=150, help="Limit on calculated Tsys to flag data for atmospheric fits.")
    parser.add_option("--eff_min", type="float", default=35, help="Minimum acceptable calculated aperture efficiency.")
    parser.add_option("--eff_max", type="float", default=100, help="Maximum acceptable calculated aperture efficiency.")
    parser.add_option("--min_elevation", type="float", default=20, help="Minimum elevation to calculate statistics.")
    parser.add_option("-c", "--correct_efficiency", action="store_true", default=False, help="Correct the aperture efficiency for atmospheric effects.")
    parser.add_option("-e", "--elev_min", type="float", default=15, help="Minimum acceptable elevation for median calculations.")
    parser.add_option("-i", "--interferometric", action="store_true", default=False, help="Interferometric mode. Switches off Tsys and SEFD measurements.")
    (opts, args) = parser.parse_args()
    if len(args) ==0:
        print 'Please specify a csv file output from analyse_point_source_scans.py.'
        sys.exit(1)
    filename = args[0]
    return opts, filename

def angle_wrap(angle, period=2.0 * np.pi):
    """Wrap angle into the interval -*period* / 2 ... *period* / 2."""
    return (angle + 0.5 * period) % period - 0.5 * period


def parse_csv(filename, pol):
    """ Make an antenna object and a data array from the input csv file
    update the data array with the desired flux for the give polarisation

    Parameters
    ----------
    filename : string
        Filename containing the result of analyse_point_source_scans.py
        first line will contain the info to construct the antenna object

    Return
    ------
    :class: katpoint Antenna object
    data : heterogeneous record array
    """
    antenna = katpoint.Antenna(open(filename).readline().strip().partition('=')[2])
    #Open the csv file as an array of strings without comment fields (antenna fields are comments)
    data = np.loadtxt(filename, dtype='string', comments='#', delimiter=', ')
    #First non-comment line is the header with fieldnames
    fieldnames = data[0].tolist()
    #Setup all fields as float32
    formats = np.tile('float32', len(fieldnames))
    #Label the string fields as input datatype
    formats[[fieldnames.index(name) for name in STRING_FIELDS if name in fieldnames]] = data.dtype
    #Save the data as a heterogeneous record array  
    data = np.rec.fromarrays(data[1:].transpose(), dtype=zip(fieldnames, formats))
    #Get the antenna temp from the data array for the desired polarisation
    if pol == 'I':
        calc_beam_height = np.sqrt(data['beam_height_HH']*data['beam_height_VV'])
        calc_baseline_height = np.sqrt(data['baseline_height_HH']*data['baseline_height_VV'])
    else:
        calc_beam_height = data['beam_height_'+pol]
        calc_baseline_height = data['baseline_height_'+pol]
    #Add the calculated beam height and baseline heights to the data array
    data = nprec.append_fields(data, ['calc_beam_height','calc_baseline_height'], [calc_beam_height,calc_baseline_height], ['float32','float32'])

    return data, antenna


def compute_gain_e(data, antenna):
    """ Compute the gain and apeture efficiency from the data.

    Parameters
    ----------
    data : heterogeneous record array containing 'calc_temp' and 'flux' records
    antenna : a katpoint:antenna object describing the antenna to use
    
    Return
    ------
    gain : The gains
    e    : The apeture efficiency
    """
    gain = data['calc_beam_height'] / data['flux']
    # Get the geometric area of the dish
    ant_area = np.pi * (antenna.diameter / 2.0) ** 2
    # The apeture efficiency
    e = gain*(2761/ant_area)*100
    
    return gain, e


def compute_tsys_sefd(data, gain):
    """ Compute Tsys and the SEFD from the gains and the baseline heights.

    Parameters
    ----------
    data : heterogeneous record array containing 'calc_temp' and 'flux' records
    gain : an array of gains calculated from the beam heights
    
    Return
    ------
    Tsys : The system temperature derived from the baseline heights
    SEFD : The system equivalent flux density derived from Tsys and the gain
    """
    # Tsys can be estimated from the baseline height.
    Tsys = data['calc_baseline_height']
    # SEFD is Tsys/G
    SEFD = Tsys/gain
    return Tsys, SEFD


def determine_good_data(data, targets=None, tsys=None, tsys_lim=150, eff=None, eff_lim=[35,100]):
    """ Apply conditions to the data to choose which can be used for 
    fitting.
    Conditions are:
        1: Target name must be in 'targets' (use all targets if targets=None).
        2: Range of aperture efficiencies between eff_lim[0] and eff_lim[1].
        3: Tsys < tsys_lim.
        4: Beam height and baseline data in csv file must not be 'nan'.
        5: Units of beam height must be K

    Parameters
    ----------
    data : heterogeneous record array containing 'targets', 'beam_height' records
    targets (optional) : list of targets to keep. 'None' means use all targets.
    tsys (optional): tsys array (same lengths as data). 'None' means don't select on Tsys.
    eff (optional): array of apeture efficiencies/ 'None' means don't select on apeture efficiency.

    Return
    ------
    good : boolean mask of data to keep True means good data, False means bad data.
    """
    #Initialise boolean array of True for defaults
    good = [True] * data.shape[0]
    #Check for wanted targets
    if targets is not None:
        good = good & np.array([test_targ in targets for test_targ in data['target']])
    #Check for wanted tsys
    if tsys is not None:
        good = good & (tsys < tsys_lim)
    #Check for wanted eff
    if eff is not None:
        good = good & ((eff>eff_lim[0]) & (eff<eff_lim[1]))
    #Check for nans
    good = good & ~(np.isnan(data['calc_beam_height'])) & ~(np.isnan(data['calc_baseline_height']))
    #Check for units of K
    good = good & (data['data_unit'] == 'K')

    return good

def fit_atmospheric_absorption(gain, elevation):
    """ Fit an elevation dependent atmospheric absorption model.
        Model is G=G_0*exp(-tau*airmass)

    """
    #Airmass increases as inverse sine of the elevation    
    airmass = 1/np.sin(elevation)
    #
    fit = np.polyfit(airmass, np.log(gain), 1)
    #
    tau,g_0 = -fit[0],np.exp(fit[1])

    return g_0, tau

def fit_atmospheric_emission(tsys, elevation, tau):
    """ Fit an elevation dependent atmospheric emission model.

    """
    #Airmass increases as inverse sine of the elevation    
    airmass = 1/np.sin(elevation)
    #Fit T_rec + T_atm*(1-exp(-tau*airmass))
    fit = np.polyfit(1 - np.exp(-tau*airmass),tsys,1)
    # Get T_rec and T_atm
    tatm,trec = fit[0],fit[1]

    return tatm,trec

def make_result_report(data, good, opts, output_filename, gain, e, g_0, tau, Tsys=None, SEFD=None, T_atm=None, T_rec=None):
    """ Generate a pdf report containing relevant results 

    """

    #Set up list of separate targets for plotting
    if opts.targets:
        targets = opts.targets.split(',')
    else:
        #Plot all targets 
        targets = list(set(data['target']))
    #Separate masks for each target to plot separately
    targetmask={}
    for targ in targets:
        targetmask[targ] = np.array([test_targ==targ.strip() for test_targ in data['target']])

    #Set up range of elevations for plotting fits
    fit_elev = np.linspace(5, 90, 85, endpoint=False)
    
    #Set up the figure
    fig = plt.figure(figsize=(8.3,11.7))

    fig.subplots_adjust(hspace=0.0)
    #Plot the gain vs elevation for each target
    ax1 = plt.subplot(511)
    for targ in targets:
        plt.plot(data['elevation'][good & targetmask[targ]], gain[good & targetmask[targ]], 'o', label=targ)
    #Plot the model curve for the gains
    fit_gain = g_0*np.exp(-tau/np.sin(np.radians(fit_elev)))
    plt.plot(fit_elev, fit_gain, 'k-')
    plt.ylabel('Gain (K/Jy)')
    #Get a title string
    title = 'Gain Curve, '
    title += antenna.name + ','
    if opts.polarisation == "I": title += ' Stokes ' + opts.polarisation + ','
    else: title += ' ' + opts.polarisation + ' polarisation,'
    if opts.interferometric: title = 'Interferometric ' + title
    title += ' ' + '%.0f MHz'%(data['frequency'][0])
    plt.title(title)
    legend = plt.legend(loc=4)
    plt.setp(legend.get_texts(), fontsize='small')

    #Plot the aperture efficiency vs elevation for each target
    ax2 = plt.subplot(512, sharex=ax1)
    for targ in targets:
        plt.plot(data['elevation'][good & targetmask[targ]], e[good & targetmask[targ]], 'o', label=targ)
    plt.ylim((opts.eff_min,opts.eff_max))
    plt.ylabel('Ae  %')



    if not opts.interferometric:
        #Plot Tsys vs elevation for each target and the fit of the atmosphere
        ax3 = plt.subplot(513, sharex=ax1)
        for targ in targets:
            plt.plot(data['elevation'][good & targetmask[targ]], Tsys[good & targetmask[targ]], 'o', label=targ)
        #Plot the model curve for Tsys
        fit_Tsys=T_rec + T_atm*(1 - np.exp(-tau/np.sin(np.radians(fit_elev))))
        plt.plot(fit_elev, fit_Tsys, 'k-')
        plt.ylabel('Tsys (K)')

        #Plot SEFD vs elevation for each target
        ax4 = plt.subplot(514, sharex=ax1)
        for targ in targets:
            plt.plot(data['elevation'][good & targetmask[targ]], SEFD[good & targetmask[targ]], 'o', label=targ)
        plt.ylabel('SEFD (Jy)')
        xticklabels = ax1.get_xticklabels()+ax2.get_xticklabels()+ax3.get_xticklabels()
    else:
        xticklabels = ax1.get_xticklabels()

    plt.setp(xticklabels, visible=False)
    plt.xlabel('Elevation (deg)')

    #Make some blank space for text
    ax5 = plt.subplot(515, sharex=ax1)
    plt.setp(ax5, visible=False)

    #Construct output text.
    outputtext = 'Median Gain (K/Jy): %1.4f  std: %.4f  (el. > %2.0f deg.)\n'%(np.median(gain[good]), np.std(gain[good]), opts.min_elevation)
    outputtext += 'Median Ae (%%):       %2.2f    std: %.2f      (el. > %2.0f deg.)\n'%(np.median(e[good]), np.std(e[good]), opts.min_elevation)
    outputtext += 'Fit of atmospheric attenuation:  '
    outputtext += 'G_0 (K/Jy): %.4f   tau: %.4f\n'%(g_0, tau)
    if Tsys is not None:
        outputtext += 'Median T_sys (K):   %1.2f    std: %1.2f      (el. > %2.0f deg.)\n'%(np.median(Tsys[good]),np.std(Tsys[good]),opts.min_elevation)
    if SEFD is not None:
        outputtext += 'Median SEFD (Jy):   %4.1f  std: %4.1f    (el. > %2.0f deg.)\n'%(np.median(SEFD[good]),np.std(SEFD[good]),opts.min_elevation)
    if (T_rec is not None) and (T_atm is not None):
        outputtext += 'Fit of atmospheric emission:  '
        outputtext += 'T_rec (K): %.2f   T_atm (K): %.2f'%(T_rec, T_atm)
    plt.figtext(0.1,0.1, outputtext,fontsize=11)
    fig.savefig(output_filename)



#get the command line arguments
opts, filename = parse_arguments()

# Get the data from the csv file
data, antenna = parse_csv(filename, opts.polarisation)

output_filename = opts.outfilebase + '_' + antenna.name + '_' + opts.polarisation + '_' + '%.0f'%data['frequency'][0] + '.pdf'

# Compute the gains from the data and fill the data recarray with the values
gain, e = compute_gain_e(data, antenna)

Tsys, SEFD = None, None
# Get TSys, SEFD if in single dish case
if not opts.interferometric:
    Tsys, SEFD = compute_tsys_sefd(data, gain)

# Determine "good" data to use for fitting and plotting
good = determine_good_data(data, targets=opts.targets, tsys=Tsys, tsys_lim=opts.tsys_lim, 
                            eff=e, eff_lim=[opts.eff_min,opts.eff_max])

# Obtain desired elevations in radians
az, el = angle_wrap(katpoint.deg2rad(data['azimuth'])), katpoint.deg2rad(data['elevation'])

# Get a fit of an atmospheric absorption model
g_0, tau = fit_atmospheric_absorption(gain[good],el[good])

T_atm, T_rec = None, None
# Fit T_atm and T_rec using atmospheric emission model for single dish case
if not opts.interferometric:
    T_atm, T_rec = fit_atmospheric_emission(Tsys[good],el[good],tau)

#remove the effect of atmospheric attenuation from the aperture efficiency
if opts.correct_efficiency:
    e = (gain -  g_0*np.exp(-tau/np.sin(el)) + g_0)*(2761/(np.pi*(antenna.diameter/2.0)**2))*100

# Make a report describing the results (no Tsys data if interferometric)
make_result_report(data, good, opts, output_filename, gain, e, g_0, tau, 
                    Tsys=Tsys, SEFD=SEFD, T_atm=T_atm, T_rec=T_rec)
