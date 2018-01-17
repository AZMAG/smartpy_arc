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
import numpy as np
import pandas as pd
import arcpy


def arc_to_pandas(workspace_path, class_name, index_fld=None, flds=None, spatial=True, where=None):
    """
    Used to import an ArcGIS data class into a pandas data frame.

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
    flds: string, optional, default None
        List of fields to include in the data frame. If not provided all
        fields w/ valid types will be imported. Valid field types are
        double, single (float), integer (long), small integer(short)
        and text. Non-valid fields will be ignored. No data values will
        be converted to -1 for all numeric types and empty string for text.
    spatial: bool, default True
        If True, adds the applicable derived spatial columns.
    Returns
    -------
    pandas.DataFrame

    Notes:
        1 - If exporting a feature layer or table view, this will currently
            support views that have fields that are not visivble, BUT will
            NOT support views with fields that have been re-named.

    """
    # update the workspace
    arcpy.env.workspace = workspace_path

    # define valid field types and null replacement values
    valid_field_types = {
        "OID": -1,
        "Double": -1,
        "Integer": -1,
        "Single": -1,
        "SmallInteger": -1,
        "String": "",
        "Date": '1678-01-01'
    }

    # get valid fields based on their type, assign null replacement values
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

    # set the index if provided
    if index_fld is not None:
        df.set_index(index_fld, inplace=True)
        df.sort_index(inplace=True)

    return df


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

    # push the index into columns
    if keep_index:
        df = df.reset_index()

    # put the pandas series into a dictionary of arrays
    arr_values = {}
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

    # now export to arc
    old_workspace = arcpy.env.workspace
    arcpy.env.workspace = workspace_path

    if overwrite:
        # delete existing table it if it exists
        if output_table in arcpy.ListTables() + arcpy.ListFeatureClasses():
            arcpy.Delete_management(output_table)

    # convert the array to a ArcGIS table or feature class
    if x_col is not None and y_col is not None:
        arcpy.da.NumPyArrayToFeatureClass(s_arr, workspace_path + "/" + output_table, [x_col, y_col], srs)
    else:
        arcpy.da.NumPyArrayToTable(s_arr, workspace_path + "/" + output_table)

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
    if old_workspace is not None:
        arcpy.env.workspace = old_workspace
    return out_flds, rows
