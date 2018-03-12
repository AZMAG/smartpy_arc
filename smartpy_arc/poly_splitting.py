"""
Contains methods for splitting and tessellating polygons.
Used primarily for parcelizing large areas.

"""
from __future__ import division, print_function

import math
import random
import arcpy


def split_poly(poly, target_area, search_tolerance=0.005):
    """
    Splits a polygon into 2 features: a left side and right side
    based on the desired area of the left polygon.

    Parameters:
    ----------
    poly: arcpy.Polygon
        The target polygon to split.
    target_area:
        The desired area of the left side of the split.
    search_tolerance: optional, default .005
        Ratio defining if the area from the split is
        close enough to the desired area.

    """
    if poly is None or poly.area <= target_area:
        return None, None

    # get the mbr properties
    mbr = poly.extent
    xmin = mbr.XMin
    ymin = mbr.YMin
    xmax = mbr.XMax
    ymax = mbr.YMax
    w = mbr.width
    h = mbr.height

    # set up the split orientation
    if w > h:
        is_horiz = True
        dMin = xmin
        dMax = xmax
    else:
        is_horiz = False
        dMin = ymin
        dMax = ymax

    # start searching
    while dMin < dMax:

        # create the split envelopes
        dMid = (dMin + dMax) / 2
        if is_horiz:
            left_splitter = arcpy.Extent(xmin - 100, ymin - 100, dMid, ymax + 100)
            right_splitter = arcpy.Extent(dMid, ymin - 100, xmax + 1, ymax + 100)
        else:
            # note: for vertical, left is lower, right is upper
            left_splitter = arcpy.Extent(xmin - 100, ymin - 100, xmax + 100, dMid)
            right_splitter = arcpy.Extent(xmin - 100, dMid, xmax + 100, ymax + 100)

        # get the left split
        left = poly.clip(left_splitter)
        if left is None:
            return None, None
        left_area = left.area

        if math.fabs(1 - (left_area / target_area)) <= search_tolerance:
            # we're done, get the right side as well
            right = poly.clip(right_splitter)
            return left, right
        else:
            # if area is too large move to left, if too small, move to right
            if left_area > target_area:
                dMax = dMid
            else:
                dMin = dMid

    # if we get this far, there were issues, return nothing
    return None, None


def recursive_split(poly, num_parts, on_done_splitting, search_tolerance=0.005):
    """
    Recursively splits a polygon in two until the number
    of parts is 1. The difference in areas among the resulting polygons
    should not exceed the search tolerance.

    Parameters:
    ----------
    poly: arcpy.Polygon
        The target polygon to split.
    num_parts:
        The number of parts to split the polygon into.
    on_done_splitting: callback function
        Determines what to do w/ the final part. Typically this will involve
        inserting the part into a new feature class.
    search_tolerance: optional, default .005
        Ratio defining if the area from the split is
        close enough to the desired area.

    """
    if num_parts <= 1:
        # we've reached the end, send the final feature to the callback
        on_done_splitting(poly)
        return

    # determine the split shares
    poly_area = poly.area

    if num_parts % 2 == 0:
        # number of parts is even, split in half
        left_area = poly_area / 2
        left_parts = num_parts / 2
        right_parts = num_parts / 2
    else:
        # number of parts is odd, randomly choose which side is larger
        if random.random() > 0.5:
            left_parts = math.ceil(num_parts / 2.0)
        else:
            left_parts = math.floor(num_parts / 2.0)
        right_parts = num_parts - left_parts
        left_area = left_parts * (poly_area / num_parts)

    # do the split and move on
    left, right = split_poly(poly, left_area, search_tolerance)
    recursive_split(left, left_parts, on_done_splitting, search_tolerance)
    recursive_split(right, right_parts, on_done_splitting, search_tolerance)

    return


def split_equal_area(in_polys, out_work, out_fc, max_acres, flds=None):
    """
    Splits a polygon into equally sized areas close to the provided
    acres.

    """

    # create the output feature class, match the attribution of the input
    out_path = '{}//{}'.format(out_work, out_fc)
    desc = arcpy.Describe(in_polys)
    srs = desc.spatialReference
    arcpy.CreateFeatureclass_management(out_work, out_fc, 'POLYGON', spatial_reference=srs)

    # add output fields
    arcpy.AddField_management(out_path, 'ORIG_FID', 'LONG')
    arcpy.AddField_management(out_path, 'SPLIT_SEQ', 'LONG')

    ignore_types = ['Blob', 'Geometry', 'OID', 'Raster']
    if flds is None:
        out_flds = [f for f in arcpy.ListFields(in_polys) if f.type not in ignore_types]
    else:
        out_flds = [f for f in arcpy.ListFields(in_polys) if f.name in flds]

    for f in out_flds:
        arcpy.AddField_management(
            out_path,
            f.name,
            f.type,
            field_length=f.length,
            field_alias=f.aliasName
        )

    # get cursors
    oid_fld = desc.OIDFieldName
    rows = arcpy.da.SearchCursor(
        in_polys, ['SHAPE@', oid_fld] + [f.name for f in out_flds])

    insert = arcpy.da.InsertCursor(
        out_path, ['SHAPE@', 'ORIG_FID', 'SPLIT_SEQ'] + [f.name for f in out_flds])

    # loop through the polys
    counter = 0
    for row in rows:

        if counter % 10000 == 0:
            print('on ' + str(counter) + '...')
        counter += 1

        # properties for the current poly
        curr_shp = row[0]
        curr_oid = row[1]
        curr_acres = curr_shp.getArea('PLANAR', 'ACRES')
        num_parts = math.floor(curr_acres / max_acres)

        # callback for performing the insert
        feat_count = [1]

        def on_done(part):
            curr_seq = feat_count[0]
            insert.insertRow([part, curr_oid, curr_seq] + list(row[2:]))
            feat_count[0] += 1

        # start the split sequence
        recursive_split(curr_shp, num_parts, on_done)
