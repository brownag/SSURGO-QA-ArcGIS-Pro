# ---------------------------------------------------------------------------
# QA_SliverFinder.py
# Created on: 2013

# Author: Steve.Peaslee
#         GIS Specialist
#         National Soil Survey Center
#         USDA - NRCS
# e-mail: adolfo.diaz@usda.gov
# phone: 608.662.4422 ext. 216

# Author: Adolfo.Diaz
#         GIS Specialist
#         National Soil Survey Center
#         USDA - NRCS
# e-mail: adolfo.diaz@usda.gov
# phone: 608.662.4422 ext. 216
#
# Identifies polygon line segments shorter than a specified length.
# Calculate area statistics for each polygon and load into a table
# Join table by OBJECTID to input featurelayer to spatially enable polygon statistics
# Create point featurelayer marking endpoints for those polygon line segments that
# are shorter than a specified distance.
#
# 06-06-2013 adapted from QA_VertexFlags
#
# 06-21-2013 fixing major bug in function that reads geometry
# Removing the interior ring segments from the search. Normally any errors would
# be duplicated in the island polygon.
#
# One thing that gave me fits was writing a string containing the degree character (chr 176)
# to a table. First use 'locale.getpreferredencoding()' to find out what your system is using.
# Next using decode as in this example:  sAngle = (Number_Format(theAngle, 1, False) + chr(176)).decode('cp1252')
# 10-31-2013
#
# 11-06-2013 Altered output workspace for QA layers to be always be in the geodatabase, not the featuredataset

# ==========================================================================================
# Updated  1/20/2021 - Adolfo Diaz
#
# - Updated and Tested for ArcGIS Pro 2.5.2 and python 3.6
# - All "decode(locale.getpreferredencoding())" references were removed since this is no longer
#   needed in python 3.6.  This was used to create the degree sign
# - All describe functions use the arcpy.da.Describe functionality.
# - All intermediate datasets are written to "in_memory" instead of written to a FGDB and
#   and later deleted.  This avoids having to check and delete intermediate data during every
#   execution.
# - All cursors were updated to arcpy.da
# - Added code to remove layers from an .aprx rather than simply deleting them
# - Updated AddMsgAndPrint to remove ArcGIS 10 boolean and gp function
# - Updated errorMsg() Traceback functions slightly changed for Python 3.6.
# - Added parallel processing factor environment
# - swithced from sys.exit() to exit()
# - All gp functions were translated to arcpy
# - Every function including main is in a try/except clause
# - Main code is wrapped in if __name__ == '__main__': even though script will never be
#   used as independent library.
# - Normal messages are no longer Warnings unnecessarily.


# ===============================================================================================================
def AddMsgAndPrint(msg, severity=0):
    # prints message to screen if run as a python script
    # Adds tool message to the geoprocessor
    #
    #Split the message on \n first, so that if it's multiple lines, a GPMessage will be added for each line
    try:

        print(msg)
        #for string in msg.split('\n'):
            #Add a geoprocessing message (in case this is run as a tool)
        if severity == 0:
            arcpy.AddMessage(msg)

        elif severity == 1:
            arcpy.AddWarning(msg)

        elif severity == 2:
            arcpy.AddError("\n" + msg)

    except:
        pass

# ================================================================================================================
def errorMsg():
    try:

        exc_type, exc_value, exc_traceback = sys.exc_info()
        theMsg = "\t" + traceback.format_exception(exc_type, exc_value, exc_traceback)[1] + "\n\t" + traceback.format_exception(exc_type, exc_value, exc_traceback)[-1]

        if theMsg.find("exit") > -1:
            AddMsgAndPrint("\n\n")
            pass
        else:
            AddMsgAndPrint(theMsg,2)

    except:
        AddMsgAndPrint("Unhandled error in unHandledException method", 2)
        pass

## ===================================================================================
def CreateWebMercaturSR():
    # Create default Web Mercatur coordinate system for instances where needed for
    # calculating the projected length of each line segment. Only works when input
    # coordinate system is GCS_NAD_1983, but then it should work almost everywhere.
    #
    try:
        # Use WGS_1984_Web_Mercator_Auxiliary_Sphere
        #theSpatialRef = arcpy.SpatialReference("USA Contiguous Albers Equal Area Conic USGS")
        theSpatialRef = arcpy.SpatialReference(3857)
        arcpy.env.geographicTransformations = "WGS_1984_(ITRF00)_To_NAD_1983"

        # return spatial reference string
        return theSpatialRef

    except:
        errorMsg()

## ===================================================================================
def GetAngleFromPoints(pntList, iPnt):
    # Calculate angle from 3 pairs of cartesian coordinates
    #
    try:
        #x1 = pntList[0][0]
        #y1 = pntList[0][1]
        #x2 = pntList[1][0]
        #y2 = pntList[1][1]
        #x3 = pntList[2][0]
        #y3 = pntList[2][1]

        # A->B
        dx = pntList[1 + iPnt][0] - pntList[0 + iPnt][0]
        dy = pntList[1 + iPnt][1] - pntList[0 + iPnt][1]
        mAB = math.sqrt(dx**2 + dy**2)

        # B->C
        dx = pntList[2 + iPnt][0] - pntList[1 + iPnt][0]
        dy = pntList[2 + iPnt][1] - pntList[1 + iPnt][1]
        mBC = math.sqrt(dx**2 + dy**2)

        # C->A
        dx = pntList[0 + iPnt][0] - pntList[2 + iPnt][0]
        dy = pntList[0 + iPnt][1] - pntList[2 + iPnt][1]
        mCA = math.sqrt(dx**2 + dy**2)

        if mAB == 0 or mBC == 0:
            AddMsgAndPrint("Failed to calculate angle at point " + str(iPnt), 0)
            return 0

        p = round((mAB**2 + mBC**2 - mCA**2 ) / (2 * mAB * mBC),10)
        theAngle = int(round(math.degrees(math.acos(p)), 0))

        #if theAngle > 180:
        #    theAngle -= 180

        return theAngle

    except:
        errorMsg()
        return -1

## ===================================================================================
def ProcessLayer(inLayer, outputSR, minAngle, iSelection):
    # All the real work is performed within this function
    # inLayer = selected featurelayer or featureclass that will be processed

    try:

        # Begin processing...
        AddMsgAndPrint("\nLocating polygon angles less than " + str(minAngle) + chr(176)) #.decode(locale.getpreferredencoding()), 0)

        # Process input featurelayer polygon geometry using search cursor
        arcpy.SetProgressorLabel("Reading polygon geometry...")
        arcpy.SetProgressor("step", "Reading polygon geometry...",  0, iSelection, 1)
        iErr = 0
        fieldList = ["OID@", "SHAPE@"]
        dLines = dict()
        dTest = dict()  # this dictionary will only contain the common key and the angle (for sorting by angle)
        iPnt = 0
        badPolys = list()

        with arcpy.da.SearchCursor(inLayer, fieldList,"",outputSR) as sCursor:
            # open searchcursor on input layer and read geometry one record at a time

            for row in sCursor:
                iPnt = 0
                iPart = 0
                fid = row[0]
                feat = row[1]
                #fid, feat = row # do I need to worry about NULL geometry here?
                #AddMsgAndPrint("Processing polygon FID " + str(fid))

                try:
                    # geometry object must have a feature associated
                    if not feat is None:

                        # geometry object has at least 1 polygon
                        if feat.partCount > 0:

                            #AddMsgAndPrint("\nPolygon #" + str(fid) + " with " + str(feat.partCount) + " parts and " + splitThousands(feat.pointCount) + " points")

                            # Iterate through the polygon geometry object
                            for part in feat:

                                # accumulate 3 points for each segment
                                pntList = []  # initialize points list for polygon
                                #AddMsgAndPrint("\tPart " + str(iPart) + " has " + str(len(part)) + " vertices")

                                # iterate through the invidual vertices of polygon
                                for pnt in part:
                                    if pnt:
                                        # add vertice or to-node coordinates to list
                                        #AddMsgAndPrint(str(iPnt) + ", " + str(pnt.X) + ", " + str(pnt.Y))
                                        pntList.append((pnt.X,pnt.Y))
                                        iPnt += 1

                                    else:
                                        # interior ring encountered, don't process any more
                                        # This means that islands that belong to other survey areas will NOT be checked for slivers
                                        #AddMsgAndPrint(" \nIsland Polygon encountered", 1)
                                        break

                                # add vertex 1 to wrap around again
                                pntList.append(pntList[1])
                                #AddMsgAndPrint("Wrap" + ", " + str(pntList[1][0]) + ", " + splitThousands(pntList[1][1]))
                                iPart += 1

                            numPnts = len(pntList) - 2  # Problem with only 3 of 4 angles being detected

                            for iPnt in range(numPnts):
                                try:
                                    theAngle = GetAngleFromPoints(pntList, iPnt)

                                    if theAngle <= minAngle:
                                        iErr += 1
                                        arcpy.SetProgressorLabel("Reading polygon geometry (" + str(iErr) + " locations flagged)")
                                        # save these 3 coordinate pairs to the dictionary for later use
                                        dLines[iErr] = ( [(pntList[0 + iPnt][0], pntList[0 + iPnt][1]), (pntList[1 + iPnt][0], pntList[1 + iPnt][1]), (pntList[2 + iPnt][0], pntList[2 + iPnt][1])], fid, theAngle)
                                        dTest[iErr] = theAngle
                                        iPnt += 1

                                except:
                                    break

                            arcpy.SetProgressorPosition()

                        else:
                            # Geometry error: Polygon Part with no parts
                            badPolys.append(str(fid))
                            #return False

                    else:
                        # Geometry error: Polygon with NULL geometry
                        badPolys.append(str(fid))
                        #return False

                except:
                    AddMsgAndPrint("FID: " + str(fid) + " ---- FEAT: " + str(feat),2)
                    errorMsg()

        arcpy.ResetProgressor()

        # If errors are found in the polygon geometry, report and then return an error
        if len(badPolys) > 0:
            AddMsgAndPrint("Bad polygon geometry detected for the following polygons: " + ", ".join(badPolys) + " \n ", 2)
            return False

        # Create a copy of the dLines dictionary, sorted by angle
        # This dictionary will be used to create the output layers, smallest angles first
        dAngles = OrderedDict(sorted(list(dTest.items()), key=lambda x: x[1]))

        # Create output line featureclass containing acute angles that were flagged
        #
        if len(dLines) > 0:
            arcpy.env.addOutputsToMap = False
            # Found acute angles below specification
            AddMsgAndPrint("Saved " + splitThousands(iErr) + " sliver locations to the following 'QA' layers: ")

            # add flagged midpoints to new points featureclass
            outLayer = MakeLineLayer(theCatalogPath, outputSR, minAngle)
            outLayer2 = MakePointLayer(theCatalogPath, outputSR, minAngle)

            # combine output to both featureclasses in the same with statement
            with arcpy.da.InsertCursor(os.path.join(arcpy.env.workspace, outLayer), ["SHAPE@", "POLYID", "ANGLE"]) as lineCursor:

                # for each value that has a reported common-point, get the list of coordinates and the
                # calculated angle from dLines dictionary and write to the output slivers featureclass
                #for key, val in dLines.items():

                iCnt = 0
                for key in dAngles:
                    pntList, fid, theAngle = dLines[key]
                    #AddMsgAndPrint("\tFID = " + str(fid), 0)
                    pnt0 = arcpy.Point(pntList[0][0],pntList[0][1])
                    pnt1 = arcpy.Point(pntList[1][0],pntList[1][1])
                    pnt2 = arcpy.Point(pntList[2][0],pntList[2][1])
                    array = arcpy.Array([pnt0, pnt1, pnt2])
                    polyLine = arcpy.Polyline(array)
                    rowLine = (polyLine, fid, theAngle)
                    lineCursor.insertRow(rowLine)

            # create new featurelayer from sliver polylines
            layerPath = os.path.dirname(sys.argv[0])
            layerFile1 = os.path.join(layerPath,"Yellow_Line.lyr")
            #outLayerName = "QA Slivers (" + splitThousands(minAngle) + chr(176).decode(locale.getpreferredencoding()) + " angle)"
            outLayerName = "QA Slivers (" + splitThousands(minAngle) + chr(176) + " angle)"

            arcpy.MakeFeatureLayer_management(outLayer, outLayerName)
            arcpy.ApplySymbologyFromLayer_management (outLayerName, layerFile1)
            arcpy.SetParameter(3, outLayerName)
            AddMsgAndPrint(" \n ", 0)

            # Run through dictionary a second time, but now loading vertex locations into point featureclass
            with arcpy.da.InsertCursor(os.path.join(arcpy.env.workspace, outLayer2), ["SHAPE@", "POLYID", "ANGLE"]) as pntCursor:

                # for each value that has a reported common-point, get the list of coordinates and the
                # calculated angle from dLines dictionary and write to the output slivers featureclass
                for key in dAngles:
                    pntList, fid, theAngle = dLines[key]
                    #AddMsgAndPrint("\tFID = " + str(fid), 0)
                    pnt1 = arcpy.Point(pntList[1][0],pntList[1][1])
                    # write out angle as text with degrees
                    sAngle = str(theAngle) + chr(176)#.decode(locale.getpreferredencoding())
                    rowPnt = (pnt1, fid, sAngle)
                    pntCursor.insertRow(rowPnt)

            # create new featurelayer from sliver vertices
            layerPath = os.path.dirname(sys.argv[0])
            layerFile2 = os.path.join(layerPath,"Red_SliverVertex.lyr")
            outLayerName2 = "QA Sliver Vertex (" + splitThousands(minAngle) + chr(176) + " angle)"
            #outLayerName2 = "QA Sliver Vertex (" + splitThousands(minAngle) + chr(176).decode(locale.getpreferredencoding()) + " angle)"
            arcpy.MakeFeatureLayer_management(outLayer2, outLayerName2)
            arcpy.ApplySymbologyFromLayer_management (outLayerName2, layerFile2)
            arcpy.SetParameter(4, outLayerName2)

            # add new line layer to top of TOC
            # behavior with new map layers is a little flaky with arcpy.mapping.
            # layers created with MakeFeatureLayer don't automatically show up in the list,
            # so you need to using mapping.Layer and mapping.AddLayer.
            # then you need to search for and get the layer from the list in order to get
            # access to the properties.
            try:
                # if this is ArcCatalog, this next line will cause failure and drop past this next section
                mxd = arcpy.mapping.MapDocument("CURRENT")
                df = arcpy.mapping.ListDataFrames(mxd, "*")[0]
                mLayer1 = arcpy.mapping.Layer(outLayerName)
                arcpy.mapping.AddLayer(df, mLayer1, "TOP")
                mLayers = arcpy.mapping.ListLayers(mxd)

                for mLayer1 in mLayers:
                    if mLayer1.name == outLayerName:
                        mLayer1.visible = False
                        break

                arcpy.env.addOutputsToMap = True
                mLayer2 = arcpy.mapping.Layer(outLayerName2)
                arcpy.mapping.AddLayer(df, mLayer2, "TOP")
                mLayers = arcpy.mapping.ListLayers(mxd)

                for mLayer2 in mLayers:
                    if mLayer2.name == outLayerName2:
                        mLayer2.visible = True
                        #mLayer2.UpdateLayer(df, mLayer2, layerFile, True)

                        if mLayer2.supports("LABELCLASSES"):
                            mLayer2.showLabels = True
                            lblClasses = mLayer2.labelClasses

                            for lblClass in lblClasses:
                                lblClass.expression = "[POLYID]"
                                #mLayer2.UpdateLayer(df, mLayer2, layerFile, True)
                                #AddMsgAndPrint("\tLabel Class: " + lblClass.className + "; " + lblClass.expression, 0)

                        break

                #mLayer2.UpdateLayer(df, mLayer2, layerFile, True)
                #arcpy.ApplySymbologyFromLayer_management (outLayerName2, layerFile2)

            except:
                # must be ArcCatalog
                pass

        else:
            # no problems found
            AddMsgAndPrint(" \nNo polygon angles less than " + splitThousands(minAngle) + " degrees were found \n ", 0)
            pass

        return True

    except:
        errorMsg()
        return False

## ===================================================================================
def MakeLineLayer(theCatalogPath, outputSR, minAngle):
    # Create polyline featureclass with short line segments defining the acute angle
    # Return table to ProcessLayer so that records can be added.
    #
    try:
        # Set workspace to that of the input polygon featureclass
        #loc = os.path.dirname(theCatalogPath)
        loc = arcpy.env.workspace
        desc = arcpy.Describe(loc)
        dt = desc.dataType.upper()

        if dt == "WORKSPACE":
            arcpy.env.workspace = loc
            ext = ""

        elif dt == "FEATUREDATASET":
            arcpy.env.workspace = os.path.dirname(loc)
            ext = ""

        elif dt == "FOLDER":
            arcpy.env.workspace = loc
            ext = ".shp"

        else:
            AddMsgAndPrint(" \n" + loc + " is a " + dt + " datatype", 2)
            return ""

        errorLayer = "QA_Slivers_" + splitThousands(minAngle) + "d" + ext
        AddMsgAndPrint(" \n\t1. Output slivers layer: " + os.path.join(arcpy.env.workspace,errorLayer), 0)

        if arcpy.Exists(os.path.join(arcpy.env.workspace, errorLayer)):
            arcpy.Delete_management(os.path.join(arcpy.env.workspace, errorLayer))

        arcpy.CreateFeatureclass_management(arcpy.env.workspace, errorLayer, "POLYLINE", "", "DISABLED","DISABLED", outputSR)

        # create new fields to store objectid and minimum segment length found for each polygon
        if arcpy.Exists(errorLayer):

            try:
                # "POLYID","ANGLE"
                #arcpy.AddField_management(errorLayer, "POLYID", "LONG")
                arcpy.AddField_management(errorLayer, "POLYID", "TEXT", "", "", 20, "POLYID")
                arcpy.AddField_management(errorLayer, "ANGLE", "DOUBLE", "12", "3")
                # Add new field to track status of each point
                arcpy.AddField_management(errorLayer, "Status", "TEXT", "", "", 10, "Status")

                try:
                    arcpy.DeleteField_management(errorLayer, "ID")

                except:
                    pass

                return errorLayer

            except:
                errorMsg()
                return ""

        else:
            errorMsg()
            return ""

    except:
        errorMsg()
        return ""

## ===================================================================================
def MakePointLayer(theCatalogPath, outputSR, minAngle):
    # Create points featureclass containing midpoint coordinates for short line segments.
    # Return table to ProcessLayer so that records can be added.
    #
    try:
        # Set workspace to that of the input polygon featureclass
        #loc = os.path.dirname(theCatalogPath)
        loc = env.workspace
        desc = arcpy.Describe(loc)
        dt = desc.dataType.upper()

        if dt == "WORKSPACE":
            env.workspace = loc
            ext = ""

        elif dt == "FEATUREDATASET":
            env.workspace = os.path.dirname(loc)
            ext = ""

        elif dt == "FOLDER":
            env.workspace = loc
            ext = ".shp"

        else:
            AddMsgAndPrint(" \n" + loc + " is a " + dt + " datatype", 2)
            return ""

        errorLayer = "QA_SliverPoints_" + splitThousands(minAngle) + "d" + ext
        AddMsgAndPrint(" \n\t2. Output vertex point layer: " + os.path.join(env.workspace,errorLayer), 0)

        if arcpy.Exists(os.path.join(env.workspace, errorLayer)):
            arcpy.Delete_management(os.path.join(env.workspace, errorLayer))

        arcpy.CreateFeatureclass_management(env.workspace, errorLayer, "POINT", "", "DISABLED","DISABLED", outputSR)

        # create new fields to store objectid and minimum segment length found for each polygon
        if arcpy.Exists(errorLayer):

            try:
                # "POLYID","ANGLE"
                arcpy.AddField_management(errorLayer, "POLYID", "LONG")
                #arcpy.AddField_management(errorLayer, "ANGLE", "DOUBLE", "12", "3")
                arcpy.AddField_management(errorLayer, "ANGLE", "TEXT", "", "", 8, "ANGLE")

                # Add new field to track status of each point
                arcpy.AddField_management(errorLayer, "Status", "TEXT", "", "", 10, "Status")

                try:
                    arcpy.DeleteField_management(errorLayer, "ID")

                except:
                    pass

                return errorLayer

            except:
                errorMsg()
                return ""

        else:
            errorMsg()
            return ""

    except:
        errorMsg()
        return ""

# ===================================================================================
def splitThousands(someNumber):
    """will determine where to put a thousands seperator if one is needed. Input is
       an integer.  Integer with or without thousands seperator is returned."""

    try:
        return re.sub(r'(\d{3})(?=\d)', r'\1,', str(someNumber)[::-1])[::-1]

    except:
        errorMsg()
        return someNumber

## ===================================================================================
import sys, string, os, locale, math, operator, traceback, re
from collections import OrderedDict
import arcpy
from arcpy import env

if __name__ == '__main__':

    try:
        # Set formatting for numbers
        locale.setlocale(locale.LC_ALL, "")

        # Target Featureclass
        inLayer = arcpy.GetParameter(0)

        # Minimum angle allowed before it is considered to be a potential error
        minAngle = arcpy.GetParameter(1)

        # Projection (optional when input layer has projected coordinate system)
        outputSR = arcpy.GetParameter(2)

        # Output featurelayer containing slivers (polylines with 3 vertices)
        #outLayer = arcpy.GetParameterAsText(3)

        arcpy.SetProduct("ArcInfo")
        arcpy.env.parallelProcessingFactor = "75%"
        arcpy.env.overwriteOutput = True
        arcpy.env.XYTolerance = 0
        arcpy.env.addOutputsToMap = False

        # Setup: Get all required information from input layer
        # Describe input layer
        desc = arcpy.Describe(inLayer)
        theDataType = desc.dataType.upper()
        theCatalogPath = desc.catalogPath
        fidFld = desc.OIDFieldName
        inputSR = desc.spatialReference
        inputDatum = inputSR.GCS.datumName

        # Set output workspace
        if arcpy.Describe(os.path.dirname(theCatalogPath)).dataType.upper() == "FEATUREDATASET":
            # if input layer is in a featuredataset, move up one level to the geodatabase
            env.workspace = os.path.dirname(os.path.dirname(theCatalogPath))
        else:
            env.workspace = os.path.dirname(theCatalogPath)

        AddMsgAndPrint(" \nOutput workspace set to: " + env.workspace, 0)

        # Get total number of features for the input featureclass
        iTotalFeatures = int(arcpy.GetCount_management(theCatalogPath).getOutput(0))

        # Get input layer information and count the number of input features
        if theDataType == "FEATURELAYER":
            # input layer is a FEATURELAYER, get featurelayer specific information
            defQuery = desc.whereClause
            fids = desc.FIDSet
            layerName = desc.nameString

            # get count of number of features being processed
            if fids == "":
                # No selected features in layer
                iSelection = iTotalFeatures

                if defQuery == "":
                    # No query definition and no selection
                    iSelection = iTotalFeatures
                    AddMsgAndPrint(" \nProcessing all " + splitThousands(iTotalFeatures) + " polygons in '" + layerName + "'...", 0)

                else:
                    # There is a query definition, so the only option is to use GetCount
                    iSelection = int(arcpy.GetCount_management(inLayer).getOutput(0))  # Use selected features code
                    AddMsgAndPrint(" \nProcessing " + splitThousands(iSelection) + " of " + splitThousands(iTotalFeatures) + " features...", 0)

            else:
                # featurelayer has a selected set, get count using FIDSet
                iSelection = len(fids.split(";"))
                AddMsgAndPrint(" \nProcessing " + splitThousands(iSelection) + " of " + splitThousands(iTotalFeatures) + " features...", 0)

        elif theDataType in ("FEATURECLASS", "SHAPEFILE"):
            # input layer is a featureclass, get featureclass specific information
            layerName = desc.baseName
            defQuery = ""
            fids = ""
            iSelection = iTotalFeatures
            AddMsgAndPrint("\nProcessing all " + splitThousands(iTotalFeatures) + " polygons in '" + layerName + "'...")

        # Make sure that input and output datums are the same, no transformations allowed
        if outputSR.name == '':
            outputSR = inputSR
            outputDatum = inputDatum
            #AddMsgAndPrint(" \nSetting output CS to same as input: " + outputSR.name + " \n" + outputDatum + " \n ", 0)

        else:
            outputDatum = outputSR.GCS.datumName
            #AddMsgAndPrint(" \nOutput datum: '" + outputDatum + "'", 0)

        if inputDatum != outputDatum:
            AddMsgAndPrint("Input and output datums do not match",2)

        if outputSR.type.upper() != "PROJECTED":
            if inputDatum in ("D_North_American_1983", "D_WGS_1984"):
                # use Web Mercatur as output projection for calculating segment length
                AddMsgAndPrint("\nInput layer coordinate system is not projected, switching to Web Mercatur (meters)", 1)
                outputSR = CreateWebMercaturSR()

            else:
                AddMsgAndPrint("Unable to handle output coordinate system: " + outputSR.name + " \n" + outputDatum,2)

        else:
            AddMsgAndPrint("\nFinal output coordinate system: " + outputSR.name)

        theUnits = outputSR.linearUnitName.lower()
        theUnits = theUnits.replace("foot", "feet")
        theUnits = theUnits.replace("meter", "meters")

        if theUnits.startswith("meter"):
            unitAbbrev = "m"
        else:
            unitAbbrev = "ft"

        # run process
        bProcessed = ProcessLayer(inLayer, outputSR, minAngle, iSelection)

    except:
        errorMsg()


