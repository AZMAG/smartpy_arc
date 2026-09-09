"""
Testing some new methods for integrating ESRI/arcpy with data frame libraries.

"""
import os
from collections.abc import Iterator
from typing import Any, Literal

import arcpy
import pandas as pd
import polars as pl
from polars.io.plugins import register_io_source


def get_cased_field_name_mapping(arc_flds: list[str], 
                                 out_flds: list[str] | dict[str, str],
                                 strict: bool = True) -> dict[str, str]:
    """
    Extracts and maps the field names in the underlying arc data to the desired output names,
    matching their case.  

    Parameters:
    -----------
    arc_flds: list[str]
        List of available input field names.
    out_flds: list[str] or dict[str, str]
        List of desired output fields names.
        Or dict keyed by the desired ouput names.
    strict: bool, optional, default True
        If True, will raise an error reporting any missing fields.
        If False, missing fields will simply be omitted from the output.    
    
    Returns:
    --------
    dict[str, str]
    ...keys are original arc fields
    ...values are the subset of output fields, with their specified casing

    """
    mapping = {}
    missing = []

    lookup = {f.casefold(): f for f in arc_flds}
    for f in out_flds:
        match =  lookup.get(f.casefold())
        if match is None:
            missing.append(f)
        else:
            mapping[match] = f

    if strict and missing:
        raise ValueError(f'missing fields: {missing}')
    return mapping


# maps between polars and arc datatypes
ARCPY_TO_POLARS_DTYPES = {
    'String': pl.String,
    'Blob': pl.Binary,
    'SmallInteger': pl.Int16,
    'Integer': pl.Int32,
    'BigInteger': pl.Int64,
    'OID': pl.Int64,
    'Single': pl.Float32,
    'Double': pl.Float64,
    'Date': pl.Datetime,
    'DateOnly': pl.Date,
    'TimeOnly': pl.Time,
    'TimestampOffset': pl.Datetime,
    'Guid': pl.String,
    'GlobalID': pl.String,
    'Object': pl.Object,
}


class ArcSchema:
    """
    Used to describe the attributes and spatial properties of an Arc/ESRI dataset 
    and map these to a set of desired ouput fields.
    
    """
    def __init__(self, src_data: str) -> None:
        self.src_data = src_data

        # available fields and data types
        d = arcpy.Describe(src_data)
        class_type = d.dataType
        shape_type = None
        srs = None
        shape_fld = ''

        # available fields and data types
        src_schema = {f.name: f.type for f in d.Fields}
        #src_schema['@OID'] = 'OID'

        if class_type in ["FeatureClass", "FeatureLayer"]:
            shape_type = d.shapeType
            shape_fld = d.shapeFieldName
            srs = d.spatialReference

            src_schema['SHAPE@X'] = 'Double'
            src_schema['SHAPE@Y'] = 'Double'
            src_schema['SHAPE@WKB'] = 'Object'
        
        if shape_type == 'Polygon':
            src_schema['SHAPE@AREA'] = 'Double'
        if shape_type in ['Polygon', 'Polyline']:
            src_schema['SHAPE@LENGTH'] = 'Double'

        del d
        self.class_type = class_type
        self.shape_type = shape_type
        self.shape_fld = shape_fld
        self.srs = srs
        self.src_schema = src_schema
        self.src_flds = list(src_schema.keys())

    def resolve_schema(self, 
                       flds: list[str] | dict[str, str] | None = None, 
                       strict: bool = True) -> tuple[list[str], dict[str, Any], str | None]:
        """
        Resolves the schema against the provided output fields.

        Parameters:
        -----------
        flds: list or dict, optional, default None
            Fields to resolve. 
            If None - use all the fields with their existing names.
            If list - get subset of fields, can re-case.
            If dict - get subset of fields and re-name.
        strict: bool, optional, default True
            If True, an error will be raised ina field is not found.
            Otherwise the field will be ommitted from the results.
        
        Returns:
        --------
        cursor: list[str]
            List of field names to send to arcpay.da.SearchCursor
        polars_scheme: dict[str, Any]
            Dict of output polars schema, keys are field names
            values are corresponding polars dtypes.
        out_shape_fld: str
            Name of the output shape/geometry column. 
            None if not present.

        """
        # resolve casing
        if flds is None:
            case_fld_map = {f: f for f in self.src_flds}
        else:
            case_fld_map = get_cased_field_name_mapping(self.src_flds, flds, strict)

        # handle shape/geometry naming
        if self.shape_fld in case_fld_map:
            case_fld_map['SHAPE@WKB'] = case_fld_map.pop(self.shape_fld)

        # fields to be sent to the cursor
        cursor_flds = list(case_fld_map.keys())
        out_shape_fld = case_fld_map.get('SHAPE@WKB')

        # final polars schema
        # ...keys are final ouput columns
        # ...values are data types
        polars_schema = {case_fld_map[k]: ARCPY_TO_POLARS_DTYPES[self.src_schema[k]] for k in case_fld_map}
        if isinstance(flds, dict):
            polars_schema = {flds[k]: v for k, v in polars_schema.items()}
            if out_shape_fld is not None: 
                out_shape_fld = flds.get(out_shape_fld)

        return cursor_flds, polars_schema, out_shape_fld
      

def scan_arc(data: str,
             flds: list[str] | dict[str, str] | None = None,
             where: str | None = None,
             strict: bool = True) -> pl.LazyFrame:
    """
    Polars scan method for arc/esri datasets.

    Parameters:
    -----------
    data: str
        Full path to the geodatabase feature class or table.
    flds: list or dict, optional, default None
        Fields to pull.
        If None - pull all fields.
        If list - pull a subset of fields, can re-case.
        If dict - get subset of fields and re-name.
    where: str, optional, default None
        Optional definition query to apply.
    strict: bool, optional, default True
         If True, an error will be raised ina field is not found.
         Otherwise the field will be ommitted from the results.

    Returns:
    --------
    pl.LazyFrame

    Sample usage:
    -------------
    my_dataset = some_path
    
    # case 1 - pull all fields
    my_lf = scan_arc(my_dataset)

    # case 2 - pull subset of fields
    # ...shape field will be pulled in binary column
    mylf2 = scan_arc(
        my_dataset,
        flds=['col1', 'Shape', 'SHAPE@AREA']
    )

    # case 3 - pull subset and rename
    my_lf3 = scan_arc(
        my_dataset,
        flds={
            'col1':       'my_fun_col',
            'Shape':      'geo_col,
            'SHAPE@X:     'x_col',
            'SHAPE@Y:     'y_col',
            'SHAPE@AREA': 'area_col'
        }
    )
     
    """
    # get the schema
    arc_schema = ArcSchema(data)
    cursor_flds, polars_schema, shp_fld = arc_schema.resolve_schema(flds, strict)

    # define the generator
    def arc_generator(with_columns: list[str] | None,
                      predicate: pl.Expr | None,
                      n_rows: int | None,
                      batch_size: int | None) -> Iterator[pl.DataFrame]:

        with arcpy.da.SearchCursor(data, cursor_flds, where_clause=where) as cursor:
            rows = []
            batch_count = 0

            def get_df():
                # construct
                df = pl.DataFrame(rows, schema=polars_schema, orient='row')

                # convert shp from bytearry to bytes
                if shp_fld is not None:
                    df = df.with_columns(
                        **{shp_fld:pl.col(shp_fld).map_elements(bytes, return_dtype=pl.Binary)}
                    )
                # apply and predicate/filters
                # # TODO: need to fix this so more generic
                if predicate is not None:
                    df = df.filter(predicate)

                # apply any additional column projection
                if with_columns is not None:
                    df = df.select(with_columns)

                return df

            for i, row in enumerate(cursor):
                if n_rows is not None and i >= n_rows:
                    yield get_df()
                    return
                else:
                    if batch_size and batch_count >= batch_size:
                        yield get_df()
                        rows = []
                        batch_count = 0
                    rows.append(row)
                    batch_count += 1
            if rows:
                yield get_df()

    # register the generator
    return register_io_source(io_source=arc_generator, schema=polars_schema)


# default spatial reference
# ...az state plane central nad83 harn
DEFAULT_SRS = arcpy.SpatialReference(2868)


# data type lookup from polars to arc
# ...right now not using BIGINTEGER because it seems to break 
# ...various arc tools - use DOUBLE for now but revisit this
PL_TO_ARC_DTYPES = {
    pl.Int8:        "SHORT",
    pl.Int16:       "SHORT",
    pl.Int32:       "LONG",
    pl.Int64:       "DOUBLE", # could be BIGINTEGER but use double for now
    pl.UInt8:       "SHORT",
    pl.UInt16:      "LONG",
    pl.UInt32:      "DOUBLE", # could be BIGINTEGER but use double for now
    pl.UInt64:      "DOUBLE", # could be BIGINTEGER but use double for now
    pl.Float32:     "FLOAT",
    pl.Float64:     "DOUBLE",
    pl.Decimal:     "DOUBLE",
    pl.String:      "TEXT",
    pl.Categorical: "TEXT",
    pl.Date:        "DATE",
    pl.Datetime:    "DATE",
}


def get_clean_name(orig_name: str, replace_char: str = '_') -> str:
    """
    Return a clean name suitable for field names.

    Pameters:
    ---------
    orig_name: str
        Original name.
    replace_char: str, optional, default `_`
        Char to replace bad chars with.

    Returns:
    --------
    str 

    """
    bad_chars = [
            ' ', '.', '+', "-", '@',
            "/", "\\", ")", "(", "*", "&", "'", ","
    ]
    clean_name = orig_name.strip()
    for char in bad_chars:
        clean_name = clean_name.replace(char, replace_char)

    # remove duplicate space
    while (replace_char * 2) in clean_name:
        clean_name = clean_name.replace(replace_char * 2, replace_char)

    return clean_name.strip()


def _add_fields(df: pl.DataFrame,
                out_cls: str | os.PathLike[str]) -> tuple[list[str], list[str]]:
    """
    Adds fields to an existing feature class or stand-alone 
    table to match the provided data frame schema.

    Parameters:
    -----------
    df: polars.DataFrame
        Data frame with the schema to apply.
    out_cls: str
        Full path to an existing feature class or 
        stand-alone table.

    Returns:
    --------
    tuple[list[str], list[str]]
    ...first item is list of output field names
    ...second item is corresponding df column names

    """
    d = arcpy.Describe(out_cls)
    class_type = d.dataType
    out_oid_fld = d.oidFieldName
    out_shp_fld = None

    if class_type == 'FeatureClass':
        out_shp_fld = d.shapeFieldName

    out_flds = []
    df_flds = []
    
    for fld, dt in df.schema.items():
        # don't add fields for objectid/shape
        if fld == out_shp_fld or fld.lower().startswith('shape@'):
            continue
        if fld.lower() == out_oid_fld.lower():
            print('ignoring df column `{}`, used as OID in output'.format(fld))
            continue
        
            # get the corresponding arc data type
        arc_dt = PL_TO_ARC_DTYPES.get(dt.base_type())
        if arc_dt is None:
            print('ignoring df column `{}`, datatype `{}` not found'.format(fld, dt))
            continue
        
        # get clean field if needed
        clean_fld = get_clean_name(fld)
        if  fld != clean_fld:
            print('field `{}` renamed to `{}`'.format(fld, clean_fld))

        # add it
        if dt == pl.String:
            max_char_len = df.select(pl.col(fld).str.len_chars().max()).item()
            out_flds.append([clean_fld, arc_dt, clean_fld, max_char_len])
        else:
            out_flds.append([clean_fld, arc_dt, clean_fld])
        df_flds.append(fld)

    arcpy.management.AddFields(out_cls, out_flds)
    return [f[0] for f in out_flds], df_flds


def polars_to_fc(df: pl.DataFrame,
                 out_work: str,
                 out_fc: str,
                 geo_col: str,
                 geo_type: Literal['POINT', 'MULTIPOINT', 'POLYGON', 'POLYLINE'],
                 srs: arcpy.SpatialReference = DEFAULT_SRS) -> str | os.PathLike:
    """
    Exports a polars data frame w/ a geometry/spatial column to a feature class.
    ** Assumes the geometry is in WKB. **

    Parameters:
    -----------
    df: polars.DataFrame
        Data frame to export.
    out_work: str 
        Full path to the output gdb/workspace.
    out_fc: str
        Name of the output feature class.
    geo_col: str
        Name of column containing geometry.
        Column type should be pl.Binary.
        Geometry should be in `WKB` format.
    geo_type: str
        Geometry type, should be 'POINT', 'POLYLINE', 'POLYGON'
        or 'MULTIPOINT'.
    srs: arcpy.SpatialReference, optional
        Output spatial reference. If not provided
        module-level `DEFAULT_SRS` will be used.
        (State Plane AZ Central NAD83 HARN)

    Returns:
    --------
    str: 
        Full path to resulting feature class.

    """
    # create the oputput feature class
    new_fc = arcpy.management.CreateFeatureclass(
        out_work,
        out_fc,
        geometry_type=geo_type,
        spatial_reference=srs
    )[0]

    # add fields
    out_flds, df_flds = _add_fields(df, new_fc)
    out_flds += ['SHAPE@WKB']
    df_flds += [geo_col]

    # do the inserts
    with arcpy.da.InsertCursor(new_fc, out_flds) as cursor:
        for row in df.select(df_flds).iter_rows():
            cursor.insertRow(row)

    # return back the full path to the result
    return new_fc


def polars_to_arc_table(df: pl.DataFrame,
                        out_work: str,
                        out_table: str) -> str | os.PathLike:
    """
    Exports a polars data frame to an Arc/ESRI table. Only 
    non-spatial and non-binary columns will be in the result.

    Parameters:
    -----------
    df: polars.DataFrame
        Data frame to export.
    out_work: str 
        Full path to the output gdb/workspace.
    out_table: str
        Name of the output table.

    Returns:
    --------
    str: 
        Full path to resulting table.

    """
    # create the output table
    new_tab = arcpy.management.CreateTable(out_work, out_table)[0]

    # add the fields
    out_flds, df_flds = _add_fields(df, new_tab)

    # do the inserts
    with arcpy.da.InsertCursor(new_tab, out_flds) as cursor:
        for row in df.select(df_flds).iter_rows():
            cursor.insertRow(row)

    # return back the full path to the result
    return new_tab


def polars_xy_to_fc(df: pl.DataFrame,
                    out_work: str, 
                    out_fc: str, 
                    x_col: str,
                    y_col: str,
                    srs: arcpy.SpatialReference = DEFAULT_SRS) -> str | os.PathLike:
    """
    Export a polars data frame with x,y cols into an Arc/ESRI point feature class.

    Parameters:
    -----------
    df: polars.DataFrame
        Data frame to export.
    out_work: str 
        Full path to the output gdb/workspace.
    out_fc: str
        Name of the output feature class.
    x_col: str
        Name of column containing x values.
    y_col: str
        Name of column containing y values.
    srs: arcpy.SpatialReference, optional
        Output spatial reference. If not provided
        module-level `DEFAULT_SRS` will be used.
        (State Plane AZ Central NAD83 HARN)

    Returns:
    --------
    str: 
        Full path to resulting feature class.

    """
    # create the oputput feature class
    new_fc = arcpy.management.CreateFeatureclass(
        out_work,
        out_fc,
        geometry_type='POINT',
        spatial_reference=srs
    )[0]
    
    # add the fields
    out_flds, df_flds = _add_fields(df, new_fc)
    out_flds += ['SHAPE@XY']
    df_flds_kw = {'_xy': pl.concat_list(x_col, y_col)}

    # do the inserts
    with arcpy.da.InsertCursor(new_fc, out_flds) as cursor:
            for row in df.select(*df_flds, **df_flds_kw).iter_rows():
                cursor.insertRow(row)

    # return back the full the path to the result
    return new_fc


########################################
# PANDAS WRAPPERS
# ...underlying logic is still polars,
# ...but provide easy pandas access
########################################


def arc_to_pandas2(data: str,
                   flds: list[str] | dict[str, str] | None = None,
                   where: str | None = None,
                   index_fld: str | list[str] | None = None,
                   strict: bool = True, 
                   use_pyarrow=False) -> pd.DataFrame:
    """
    Updated method for importing ESRI feature class or table to pandas.
    **This method will automatically load geometry and SHAPE@ columns.**
    Use the `flds` arg to ommit these.

    Parameters:
    -----------
    data: str
        Full path to the geodatabase feature class or table.
    flds: list or dict, optional, default None
        Fields to pull.
        If None - pull all fields.
        If list - pull a subset of fields, can re-case.
        If dict - get subset of fields and re-name.
    where: str, optional, default None
        Optional definition query to apply.
    index_fld: str or list[str], optional, default None
        Optionally prescribes columns to serve as index.
    strict: bool, optional, default True
         If True, an error will be raised ina field is not found.
         Otherwise the field will be ommitted from the results.
    use_pyarrow: bool optional, default False
        Whether or not to use polars/pyarrow dtypes.
        If True, allows faster conversion between polars/pandas.

    Returns:
    --------
    pandas.DataFrame

    """
    df = (
        scan_arc(data, flds, where, strict)
        .collect()
        .to_pandas(use_pyarrow_extension_array=use_pyarrow)
    )
    if index_fld is not None:
        df = df.set_index(index_fld, drop=True)
    return df


def pandas_to_fc(df: pd.DataFrame,
                 out_work: str,
                 out_fc: str,
                 geo_col: str,
                 geo_type: Literal['POINT', 'MULTIPOINT', 'POLYGON', 'POLYLINE'],
                 include_index: bool = True,
                 srs: arcpy.SpatialReference = DEFAULT_SRS) -> str | os.PathLike:
    """
    Exports pandas data frame w/ a geometry/spatial column to a feature class.
    ** Assumes the geometry is in WKB. **

    Parameters:
    -----------
    df: pandas.DataFrame
        Data frame to export.
    out_work: str 
        Full path to the output gdb/workspace.
    out_fc: str
        Name of the output feature class.
    geo_col: str
        Name of column containing geometry.
        Column type should be pl.Binary.
        Geometry should be in `WKB` format.
    geo_type: str
        Geometry type, should be 'POINT', 'POLYLINE', 'POLYGON'
        or 'MULTIPOINT'.
    include_index: bool, optional default True
        Include index as column(s) if True.
    srs: arcpy.SpatialReference, optional
        Output spatial reference. If not provided
        module-level `DEFAULT_SRS` will be used.
        (State Plane AZ Central NAD83 HARN)

    Returns:
    --------
    str: 
        Full path to resulting feature class.

    """
    return polars_to_fc(
        pl.from_pandas(df, include_index=include_index),
        out_work,
        out_fc,
        geo_col,
        geo_type,
        srs
    )


def pandas_to_arc_table(df: pd.DataFrame,
                        out_work: str,
                        out_table: str,
                        include_index: bool = True) -> str | os.PathLike:
    """
    Exports a pandas data frame to an Arc/ESRI table. Only 
    non-spatial and non-binary columns will be in the result.

    Parameters:
    -----------
    df: pandas.DataFrame
        Data frame to export.
    out_work: str 
        Full path to the output gdb/workspace.
    out_table: str
        Name of the output table.
    include_index: bool, optional default True
        Include index as column(s) if True.
        
    Returns:
    --------
    str: 
        Full path to resulting table.

    """
    return polars_to_arc_table(
        pl.from_pandas(df, include_index=include_index),
        out_work,
        out_table
    )
