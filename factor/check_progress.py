"""
Module that checks the progress of a run
"""
import sys
import os
import shutil
import numpy as np
import pickle
import logging
import glob
import factor
import factor.directions
import factor.parset
import pyrap.images as pim
try:
    from matplotlib import pyplot as plt
    from matplotlib.patches import Polygon
    from matplotlib.ticker import FuncFormatter
except Exception as e:
    raise ImportError('PyPlot could not be imported. Plotting is not '
        'available: {0}'.format(e.message))
try:
    from wcsaxes import WCSAxes
    hasWCSaxes = True
except:
    hasWCSaxes = False

log = logging.getLogger('progress')


def run(parset_file):
    """
    Displays the current progress of a run
    """
    directions_list = load_directions(parset_file)

    plot_state(directions_list)


def load_directions(parset_file):
    """
    Return directions for a run
    """
    # Read parset
    parset = factor.parset.parset_read(parset_file)

    # Load directions. First check for user-supplied directions file then for
    # Factor-generated file from a previous run
    direction_list = []
    dir_parset = parset['direction_specific']
    if 'directions_file' in dir_parset:
        directions = factor.directions.directions_read(dir_parset['directions_file'],
            parset['dir_working'])
    elif os.path.exists(os.path.join(parset['dir_working'], 'factor_directions.txt')):
        directions = factor.directions.directions_read(os.path.join(parset['dir_working'],
            'factor_directions.txt'), parset['dir_working'])
    for direction in directions:
        has_state = direction.load_state()
        if has_state:
            direction_list.append(direction)

    return direction_list


def plot_state(directions_list):
    """
    Plots the facets of a run
    """
    global midRA, midDec

    # Set up coordinate system and figure
    points, midRA, midDec = factor.directions.getxy(directions_list)
    fig = plt.figure(1, figsize=(7.66,7))
    if hasWCSaxes:
        wcs = factor.directions.makeWCS(midRA, midDec)
        ax = WCSAxes(fig, [0.16, 0.1, 0.8, 0.8], wcs=wcs)
        fig.add_axes(ax)
    else:
        ax = plt.gca()

    # Plot facets
    for direction in directions_list:
        vertices = read_vertices(direction.vertices_file)
        RAverts = vertices[0]
        Decverts = vertices[1]
        xverts, yverts = factor.directions.radec2xy(RAverts, Decverts,
            refRA=midRA, refDec=midDec)
        xyverts = [np.array([xp, yp]) for xp, yp in zip(xverts, yverts)]
        mpl_poly = Polygon(np.array(xyverts), edgecolor='b', facecolor='none',
            clip_box=ax.bbox, picker=3.0, linewidth=2)
        mpl_poly.facet_name = direction.name
        mpl_poly.completed_ops = get_completed_ops(direction)
        mpl_poly.started_ops = get_started_ops(direction)
        mpl_poly.selfcal_images = find_selfcal_images(direction)
        ax.add_patch(mpl_poly)
        ax.add_artist(mpl_poly)

    ax.relim()
    ax.autoscale()
    ax.set_aspect('equal')

    if hasWCSaxes:
        RAAxis = ax.coords['ra']
        RAAxis.set_axislabel('RA', minpad=0.75)
        RAAxis.set_major_formatter('hh:mm:ss')
        DecAxis = ax.coords['dec']
        DecAxis.set_axislabel('Dec', minpad=0.75)
        DecAxis.set_major_formatter('dd:mm:ss')
        ax.coords.grid(color='black', alpha=0.5, linestyle='solid')
    else:
        plt.xlabel("RA (arb. units)")
        plt.ylabel("Dec (arb. units)")

    # Define coodinate formater to show RA and Dec under mouse pointer
    ax.format_coord = formatCoord

    fig.canvas.mpl_connect('pick_event', on_pick)
    plt.show()
    plt.close(fig)


def on_pick(event):
    facet = event.artist
    print('Current state of reduction for {}:'.format(facet.facet_name))
    print('    Completed operations: {}'.format(facet.completed_ops))
    print('      Started operations: {}'.format(facet.started_ops))

    # Open images (if any)
    if len(facet.selfcal_images) > 0:
        im = pim.image(selfcal_images)
        im.view()
    pl.draw()


def get_completed_ops(direction):
    """
    Returns list of completed operations
    """
    has_state = direction.load_state()
    if has_state:
        return direction.completed_operations
    else:
        return []


def get_started_ops(facet_name):
    """
    Returns list of started operations
    """
    has_state = direction.load_state()
    if has_state:
        return direction.started_operations
    else:
        return []


def find_selfcal_images(direction):
    """
    Returns the filenames of selfcal images
    """
    working_dir = direction.working_dir
    selfcal_dir = os.path.join(working_dir, 'facetselfcal', direction.name)

    if direction.use_wideband:
        selfcal_images = glob.glob(selfcal_dir+'/*.casa_image?2.image.tt0')
    else:
        selfcal_images = glob.glob(selfcal_dir+'/*.casa_image?2.image')

    return selfcal_images.sort()


def formatCoord(x, y):
    """Custom coordinate format"""
    global midRA, midDec
    RA, Dec = factor.directions.xy2radec([x], [y], midRA, midDec)
    return 'RA = {0:.2f} Dec = {1:.2f}'.format(RA[0], Dec[0])


def read_vertices(filename):
    """
    Returns facet vertices
    """
    with open(filename, 'r') as f:
        direction_dict = pickle.load(f)
    return direction_dict['vertices']


def resample(array, factor):
    """
    Return resampled version of an image
    """

    nx, ny = np.shape(array)

    nx_new = nx // factor
    ny_new = ny // factor

    array2 = np.zeros((nx_new, ny))
    for i in range(nx_new):
        array2[i, :] = np.mean(array[i * factor:(i + 1) * factor, :], axis=0)

    array3 = np.zeros((nx_new, ny_new))
    for j in range(ny_new):
        array3[:, j] = np.mean(array2[:, j * factor:(j + 1) * factor], axis=1)

    return array3
