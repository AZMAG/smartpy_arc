"""
Utility functions for working w/ ArcGIS pro environment and
libraries. Eventually start to deprecate the
arc_pandas and arc_utils libraties in lieu of this.

"""

import arcpy
import pandas as pd
from .arc_pandas import *

def get_map(aprx_name='CURRENT', map_name=None):
    """

    """
    aprx = arcpy.mp.ArcGISProject(aprx_name)
    if map_name is None:
        return aprx.activeMap
    else:
        return aprx.listMaps(map_name)[0]


def get_df(layer_name, **kwargs):
    """
    Note: if the layer has a selection applied to it, only the selected rows
    will be returned.

    """
    curr_m = get_map()
    lay = curr_m.listLayers(layer_name)[0]
    return arc_to_pandas('', layer_name, **kwargs)
