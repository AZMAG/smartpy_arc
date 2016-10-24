"""

This modules contains functions that make it easier to work
ESRI data objects.

"""
import arcpy


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
    create_layer('killme', in_fc,  flds, where, shp_prefix)
    arcpy.CopyFeatures_management('killme', out_fc)
    arcpy.Delete_management('killme')

    # at 10.3 field aliases persist, so set these to match the field name
    for f in arcpy.ListFields(out_fc):
        if f.name != f.aliasName:
            arcpy.AlterField_management(out_fc, f.name, f.name, f.name)

