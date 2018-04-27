"""

This modules contains functions that make it easier to work
ESRI data objects.

"""
import arcpy


def row_count(data):
    """
    Return the # of rows/features in the provided data (feature class,
    table, feature layer or table view)

    """
    return int(arcpy.GetCount_management(data).getOutput(0))


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


def list_fields(fc):
    """
    Returns the field names in a feature class or table.

    """
    return [f.name for f in arcpy.ListFields(fc)]


def copy_oids(fc, fld_name):
    """
    Copies the OID values into a new field.

    """
    oid_fld = arcpy.Describe(fc).OIDFieldName
    arcpy.AddField_management(fc, fld_name, 'LONG')
    arcpy.CalculateField_management(
        fc, fld_name, '!{}!'.format(oid_fld), 'PYTHON_9.3')


def create_layer(layer_name, table, flds=None, where=None, shp_prefix=None):
    """
    Wraps up obtaining a feature layer and handles some of the
    logic for retaining a subset of fields and renaming them.

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


def create_new_feature_class(in_fc, out_fc, flds=None, where=None, shp_prefix=None):
    """
    Basically a shortcut to get a feature class with different fields
    and optionally a where condition.

    TODO: add something to wrap up doing joins?

    Parameters:
    -----------
    in_fc: string
        Path to the input feature class.
    out_fc: string
        Path to the output feature class.
    flds: dictionary, optional, default None
        Dictionary of fields to retain, the keys are the existing
        names and values are the output names.
    where: string, optional, defualt None
        Definition query to apply.

    """
    create_layer('__killme', in_fc, flds, where, shp_prefix)
    arcpy.CopyFeatures_management('__killme', out_fc)
    arcpy.Delete_management('__killme')

    # at 10.3 field aliases persist, so set these to match the field name
    for f in arcpy.ListFields(out_fc):
        if f.name != f.aliasName:
            arcpy.AlterField_management(out_fc, f.name, new_field_alias=f.name)


def get_db_conn(server, database):
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
            database=database
        )

    return conn_path
