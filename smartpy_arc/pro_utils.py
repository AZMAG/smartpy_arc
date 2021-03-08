"""
Utility functions for working w/ ArcGIS pro environment and
libraries. Eventually start to deprecate the
arc_pandas and arc_utils libraties in lieu of this.

"""
import os
import random
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


def get_field_map(src, flds):
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
        fm.outputField = out_f
        fm.outputField.name = new_name
        mappings.addFieldMap(fm)

    return mappings


def copy_feats(data, out_work, out_fc, flds=None, where=None):
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
        field_map = get_field_map(data, flds)

    return arcpy.FeatureClassToFeatureClass_conversion(
        data,
        out_work,
        out_fc,
        where,
        field_map
    )


def row_count(data):
    """
    Return the # of rows/features in the provided data (feature class,
    table, feature layer or table view)

    """
    return int(arcpy.GetCount_management(data).getOutput(0))


def list_flds(data):
    """
    Short hand for listing the field names in a featue class
    or table.

    """
    return [f.name for f in arcpy.ListFields(data)]


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
