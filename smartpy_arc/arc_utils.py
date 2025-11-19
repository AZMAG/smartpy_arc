"""

This modules contains functions that make it easier to work
ESRI data objects.

Note: this now houses arc_pandas stuff too, to avoid 
circular references.

"""
import os
import random
import arcpy

import os
import random
from collections import OrderedDict

import numpy as np
import pandas as pd
import pyarrow as pa

_POLARS_INSTALLED = True
try:
    import polars as pl
except:
    _POLARS_INSTALLED = False

################################
# utilities for inspecting data
################################


def row_count(data):
    """
    Return the # of rows/features in the provided data (feature class,
    table, feature layer or table view)

    """
    return int(arcpy.GetCount_management(data).getOutput(0))


def list_flds(data):
    """
    Short hand for listing the field names in a feature class
    or table.

    """
    return [f.name for f in arcpy.ListFields(data)]


def list_fld_types(data):
    """
    Returns a dict of the field types,
    keys are the field names, values the type and
    char length if STRING/TEXT.
    
    """ 
    d = {}
    for f in arcpy.ListFields(data):
        if f.type != 'String':
            d[f.name] = f.type
        else:
            d[f.name] = '{}({})'.format(f.type, f.length)
    return d


def get_oid_fld(data):
    """
    Returns the name of objectid field.

    """
    return arcpy.Describe(data).OIDFieldName


def get_shp_fld(data):
    """
    Returns the name of the shape field. 
    Returns None if not available.

    """
    for f in arcpy.ListFields(data):
        if f.type == 'Geometry':
            return f.name
    return None


##################################
# context managers for controlling 
# arcpy state
##################################


class TempWork():
    """
    Context manager for temporarily changing workspaces. Use this
    for cases where you temporarily want to change the workspace
    within a function and then have it revert back to the original
    workspace upon exiting.

    For example:

    with TempWork(r'c:\temp') as work:
        print arcpy.ListFeeatureClasses()

    Will print the tables in the provided workspace and then
    set the worksapce back when done.

    """

    def __init__(self, workspace=None):
        self.workspace = workspace

    def __enter__(self):
        self.old_workspace = arcpy.env.workspace
        arcpy.env.workspace = self.workspace

    def __exit__(self, *args):
        arcpy.env.workspace = self.old_workspace


class TempOverwrite():
    """
    Context manager for temporarily changing the arcpy ovewrite state.

    """

    def __init__(self, overwrite=True):
        self.overwrite = overwrite

    def __enter__(self):
        self.old_state = arcpy.env.overwriteOutput
        arcpy.env.overwriteOutput = self.overwrite

    def __exit__(self, *args):
        arcpy.env.overwriteOutput = self.old_state


class TempQualifiedFields():
    """
    Context manager for temporarily changing the qualified field names argument

    """

    def __init__(self, qualified=False):
        self.qualified = qualified

    def __enter__(self):
        self.old_state = arcpy.env.qualifiedFieldNames
        arcpy.env.qualifiedFieldNames = self.qualified

    def __exit__(self, *args):
        arcpy.env.qualifiedFieldNames = self.old_state


class CheckoutExtension():
    """
    Context manager for temporarily checking out an ArcGIS extension.
    Will checkout the extension and then check it back in after
    the code is executed.

    For example:

    with CheckoutExtension('spatial') as ce:
        # generate the density surface
        kd = KernelDensity('pnts', None, kd_resolution, kd_resolution, "SQUARE_MILES")

    """

    def __init__(self, name):
        self.extension_name = name

    def __enter__(self):
        arcpy.CheckOutExtension(self.extension_name)

    def __exit__(self, *args):
        arcpy.CheckInExtension(self.extension_name)


class ScratchGdb():
    """
    Context manager for dealing w/ temporary file geodatabase
    files. Given a `with` session, creates the gdb. When leaving
    the session the gdb will be deleted.

    Can also be used outside of `with`, use `del` on an instance
    to clear out the geodatabase.

    Doing this for a couple of reasons:

        1 - ArcPro does weird stuff with the in_memory
        workspace, also the in_memory workspace doesnt work
        with some tools.

        2 - ArcPro does weird stuff with scratch file gdb
        (like rndomly deletes it)

        3 - There are sometimes locking issues when trying
        to write to the same gdb when multiple notebooks are open.


    Example usage:
    --------------
    # example 1: as a context manager
    with ScratchGdb() as scratch:
        out_file = arcpy.CopyFeats(some_fc, scratch.path, 'some_fc_copy')

    # example 2: stand-alone
    scratch = ScratchGdb()
    out_file = arcpy.CopyFeats(some_fc, scratch.path, 'some_fc_copy')
    del scratch

    """

    # scratch workspace/folder location
    scratch_folder = arcpy.env.scratchFolder

    # prefix assigned to all scratch geodatabaes
    gdb_prefix = '__scratch__killme_'

    def __init__(self):
        """
        Create a new file gdb in the ArcGIS scratch folder. Should
        have a unique name.

        """
        work = ScratchGdb.scratch_folder
        existing = [f for f in os.listdir(work) if f.endswith('.gdb')]
        while True:
            gdb_name = '{}{}.gdb'.format(ScratchGdb.gdb_prefix, random.randint(0, 1000))
            if gdb_name not in existing:
                break

        arcpy.CreateFileGDB_management(work, gdb_name)
        self._name = gdb_name
        self._folder = work
        self._path = '{}\\{}'.format(work, gdb_name)

    @property
    def name(self):
        """
        Name of the scratch geodatabase.

        """
        return self._name

    @property
    def folder(self):
        """
        Name of the folder the scratch geodatabase
        resides in.

        """
        return self._folder

    @property
    def path(self):
        """
        Full path to the scratch geodatabase.

        """
        return self._path

    def clear(self):
        """
        Remove the temporary gdb. Produce a warning if the gdb
        could not be deleted (usually because it's locked).

        TODO: look into removing the .lock files?

        """
        try:
            arcpy.Delete_management(self._path)
        except:
            # this seems to be raised in th context manager
            # even when there is no issue deleting?
            # so for now just continue, use list_gdbs and clear_gdbs
            #     methods to clean up remaining stuff later
            #raise Warning(
            #    'Could not remove {} -- check for locks'.format(self._path))
            a = 1

        self._name = None
        self._folder = None
        self._path = None

    def __enter__(self):
        """
        Called when entering a `with` block. Just returns
        a reference to the instance for use w/in the with.

        """
        return self

    def __exit__(self, *args):
        """
        Called when exiting a `with` block. This will
        attempt to remove any temporary/scratch output.

        """
        self.clear()

    def __del__(self):

        """
        Called when using `del` on an instnace. This will
        attempt to remove any temporary/scratch output.

        """
        self.clear()

    @classmethod
    def list_gdbs(cls, full_path=False):
        """
        Returns a list of the names of existing scratch gdbs.

        """
        return [g for g in os.listdir(cls.scratch_folder) if g.startswith(cls.gdb_prefix)]

    @classmethod
    def clear_gdbs(cls):
        """
        Attempt to clear out all existing scratch gdbs. Use this for cases where
        the gdb couldn't be deleted when in use because of locks or something.

        """
        for g in cls.list_gdbs():
            try:
                arcpy.Delete_management('{}\\{}'.format(cls.scratch_folder, g))
            except:
                continue



####################################
# utilities for wrangling data
#####################################


def get_db_conn(server, database, version='sde.DEFAULT'):
    """
    Creates a sde connection in the scratch folder and returns the path
    to `.sde` file.

    Assumes OSA, and a SQL Server database.

    Parameters:
    ------------
    server: str
        Database server/instance
    database: str
        Name of the database

    Returns:
    --------
    string with full path to the `.sde` file

    """
    scratch_work = arcpy.env.scratchFolder
    conn_name = 'temp__{}_{}'.format(server, database)
    conn_path = '{}//{}.sde'.format(scratch_work, conn_name)

    with TempOverwrite():
        arcpy.CreateDatabaseConnection_management(
            scratch_work,
            conn_name,
            database_platform='SQL_SERVER',
            instance=server,
            account_authentication='OPERATING_SYSTEM_AUTH',
            database=database,
            version=version
        )

    return conn_path


def copy_oids(fc, fld_name):
    """
    Copies the OID values into a new field.

    """
    oid_fld = arcpy.Describe(fc).OIDFieldName
    arcpy.AddField_management(fc, fld_name, 'LONG')
    arcpy.CalculateField_management(
        fc, fld_name, '!{}!'.format(oid_fld), 'PYTHON_9.3')


def get_field_map(src, flds, fld_lens={}):
    """
    Returns a field map for an arcpy data itme from a list or dictionary.
    Useful for operations such as renaming columns merging feature classes.

    Parameters:
    -----------
    src: str, arcpy data item or arcpy.mp layer or table
        Source data item containing the desired fields.
    flds: dict <str: str>
        Mapping between old (keys) and new field names (values).

    Returns:
    --------
    arcpy.FieldMappings

    """
    mappings = arcpy.FieldMappings()
    if isinstance(flds, list):
        flds = {n: n for n in flds}

    for old_name, new_name in flds.items():
        fm = arcpy.FieldMap()
        fm.addInputField(src, old_name)
        out_f = fm.outputField
        out_f.name = new_name
        out_f.aliasName = new_name
        if old_name in fld_lens:
            out_f.length = fld_lens[old_name]
        fm.outputField = out_f
        fm.outputField.name = new_name
        mappings.addFieldMap(fm)

    return mappings

def create_layer(layer_name, table, flds=None, where=None, shp_prefix=None):
    """
    Wraps up obtaining a feature layer and handles some of the
    logic for retaining a subset of fields and renaming them.

    **Note in ArcPro the field re-naming doesn't seem to work, 
      so use copy_feats if that is needed**

    Parameters:
    ----------
    layer_name: string
        The name of the layer that will be created.
    table: string
        Full name to feature class (including the workspace).
    flds: dictionary or list, optional, default None
        Dictionary or list of fields to retain.
        If a dictionary the keys are the existing
        names and values are the output names.
    where: string, optional, default None
        Definition query to apply.

    """
    # if list of names provided, convert to dictionary
    if isinstance(flds, list):
        t = {}
        for item in flds:
            t[item] = item
        flds = t

    # add shape fields if desired
    if shp_prefix is not None:
        desc = arcpy.Describe(table)
        if desc.shapeType == "Polygon":
            flds[desc.AreaFieldName] = shp_prefix + '_area'

    # create field definitions
    fi = arcpy.FieldInfo()
    for fld in arcpy.ListFields(table):
        fld_name = fld.name
        if flds is None:
            fi.addField(fld_name, fld_name, 'VISIBLE', '')
        else:
            value = flds.get(fld_name, None)
            if value is not None:
                fi.addField(fld_name, value, 'VISIBLE', '')
            else:
                fi.addField(fld_name, fld_name, 'HIDDEN', '')

    # create the feature layer
    if where is None:
        arcpy.MakeFeatureLayer_management(table, layer_name, field_info=fi)
    else:
        arcpy.MakeFeatureLayer_management(table, layer_name, where, field_info=fi)


def copy_feats(data, out_work, out_fc, flds=None, where=None, fld_lens={}):
    """
    Copies features into a new feature class.

    Parameters:
    -----------
    data: str or feature layer
        Data to copy out. If the data is a layer will respect
        defintion query and/or selection set.
    out_work: str
        Output workspace to top to.
    out_fc: str
        Name of the new feature class.
    flds: list or dict <str: str>, optional default None
        Fields to copy. If dict is provided fields will
        be-renamed.
    where: str, optional default None
        Optional query to apply.

    Returns:
    -------
    str of full path to the created feature class.

    TODO:
    -----
    When working w/in pro, seems to put in aprx.defaultGeodatabse
    when specifying in_memory as the output workspace, also will
    rename the feauture class if it already exists, not sure how
    to overwrite. If running outside ArcPro then behavior is as
    expected.

    """
    field_map = None
    if flds is not None:
        field_map = get_field_map(data, flds, fld_lens)

    return arcpy.FeatureClassToFeatureClass_conversion(
        data,
        out_work,
        out_fc,
        where,
        field_map
    )


def get_centroids(polys, out_gdb, out_fc, flds_to_keep=None):
    """
    Generates centroids, this will be the 'natural' centroid when it falls within 
    the polygon and a point somewhere inside the polygon if not. For some reason this is way
    faster than arcpy.management.FeatureToPoint.

    The orignal OID/OBJECTID values will be stored in the column `src_<OBJECTID ID COLUMN NAME>`

    Parameters:
    -----------
    polys: str
        Full path to the feature class.
    out_gdb: str
        Full path to the output feature class.
    out_fc: str
        Name of the ouput feature class
    flds_to_keep: str or list of str, default None
        List of fields to retain in the output.
        If not provided all columns except Shape related will be retained.

    Returns:
    --------
        Full path to the output featuere class.

    """
    # manage fields
    d = arcpy.Describe(polys)
    srs = d.spatialReference
    shp_col = d.shapeFieldName
    oid_col = d.oidFieldName

    if flds_to_keep is None:
        flds_to_keep = [f for f in list_flds(polys) if f not in [shp_col, oid_col, 'Shape_Length', 'Shape_Area']]
    else:
        if not isinstance(flds_to_keep, list):
            flds_to_keep=[flds_to_keep]
    
    # get centroids
    res = {}
    cursor = arcpy.da.SearchCursor(polys, [oid_col, '{}@'.format(shp_col)] + flds_to_keep)    
    for feat in cursor:
        curr_oid = feat[0]
        curr_shp = feat[1]
        centroid = curr_shp.centroid
        res[curr_oid] = [centroid.X, centroid.Y] + list(feat[2:])

    # build the dataframe
    df = pd.DataFrame.from_dict(res, orient='index', columns=['x', 'y'] + flds_to_keep)
    df.index.name = 'src_{}'.format(oid_col)
    for col in df.columns:
        if str(df[col].dtype) == 'object':
            df[col] = df[col].fillna('')

    # send back to arc
    out = '{}//{}'.format(out_gdb, out_fc)
    pandas_to_arc(
        df,
        out_gdb,
        out_fc,
        x_col='x', y_col='y', srs=srs
    )
    return out


def add_ap_ratio(data, fld_name='ap_ratio'):
    """
    Adds and calculated an area-perimter ratio field. The ratio is based on
    comparing the length to that of a circle w/ the same area.

    Parameters:
    -----------
    data: str
        Full path to the feature class (must be polygons).
    fld_name str, optional, default `ap_ratio`
        Name for the field to add.


    """
    arcpy.AddField_management(data, fld_name, 'DOUBLE')
    arcpy.CalculateField_management(
        data,
        fld_name,
        'Length($feature) / (2 * Sqrt(3.14159265 * Area($feature)))',
        'ARCADE'
    )


#####################
# pandas integration
#####################


def arc_to_pandas(workspace_path, class_name, index_fld=None, flds=None, spatial=True, where=None,
                  fill_nulls=True, str_fill='', num_fill=-1, date_fill='1678-01-01'):
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
    date_fill: str, default '1678-01-01'
        Value to fill date/time columns.

    Returns
    -------
    pandas.DataFrame

    Notes:
        1 - If exporting a feature layer or table view, this will currently
            support views that have fields that are not visivble, BUT will
            NOT support views with fields that have been re-named.

    """
    # build full path to the class/table
    if workspace_path is not None and workspace_path != '':
        class_name = '{}//{}'.format(workspace_path, class_name)

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

    # need to handle bad datetimes
    arr_flds = arr.dtype.fields
    date_flds = [k for k, v in arr_flds.items() if v[0] == np.dtype('<M8[us]')]
    # note was previously using pandas built-ins, but these have issues
    # ...with some datasets so hard code those timestamps here 
    #min_date = pd.Timestamp.min  -- Timestamp('1677-09-21 00:12:43.145224193')
    #max_date = pd.Timestamp.max  -- Timestamp('2262-04-11 23:47:16.854775807')
    min_date = np.datetime64('1677-09-22')
    max_date = np.datetime64('2262-04-12')
    
    for f in date_flds:
        # convert to datetime in pandas, use 'coerce' to eliminate bad values
        date_ts = pd.to_datetime(arr[f], errors='coerce')
        # assign back to array
        arr[f] = date_ts.values

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
    # TODO: look possible make this the defaualt and
    # use more distinct null values
    if not fill_nulls:
        # note: need separate calls or it seems to change data types
        df.replace(num_fill, np.nan, inplace=True)
        df.replace([str_fill, 'nan'], np.nan, inplace=True)
        df.replace(pd.Timestamp(date_fill), np.nan, inplace=True)

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
        if arr.dtype == object:
            arr = arr.astype(str)
        if arr.dtype == np.int64:
            max_val = arr.max()
            min_val = arr.min()
            if min_val < -2147483647 or max_val > 2147483647:
                arr = arr.astype(np.float64)
            else:
                arr = arr.astype(np.int32)
        if arr.dtype == bool:
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
    with TempWork(workspace_path):

        if overwrite:
            if arcpy.Exists(output_table):
                arcpy.Delete_management(output_table)

        # convert the array to a ArcGIS table or feature class
        # note: these numpy gp tools have pretty specific path requirement
        out_path = '{}/{}'.format(workspace_path, output_table)
        if x_col is not None and y_col is not None:
            arcpy.da.NumPyArrayToFeatureClass(
                s_arr, out_path, [x_col, y_col], srs)
        else:
            arcpy.da.NumPyArrayToTable(s_arr, out_path)

        # id desired, return a cursor with the results
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
    return out_flds, rows


def pandas_to_features(df, fc, pd_id_fld, arc_id_fld, out_fc, keep_common=True):
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
    keep_common: bool, optional, default True
        If True, only joined features will be retained.
        IF False, all features will be retained.

    """
    with ScratchGdb() as scratch:

        with TempWork(scratch.path):
            temp_pd_name = '__pd_temp'
            temp_arc_name = '__polys_temp'

            # output the pandas table to a scratch workspace and add an attribute index
            pandas_to_arc(df, scratch.path, temp_pd_name, overwrite=True)
            arcpy.AddIndex_management(temp_pd_name, pd_id_fld, pd_id_fld)

            # do the join and export
            create_layer(temp_arc_name, fc)

            if keep_common:
                join_type='KEEP_COMMON'
            else:
                join_type='KEEP_ALL'

            arcpy.AddJoin_management(
                temp_arc_name,
                arc_id_fld,
                temp_pd_name,
                pd_id_fld,
                join_type
            )
            with TempQualifiedFields(False):
                arcpy.CopyFeatures_management(temp_arc_name, out_fc)

            # tidy up
            arcpy.Delete_management(temp_pd_name)
            arcpy.Delete_management(temp_arc_name)


def arc_to_pandas_a(data, flds=None, geometry_encoding=None) -> pd.DataFrame:
    """
    Returns a pandas.DataFrame for an ESRI feature
    class or table -- using Apache Arrow instead of numpy.

    The panadas dataframe will have arrow dtypes. 

    Parameters:
    -----------
    data: str
        Full path to the data
    flds: list or dict, optional, defualt None
        Fields to pull.
        ...If dict, keys are field names, values new names
        ...If list, the matching case will match.   
    geometry_encoding: str, optional default None
        The geometry encoding to use.
            None: shape/geometry columns will not be pulled
            `ESRISHAPE`: Native binary geometry encoding
            `ESRIJSON`: Native JSON format geometry encoding
            `GEOJSON`: Open standard JSON format geometry encoding
            `WKT`: known text (WKT) geometry encoding
            `WKB`: known binary (WKB) geometry encoding
        
    Returns:
    --------
    pandas.DataFrame

    """
    return (
        arc_to_polars(data, flds, geometry_encoding)
        .to_pandas(use_pyarrow_extension_array=True)
    )


def arc_to_polars(data, flds=None, geometry_encoding=None) -> pl.DataFrame:
    """
    Returns a polars.DataFrame for an ESRI feature
    class or table.

    Parameters:
    -----------
    data: str
        Full path to the data
    flds: list or dict, optional, defualt None
        Fields to pull.
        ...If dict, keys are field names, values new names
        ...If list, the matching case will match.   
    geometry_encoding: str, optional default None
        The geometry encoding to use.
            None: shape/geometry columns will not be pulled
            `ESRISHAPE`: Native binary geometry encoding
            `ESRIJSON`: Native JSON format geometry encoding
            `GEOJSON`: Open standard JSON format geometry encoding
            `WKT`: known text (WKT) geometry encoding
            `WKB`: known binary (WKB) geometry encoding
    Returns:
    --------
    polars.DataFrame

    """
    if not _POLARS_INSTALLED:
        raise ImportError('Must have polars installed: pip install polars')

    # so we don't pull the shape field when no fields are specified
    if flds is None and geometry_encoding is None:
        shp_fld = get_shp_fld(data)
        if shp_fld is not None:
            flds = [f for f in list_flds(data) if f != shp_fld]

    # column names to pull
    names = flds
    if isinstance(flds, dict):
        names = list(flds.keys())

    # get the data from via arrow
    df =  pl.from_arrow(arcpy.da.TableToArrowTable(data, names, geometry_encoding=geometry_encoding))

    # re-name as needed
    # ...match the requested case, regardless of what was in the data
    if flds is not None:
        df_cols = df.columns    
        df_cols_lower = {c.lower(): c for c in df_cols}
   
        if isinstance(flds, list):
            names_lower = {n.lower(): n for n in names}
            new_names = {df_cols_lower[k]: v for k, v in names_lower.items() if v not in df.columns}

        if isinstance(flds, dict):
            new_names = {(k if k in df_cols else df_cols_lower[k.lower()]): v for k, v in flds.items()}

        if len(new_names) > 0:
            df = df.rename(new_names)

    return df


def polars_to_arc(df, out_work, out_cls, geo_col=None, srs=None, geometry_encoding='EsriShape'):
    """
    Export a polars.DataFrame to an ArcGIS feature class or table. 
    
    Parameters:
    -----------
    df: polars.DataFrame
        Data to export
    out_work: str
        Full path to output workspace/gdb
    out_cls: str
        Name of the output table/feature class
    geo_col: str, optional, default None
        Name of the column to use for geometry,
        omit if just exporting a table.
    srs: arcpy.SpatialReference, optional, default None
        Spatial reference for the geometry columns.
        Required if exporting a geometry column.
    geometry_encoding: str, optional default `EsriShape`
        Type of geometry encoding, valid values:
            `EsriShape`:  Native binary geometry encoding
            `EsriJSON`: Native JSON format geometry encoding
            `GeoJSON`: Open standard JSON format geometry encoding
            `WKB`: known text (WKT) geometry encoding
            `WKT`: known binary (WKB) geometry encoding

    Returns:
    --------
    str: full path to the results. 

    """
    # convert from polars to arrow
    arr = df.to_arrow()

    # update schema and types as needed
    new_schema = []
    for f in arr.schema:
        
        f_name = f.name
        f_type = f.type
        f_metadata = None
    
        # need to convert large string to string
        if f.type == pa.large_string():
            f_type = pa.string()

        # need to convert large binary to binary
        if f.type == pa.large_binary():
            f_type = pa.binary()
    
        # handle metadata for geometry/shape field
        if f_name.lower() == geo_col.lower():
            f_metadata = {
                'esri.encoding': geometry_encoding,
                'esri.sr_wkt': srs.exportToString(),
            }

        # update the schema 
        new_schema.append(pa.field(f_name, f_type, metadata=f_metadata))

    # re-cast everything and export to arc
    arr2 = arr.cast(pa.schema(new_schema))

    if geo_col is not None:
        return arcpy.management.CopyFeatures(arr2, '{}//{}'.format(out_work, out_cls))
    else:
        return arcpy.managment.CopyRows(arr2, '{}//{}'.format(out_work, out_cls))
    
    
#####################
# deprecated methods
#####################


def create_new_feature_class(in_fc, out_fc, flds=None, where=None, shp_prefix=None):
    raise DeprecationWarning("***DEPRECATED -- see `copy_feats` method***")


def create_new_feature_class2(in_fc, out_gdb, out_fc, flds=None, where=None):
    raise DeprecationWarning("***DEPRECATED -- see `copy_feats` method***")


def pandas_join_to_arc(df,
                       join_to,
                       pandas_on,
                       arc_on,
                       output=None,
                       keep_index=True,
                       pandas_cols=None,
                       arc_cols=None):
    raise DeprecationWarning("***DEPRECATED -- see `pandas_to_features` method***")
