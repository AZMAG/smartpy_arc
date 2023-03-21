"""

This modules contains functions that make it easier to work
ESRI data objects.

"""
import os
import random
import arcpy


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


def get_oid_fld(data):
    """
    Returns the name of objectid field.

    """
    return arcpy.Describe(data).OIDFieldName


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
            df[col].fillna('', inplace=True)

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
# deprecated methods
#####################


def create_new_feature_class(in_fc, out_fc, flds=None, where=None, shp_prefix=None):
    raise DeprecationWarning("***DEPRECATED -- see `copy_feats` method***")


def create_new_feature_class2(in_fc, out_gdb, out_fc, flds=None, where=None):
    raise DeprecationWarning("***DEPRECATED -- see `copy_feats` method***")
