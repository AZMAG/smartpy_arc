"""
Utility functions for working w/ ArcGIS pro environment and
libraries. Eventually start to deprecate the
arc_pandas and arc_utils libraties in lieu of this.

"""
import arcpy
import pandas as pd
from .arc_pandas import *


def get_aprx(aprx_name='CURRENT'):
    """
    Return a project reference. By default
    this is the current map.

    Parameters:
    -----------
    aprx_name: str, optional, default 'CURRENT'
        Full path to the aprx. If not provided,
        uses the currently open project.

    Returns:
    --------
    arcpy.mp.ArcGISProject

    """
    return arcpy.mp.ArcGISProject(aprx_name)


def default_gdb(aprx=None):
    """
    Shorthand for getting the default geodatabase path.

    Parameters:
    ----------
    aprx: arcpy.mp.ArcGISProject, optional, default None
        If None, use the active project.

    Returns:
    --------
    str

    """
    if aprx is None:
        aprx = get_aprx()

    return aprx.defaultGeodatabase


def get_map(aprx_name='CURRENT', map_name=None):
    """
    Returns a map from ArcPro. Defaults to currently
    opened project and currently active map. If a name is provided, map names
    must be unique.

    Parameters:
    -----------
    aprx_name: str, optional, default CURRENT
        Name of the project. I not provided defaults to current project.
    map_name: str, optional, default None
        Name of the map. If not provided defaults to active maps.

    Returns:
    --------
    arcpy.mp.Map

    """
    aprx = arcpy.mp.ArcGISProject(aprx_name)
    if map_name is None:
        return aprx.activeMap
    else:
        maps = aprx.listMaps(map_name)
        if len(maps) > 0:
            raise ValueError('map names in the project must be unique!')
        return aprx.listMaps(map_name)[0]


def get_layer(name, aprx_name='CURRENT', map_name=None):
    """
    Fetch a layer from the provided map and project.

    Parameters:
    -----------
    name: str
        Name of layer to fetch.
    aprx_name: str, optional, default 'CURRENT'
        Project to fetch from. By default this is the currently open project.
    map_name: str, optional, default None
        Map to fetch from. By default this is the active map.

    Returns:
    --------
    arcpy.mp.Layer

    """
    curr_m = get_map(aprx_name, map_name)
    layers = curr_m.listLayers(name)
    if len(layers) == 0:
        raise ValueError('layer {} not found'.format(name))
    if len(layers) > 1:
        raise ValueError('{} is not a unique layer'.format(name))
    return layers[0]


def get_table(name, aprx_name='CURRENT', map_name=None):
    """
    Fetch a stand-alone table from the provided map and project.

    Parameters:
    -----------
    name: str
        Name of stand-alone table to fetch.
    aprx_name: str, optional, default 'CURRENT'
        Project to fetch from. By default this is the currently open project.
    map_name: str, optional, default None
        Map to fetch from. By default this is the active map.

    Returns:
    --------
    arcpy.mp.Layer

    """
    curr_m = get_map(aprx_name, map_name)
    tables = curr_m.listTables(name)
    if len(tables) == 0:
        raise ValueError('table {} not found'.format(name))
    if len(tables) > 1:
        raise ValueError('{} is not a unique table'.format(name))
    return tables[0]


def get_df(name, aprx_name='CURRENT', map_name=None, **kwargs):
    """
    Fetches a layer or stand-alone table from the active map and
    returns a pandas.DataFrame.

    Notes:
    ------
        1 - The name must be unique among all layers and stand-alone
            tables in the map/project.
        2 - If the layer/table has a selection applied to it, only the selected rows
            will be returned.

    Parameters:
    -----------
    name: str
        Name of layer or stand-alone table to fetch.
    aprx_name: str, optional, default 'CURRENT'
        Project to fetch from. By default this is the currently open project.
    map_name: str, optional, default None
        Map to fetch from. By default this is the active map.
    **kwargs:
        Optional additional arguments to pass to arc_pandas.arc_to_pandas method.
        See method for signature.

    Returns:
    --------
    pandas.DataFrame

    """
    curr_m = get_map(aprx_name, map_name)
    items = curr_m.listLayers(name) + curr_m.listTables(name)
    if len(items) == 0:
        raise ValueError('{} not found'.format(name))
    if len(items) > 1:
        raise ValueError('{} is not a unique name'.format(name))
    return arc_to_pandas('', items[0], **kwargs)
