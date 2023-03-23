"""
Use this module to integrate ArcGIS data objects
with pandas.

Dependencies & caveats:
- py27:
    - ArcGIS desktop 64 bit background geoprocessing installed
    - If not using the ArcGIS python distribution, must have the following in the
      python path of the distribution:
        C:\Program Files (x86)\ArcGIS\Desktop10.7\bin64
        C:\Program Files (x86)\ArcGIS\Desktop10.7\arcpy
- py36:
    - ArcGIS Pro
    - Must be working w/in the pro conda environment (or a clone)


Expected workspaces:
- Shapefile and dbase table: full path to folder location
- File geodatabase: full path to geodatabse (.gdb folder)
- Database: full path .sde file

"""

# code is not in arc_utils module
from smartpy_arc.arc_utils import *