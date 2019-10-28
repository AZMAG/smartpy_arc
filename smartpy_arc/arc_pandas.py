"""
Use this module to integrate ArcGIS data objects
with pandas.

Dependencies & caveats:
- Written and tested w/ ArcGIS 10.2.1 (build 3497)
- Must have ArcGIS desktop 64 bit background geoprocessing installed
- Not intended to run w/in the default ArcGIS python distribution, instead
    run w/in a scientific distribution like winpython or anaconda
- Must have the following in the python path of the distribution:
    - path to ArcGIS 64 bit bin:
        C:\Program Files (x86)\ArcGIS\Desktop10.2\bin64
    - path to arcpy:
        C:\Program Files (x86)\ArcGIS\Desktop10.2\arcpy

Expected workspaces:
- Shapefile and dbase table: full path to folder location
- File geodatabase: full path to geodatabse (.gdb folder)
- Database: full path .sde file

"""
import os
from collections import OrderedDict

import numpy as np
import pandas as pd
import arcpy

from .arc_utils import *


def arc_to_pandas(workspace_path, class_name, index_fld=None, flds=None, spatial=True, where=None,
                  fill_nulls=True, str_fill='', num_fill=-1, date_fill='1678-01-01 00:00:00'):
    """
    Used to import an ArcGIS data class into a pandas data frame.

    TODO: the defaults for filling null values are supplied to support previous workflows.
    Going forward it may make sense to update some of these and probably make np.nans
    the default.

    Parameters:
    ----------
    workspace_path: string
        Full path to ArcGIS workspace location.
    class_name: string
        name of the feature class or table to import.
    index_fld: string, optional, default None
        Name of field to serve as pandas index. If not provided
        an auto-generated index will be used. The index does not need
        to be unique.
    flds: list or dict of string, optional, default None
        List of fields to include in the data frame. If not provided all
        fields w/ valid types will be imported. Valid field types are
        double, single (float), integer (long), small integer(short)
        and text. Non-valid fields will be ignored. No data values will
        be converted to -1 for all numeric types and empty string for text.
    spatial: bool, default True
        If True, adds the applicable derived spatial columns.
    fill_nulls: bool, default True
        If True, null values will be filled, if False, they will np.nan
    str_fill: str, default ''
        Value to fill nulls in string/text columns.
    num_fill: int, default -1
        Value to fill nulls in numeric columns.
    date_fill: str, default '1678-01-01 00:00:00'
        Value to fill date/time columns.

    Returns
    -------
    pandas.DataFrame

    Notes:
        1 - If exporting a feature layer or table view, this will currently
            support views that have fields that are not visivble, BUT will
            NOT support views with fields that have been re-named.

    """

    with TempWork(workspace_path):

        # define valid field types and null replacement values
        valid_field_types = {
            "OID": num_fill,
            "Double": num_fill,
            "Integer": num_fill,
            "Single": num_fill,
            "SmallInteger": num_fill,
            "String": str_fill,
            "Date": date_fill
        }

        # get valid fields based on their type, assign null replacement values
        rename_dict = None
        if flds:
            if isinstance(flds, dict):
                rename_dict = flds
                flds = flds.keys()

        fld_names = []
        null_dict = {}

        for fld in arcpy.ListFields(class_name):
            if flds is None or fld.name in flds:
                if fld.type in valid_field_types and fld.name:
                    fld_names.append(str(fld.name))
                    null_dict[str(fld.name)] = valid_field_types[str(fld.type)]

        # add geometry properties
        desc = arcpy.Describe(class_name)
        if desc.dataType in ["FeatureClass", "FeatureLayer"] and spatial:
            fld_names.append("SHAPE@X")
            fld_names.append("SHAPE@Y")

            if desc.shapeType == "Polygon":
                fld_names.append("SHAPE@AREA")

            if desc.shapeType == "Polygon" or desc.shapeType == "Polyline":
                fld_names.append("SHAPE@LENGTH")

        # convert feature attributes to numpy array (structured array)
        if where is None:
            arr = arcpy.da.TableToNumPyArray(class_name, fld_names, null_value=null_dict)
        else:
            arr = arcpy.da.TableToNumPyArray(
                class_name, fld_names, where_clause=where, null_value=null_dict)

        # convert the structured array to a pandas data frame
        df = pd.DataFrame(arr)

        # rename columns
        if rename_dict:
            df.rename(columns=rename_dict, inplace=True)

        # set the index if provided
        if index_fld is not None:
            df.set_index(index_fld, inplace=True)
            df.sort_index(inplace=True)

        # set nulls back if desired
        # TODO: look possible make this the default and
        # use more distinct null values
        if not fill_nulls:
            df.replace([num_fill, str_fill, 'nan'], np.nan, inplace=True)
            df = df.astype(str).replace(date_fill, np.nan)
    return df


def pandas_to_array(df, keep_index=True, cols=None):
    """
    Exports a pandas data from to a structured numpy array that can be
    provided to arcpy functions.

    Parameters:
    ----------
    df: pandas.DataFrame
        Data frame to export.
    keep_index: bool, optional, default True
        If True, column(s) will be created from the index.
    cols: list <string>, optional, default None:
        List of fields/columns to include in output, if not provided
        all fields will be exported. Also, include index names here.

    Returns
    -------
    numpy structured array

    """
    # push the index into columns
    if keep_index:
        df = df.reset_index()

    # put the pandas series into a dictionary of arrays
    #arr_values = {}
    arr_values = OrderedDict()
    arr_dtypes = []

    # use all columns if none provided
    if cols is None:
        cols = df.columns

    # remove unicode from column names
    cols = [str(item) for item in cols]

    for col in cols:
        arr = df[col].values

        # convert types to make ArcGIS happy
        if arr.dtype == np.object:
            arr = arr.astype(unicode)
        if arr.dtype == np.int64:
            max_val = arr.max()
            min_val = arr.min()
            if min_val < -2147483647 or max_val > 2147483647:
                arr = arr.astype(np.float64)
            else:
                arr = arr.astype(np.int32)
        if arr.dtype == np.bool:
            arr = arr.astype(np.int32)
        if arr.dtype == np.dtype('<M8[ns]'):
            arr = arr.astype('<M8[us]')

        arr_values[col] = arr
        arr_dtypes.append((col, arr.dtype))

    # create the structured array
    s_arr = np.empty(len(df), dtype=arr_dtypes)
    for col in arr_values:
        s_arr[col] = arr_values[col]

    return s_arr


def pandas_to_arc(df,
                  workspace_path,
                  output_table,
                  keep_index=True,
                  cols=None,
                  get_cursor=False,
                  overwrite=False,
                  x_col=None,
                  y_col=None,
                  srs=None):
    """
    Used to export a pandas data frame to an ArcGIS table.

    TODO: if an integer column has nulls convert it to float
    1st, otherwise the column gets converted to text with
    'np.nan' in the null cells.

    Parameters:
    ----------
    df: pandas.DataFrame
        Data frame to export.
     workspace_path: string
        Full path to ArcGIS workspace location.
    output_table: string
        name of the output table.
    keep_index: bool, optional, default True
        If True, column(s) will be created from the index.
    cols: list <string>, optional, default None:
        List of fields/columns to include in output, if not provided
        all fields will be exported. Also, include index names here.
    get_cursor: bool, optional, default False
        If True, returns dictionary with field info and an
        arcpy search cursor.
    overwrite: bool, optional, default False
        If True, an existing table will be overwritten. If False,
        and a table already exists, an error will be thrown. Note:
        ArcGIS is sometime weird about schema locks, so an exception
        could potentially be thrown if there is an outstanding cursor.

    Returns
    -------
    out_flds: dictionary<string,int>
        Dictionary of field names in the result, keys are field names
        and values are indexes in the row.
    rows: iterator of tuples
        Returns the results of arcpy.da.SearchCursor() on the exported result.

    """

    # convert data frame to structured array
    s_arr = pandas_to_array(df, keep_index, cols)

    # now export to arc
    old_workspace = arcpy.env.workspace
    arcpy.env.workspace = workspace_path

    if overwrite:
        # delete existing table it if it exists
        if output_table in arcpy.ListTables() + arcpy.ListFeatureClasses():
            arcpy.Delete_management(output_table)

    # convert the array to a ArcGIS table or feature class
    out_path = '{}/{}'.format(workspace_path, output_table)
    if x_col is not None and y_col is not None:
        arcpy.da.NumPyArrayToFeatureClass(
            s_arr, out_path, [x_col, y_col], srs)
    else:
        arcpy.da.NumPyArrayToTable(s_arr, out_path)

    # return a cursor with the results
    if get_cursor:
        fld_names = []
        out_flds = {}
        fld_idx = 0
        for curr_fld in arcpy.ListFields(output_table):
            fld_names.append(curr_fld.name)
            out_flds[curr_fld.name] = fld_idx
            fld_idx += 1
        rows = arcpy.da.SearchCursor(output_table, fld_names)
    else:
        out_flds = None
        rows = None

    # return the results
    arcpy.env.workspace = old_workspace
    return out_flds, rows


def pandas_join_to_arc(df,
                       join_to,
                       pandas_on,
                       arc_on,
                       output=None,
                       keep_index=True,
                       pandas_cols=None,
                       arc_cols=None):
    """
    Export a pandas data frame and join it to an existing
    feature class or table.

    Parameters:
    ----------
    df: pandas.DataFrame
        Data frame to export.
    join_to: str
        Full path to feature class, layer or table to join to.
    pandas_on: str
        Name of column in pandas data frame to join on.
    arc_on: str
        Name of field in arc dataset to join on.
    output: str, optional, default None
        Full path to output table or feature class.
        If not provided, data frame fields will be appended to the existing table.
    keep_index: bool, optional, default True
        If True, column(s) will be created from the index.
    pandas_cols: list <string>, optional, default None:
        List of fields/columns to include in output, if not provided
        all fields will be exported. Also, include index names here.
    arc_cols: list <string>, optional, default None:
        List of fields/columns to include from the arc dataset. If
        omitted all columns will be included.

    """

    arcpy.env.qualifiedFieldNames = False

    # convert data frame to structured array
    if pandas_cols:
        pandas_cols = list(set(pandas_cols + [pandas_on]))
    s_arr = pandas_to_array(df, keep_index, pandas_cols)

    # create the output
    if output:
        if arc_cols:
            # arc_cols = list(set(arc_cols + [arc_on]))
            if arc_on not in arc_cols:
                arc_cols.append(arc_on)
        create_new_feature_class(join_to, output, flds=arc_cols)
    else:
        output = join_to

    # attach the data frame
    arcpy.da.ExtendTable(
        output,
        arc_on,
        s_arr,
        pandas_on
    )


def pandas_to_features(df, fc, pd_id_fld, arc_id_fld, out_fc):
    """
    Exports a pandas data frame and join it to an existing
    feature class or table. Intended for larger datasts.

    Parameters:
    ----------
    df: pandas.DataFrame
        Data frame to export.
    fc: str
        Full path to feature class or layer to join to.
    pd_id_fld: str
        Name of field in data frame to join on.
    arc_id_fld: str
        Name of field in feature class to join on.
    out_fc: str
        Full path to the output feature class.

    """

    # output the pandas table to a scratch workspace and add an attribute index
    temp_out = '{}//{}'.format(arcpy.env.scratchGDB, '___pandas_out')
    pandas_to_arc(df, os.path.dirname(temp_out), os.path.basename(temp_out), overwrite=True)
    arcpy.AddIndex_management(temp_out, pd_id_fld, pd_id_fld)

    # do the join and export
    create_layer('__temp_polys', fc)
    arcpy.AddJoin_management(
        '__temp_polys',
        arc_id_fld,
        temp_out,
        pd_id_fld,
        'KEEP_COMMON'  # do we want to make this an input argument?
    )
    with TempQualifiedFields(False):
        arcpy.CopyFeatures_management('__temp_polys', out_fc)

    # tidy up
    arcpy.Delete_management(temp_out)
    arcpy.Delete_management('__temp_polys')
    arcpy.Delete_management('in_memory//__temp_export')
