# ---------------------------------------------------------------------------
# QA_VertexProblems.py
# Created on: July 10, 2009

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

# Identifies polygon line segments shorter than a specified length.
# Calculate area statistics for each polygon and load into a table
# Join table by OBJECTID to input featurelayer to spatially enable polygon statistics
# Create point featurelayer marking endpoints for those polygon line segments that
# are shorter than a specified distance.
#
# 07-10-2009 Original coding
# 05-15-2013 Renamed for SSURGO QA and converted to arcpy with da cursors (ArcGIS 10.1). Major rewrite.
# 06-07-2013 Problem with pre-existing join at line 240. Possibley failing to remove old join with shapefile input.
# 10-31-2013

# ==========================================================================================
# Updated  1/26/2021 - Adolfo Diaz
#
# - Updated and Tested for ArcGIS Pro 2.6.1 and python 3.6
# - All describe functions use the arcpy.da.Describe functionality.
# - FIDSet now returns None and cannot be compared with ""
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
def ProcessLayer(inLayer, outputSR, outLayer, minDist, iSelection):
    # All the real work is performed within this function
    # inLayer = selected featurelayer or featureclass that will be processed

    try:
        # Create table to store geometry statistics for each polygon
        # Later this table will be joined to the input layer on POLYID
        #
        AddMsgAndPrint(" \nReading polygon geometry...", 0)

        # Create a list of coordinate pairs that have been added to the table to prevent duplicates
        #
        lSegments = []

        # create new table to store individual polygon statistics
        # POLYID,ACRES,VERTICES,AVI,MIN_DIST,MULTIPART
        statsTbl = MakeStatsTable(unitAbbrev)

        if arcpy.Exists(statsTbl):
            # open update cursor on polygon statistics table
            iCursor = arcpy.da.InsertCursor(statsTbl, ["POLYID","ACRES","VERTICES","AVI","MIN_DIST","MULTIPART"])

        else:
            return False

        # Process input featurelayer polygon geometry using search cursor
        #
        arcpy.SetProgressorLabel("Reading polygon geometry...")
        arcpy.SetProgressor("step", "Reading polygon geometry...",  0, iSelection, 1)
        iCnt = 0
        fieldList = ["OID@","SHAPE@","SHAPE@AREA","SHAPE@LENGTH"]
        dPoints = dict()
        bHasMultiPart = False

        with arcpy.da.SearchCursor(inLayer, fieldList,"",outputSR) as sCursor:
            #SearchCursor (in_table, field_names, {where_clause}, {spatial_reference}, {explode_to_points}, {sql_clause})

            for fid, feat, theArea, thePerimeter in sCursor:
                # Process a polygon record. row[1] is the same as feat
                #fid, feat, theArea, thePerimeter = row # do I need to worry about NULL geometry here?

                if not feat is None:
                    # check to make sure geometry object contains a single-part polygon
                    iPartCnt = feat.partCount

                    if iPartCnt == 1:
                        iPartCnt = 0

                    elif iPartCnt == 0:
                        AddMsgAndPrint("Bad geometry for polygon #" + str(fid),2)

                    else:
                      bHasMultiPart = True

                    # get the total number of points for this polygon
                    iPnts = feat.pointCount
                    iSeg = 1000000  # use an arbitrarily high segment length as the minimum for comparison

                    for part in feat:
                        # accumulate 2 points for each segment
                        pntList = []  # initialize points list for polygon
                        pnt0 = part[0]

                        for pnt in part:
                            try:
                                pntList.append((pnt.X,pnt.Y))

                            except:
                                pass

                            if pnt:
                                # add vertice or to-node coordinates to list

                                if len(pntList) == 2:
                                    # calculate current segment length using 2 points
                                    dist = math.hypot(pntList[0][0] - pntList[1][0], pntList[0][1] - pntList[1][1] )
                                    #AddMsgAndPrint("\tLen: " + str(dist), 0)

                                    if dist < iSeg:
                                        iSeg = dist

                                    if dist < minDist:
                                        iCnt += 1

                                        # get midpoint of short line segment for vertex flag placement
                                        xm = (pntList[0][0] + pntList[1][0]) / 2.0
                                        ym = (pntList[0][1] + pntList[1][1]) / 2.0
                                        midPnt = [(xm,ym), fid, dist]

                                        # print line segment that is less than specified distance
                                        #AddMsgAndPrint("\t\tPolygon " + str(fid) + ":  " + str(midPnt), 0)

                                        if fid in dPoints:
                                            # add this point to the existing list for this polygon
                                            dPoints[fid].append(midPnt)

                                        else:
                                            # create new dictionary entry for this polygon
                                            dPoints[fid] = [midPnt]
                                            arcpy.SetProgressorLabel("Reading polygon geometry ( " + Number_Format(len(dPoints)) + " locations flagged )...")

                                    # then drop the first point from the list
                                    pntList.pop(0)

                                # add the next point
                                #pntList.append((pnt.X,pnt.Y))

                            else:
                                # interior ring or end of polygon encountered,
                                #AddMsgAndPrint("\tInterior Ring...", 0)
                                pntList = []  # reset points list for interior ring
                                break

                else:
                    # bad polygon geometry
                    AddMsgAndPrint("NULL geometry for polygon #" + str(fid),2)

                #POLYID,ACRES,VERTICES,AVI,MIN_DIST,MULTIPART
                if theUnits == "meters":
                    acres = theArea / 4046.85643

                elif theUnits == "feet_us":
                    acres = theArea / 43560.0

                else:
                    AddMsgAndPrint("\nFailed to calculate acre value using unit: " + theUnits, 2)
                    return False

                avi = thePerimeter / iPnts
                outRow = [fid, acres,iPnts,avi,iSeg,iPartCnt]
                iCursor.insertRow(outRow)
                arcpy.SetProgressorPosition()

        del outRow
        del iCursor

        if bHasMultiPart:
            AddMsgAndPrint("Input layer has multipart polygons that require editing (explode)", 2)

        if outLayer != "" and len(dPoints) > 0:
            # pairs of close vertices were flagged and need to be exported as midpoints in a new featureclass
            AddMsgAndPrint("\nFlagged " + Number_Format(iCnt, 0, True) + " segments shorter than " + str(minDist) + " " + theUnits,1)

            # add flagged midpoints to new points featureclass
            outLayer = MakePointsLayer(outputSR, minDist, unitAbbrev)

            arcpy.SetProgressorLabel("Saving midpoint of each short segment...")
            arcpy.SetProgressor("step", "Saving midpoint of each short segment...",  0, iCnt, 1)

            with arcpy.da.InsertCursor(os.path.join(env.workspace, outLayer), ["SHAPE@","POLYID","LENGTH_" + unitAbbrev]) as pntCursor:

                # for each value that has a reported common-point, get the list of coordinates from
                # the dDups dictionary and write to the output Common_Points featureclass
                for fid in list(dPoints.keys()):
                    pnts = dPoints[fid]

                    for pnt in pnts:
                        #AddMsgAndPrint("\t" + str(fid) + ": " + str(pnt[0]) + ", " + str(pnt[1]) + ", " + str(pnt[2]), 0)
                        pntCursor.insertRow(pnt)

                    arcpy.SetProgressorPosition()

            # create join between input polygon layer and QA_VertexStats table
            # "QA_VertexStats"
            AddMsgAndPrint(" \nOutput polygon statistics table: " + os.path.basename(statsTbl) + " (joined to input layer)", 0)
            arcpy.AddIndex_management (statsTbl, "POLYID", "Indx_PolyID", "UNIQUE", "NON_ASCENDING")
            arcpy.AddJoin_management (inLayer, fidFld, statsTbl, "POLYID", "KEEP_ALL")

            # create new featurelayer from vertex flag points
            layerPath = os.path.dirname(sys.argv[0])
            AddMsgAndPrint(layerPath)
            # layerFile = os.path.join(layerPath, "RedDot.lyr")
            outLayerName = "QA Vertex Flag Points (" + str(minDist) + " " + unitAbbrev + ")"
            arcpy.MakeFeatureLayer_management(outLayer, outLayerName)
            arcpy.env.addOutputsToMap = True
            # arcpy.ApplySymbologyFromLayer_management (outLayerName, layerFile)
            arcpy.SetParameter(3, outLayerName)
            arcpy.ResetProgressor()

        else:
            # no problems found
            #arcpy.Delete_management(statsTbl)
            AddMsgAndPrint("\nNo short segments detected (less than " + Number_Format(minDist, 3, False) + " " + theUnits + ") \n ", 0)
            pass

        return True

    except:
        errorMsg()
        return False

## ===================================================================================
def MakePointsLayer(outputSR, minDist, unitAbbrev):
    # Create points shapefile in memory containing midpoint coordinates for short line segments.
    # Return table to ProcessLayer so that records can be added.
    #
    try:
        # Set workspace to that of the input polygon featureclass
        loc = env.workspace
        desc = arcpy.Describe(loc)
        dt = desc.dataType.upper()

        if dt == "WORKSPACE":
            ext = ""

        elif dt == "FEATUREDATASET":
            ext = ""

        elif dt == "FOLDER":
            ext = ".shp"

        else:
            AddMsgAndPrint(" \n" + loc + " is a " + dt + " datatype", 2)
            return ""

        pointsLayer = "QA_VertexFlags_" + str(minDist).replace(".", "_") + ext
        AddMsgAndPrint(" \nOutput points layer: " + os.path.join(env.workspace,pointsLayer), 1)
        arcpy.CreateFeatureclass_management(env.workspace, pointsLayer, "POINT", "", "DISABLED","DISABLED", outputSR)

        # create new fields to store objectid and minimum segment length found for each polygon
        if arcpy.Exists(pointsLayer):

            try:
                # "POLYID","SEGNO","LENGTH"
                arcpy.AddField_management(pointsLayer, "POLYID", "LONG")
                arcpy.AddField_management(pointsLayer, "LENGTH" + "_" + unitAbbrev.upper(), "DOUBLE", "12", "3")
                # Add new field to track status of each point
                arcpy.AddField_management(pointsLayer, "Status", "TEXT", "", "", 10, "Status")

                try:
                    arcpy.DeleteField_management(pointsLayer, "ID")

                except:
                    pass

                return pointsLayer

            except:
                AddMsgAndPrint("Exception while adding shapefile fields in MakePointsLayer", 2)
                errorMsg()
                return ""

        else:
            AddMsgAndPrint("Failed to create output shapefile in MakePointsLayer", 2)
            errorMsg()
            return ""

    except:
        errorMsg()
        return ""

## ===================================================================================
def MakeStatsTable(unitAbbrev):
    # Create join table containing polygon statistics
    # At the end, this table will be joined to the input featureclass so that values
    # can be mapped to show where the layer has issues.
    #
    try:
        thePrefix = "QA_VertexStats"

        if env.workspace.endswith(".gdb"): # or env.workspace.endswith(".mdb"):
            theExtension = ""

        else:
            theExtension = ".dbf"

        statsTbl = os.path.join(env.workspace, thePrefix + theExtension)

        try:
            if arcpy.Exists(statsTbl):
                arcpy.Delete_management(statsTbl)

            arcpy.CreateTable_management(os.path.dirname(statsTbl), os.path.basename(statsTbl))
            #AddMsgAndPrint("Created polygon stats table (" + statsTbl + ")", 1)

        except:
            errorMsg()
            return ""

        try:
            # POLYID,ACRES,VERTICES,AVI,MIN_DIST,MULTIPART
            #AddField_management (in_table, field_name, field_type, {field_precision}, {field_scale}, {field_length}, {field_alias}, {field_is_nullable}, {field_is_required}, {field_domain})
            arcpy.AddField_management(statsTbl, "POLYID", "LONG","","","", "PolygonID")
            arcpy.AddField_management(statsTbl, "ACRES", "DOUBLE", "12", "1","", "Acres")
            arcpy.AddField_management(statsTbl, "VERTICES", "LONG", "12","","", "Vertex Count")
            arcpy.AddField_management(statsTbl, "AVI", "DOUBLE", "12", "1", "", "Avg Segment (" + unitAbbrev + ")")
            arcpy.AddField_management(statsTbl, "MIN_DIST", "DOUBLE", "12", "3", "", "Min Segment (" + unitAbbrev + ")")
            arcpy.AddField_management(statsTbl, "MULTIPART", "SHORT", "", "", "", "Is Multipart")

            try:
                if arcpy.ListFields(statsTbl, "Field1")[0] == "Field1":
                    AddMsgAndPrint("Deleting extra FIELD1 field", 0)
                    arcpy.DeleteField_management(statsTbl, "Field1")

            except:
                pass

        except:
            errorMsg()
            return ""

        return statsTbl

    except:
        errorMsg()
        return ""

## ===================================================================================
def RemoveJoins(inputLayer, theWildcard):
    ## Remove any joined tables matching wildcard string
    # inputLayer could also be a standalone table

    try:
        theJoinList = []
        desc = arcpy.Describe(inputLayer)

        if desc.DataType.upper() == "FEATURELAYER":
            theFC = desc.Featureclass.Name.replace(".shp","")
            #AddMsgAndPrint("\nFeatureclass name for input = " + theFC + "\n", 0)

        else:
            #AddMsgAndPrint("Error." + inputLayer + " is not a featurelayer", 2)
            return True

        fieldList = desc.fields

        for theField in fieldList:
            fullName = theField.name
            nameList = arcpy.ParseFieldName(fullName).split(",")
            #AddMsgAndPrint("    Fully qualified field name: " + fullName, 0)
            fieldName = nameList[3]
            tableName = fullName[0:-(len(fieldName))]

            if tableName != theFC and not tableName in theJoinList:
                # Found join, but only remove it if it matches wildcard
                if theWildcard == "" and tableName != " ":
                    theJoinList.append(tableName)
                    AddMsgAndPrint(" \nRemoving join: " + tableName, 0)
                    arcpy.RemoveJoin_management(inLayer, tableName)

                elif tableName.startswith(theWildcard):
                    theJoinList.append(tableName)
                    AddMsgAndPrint(" \nRemoving join: " + tableName, 0)
                    arcpy.RemoveJoin_management(inLayer, tableName)

        return True

    except:
        errorMsg()
        return False

## ===================================================================================
def Number_Format(num, places=0, bCommas=True):
    try:
    # Format a number according to locality and given places
        #locale.setlocale(locale.LC_ALL, "")
        if bCommas:
            theNumber = locale.format("%.*f", (places, num), True)

        else:
            theNumber = locale.format("%.*f", (places, num), False)
        return theNumber

    except:
        errorMsg()
        return num

## ===================================================================================
## MAIN
import sys, string, os, locale, math, operator, traceback, arcpy
from arcpy import env

if __name__ == '__main__':

    try:
        # Set formatting for numbers
        locale.setlocale(locale.LC_ALL, "")

        # Target Featureclass
        inLayer = arcpy.GetParameterAsText(0)

        # Line segment length below which vertices are flagged
        minDist = arcpy.GetParameter(1)

        # Projection (optional when input layer has projected coordinate system)
        outputSR = arcpy.GetParameter(2)

        # Output featurelayer containing flagged vertices (too close to neighbor)
        outLayer = arcpy.GetParameterAsText(3)

        # Check out ArcInfo license for PolygonToLine
        arcpy.SetProduct("ArcInfo")
        arcpy.env.parallelProcessingFactor = "75%"
        arcpy.env.overwriteOutput = True

        # An initial description of the input is required
        # Describe input layer
        desc = arcpy.da.Describe(inLayer)
        theDataType = desc['dataType'].upper()

        # input layer needs to be a featurelayer. If it is a featureclass, do a switch.
        if theDataType in ("FEATURECLASS", "SHAPEFILE"):
            # swap out the input featureclass for a new featurelayer based upon that featureclass
            inLayer = desc['name'] + " Layer"
            AddMsgAndPrint(" \nCreating new featurelayer named: " + inLayer)
            arcpy.MakeFeatureLayer_management(desc['catalogPath'], inLayer)

        # First clean up any joins from previous runs
        else:
            if not RemoveJoins(inLayer, "QA_VertexStats"):
                AddMsgAndPrint("Failed to remove previous table join",2)
                exit()

        # Setup: Get all required information from input layer
        # Describe input layer
        desc = arcpy.da.Describe(inLayer)
        theDataType = desc['dataType'].upper()
        theCatalogPath = desc['catalogPath']
        fidFld = desc['OIDFieldName']
        inputSR = desc['spatialReference']
        inputDatum = inputSR.GCS.datumName

        # Set output workspace
        if arcpy.Describe(os.path.dirname(theCatalogPath)).dataType.upper() == "FEATUREDATASET":
            # if input layer is in a featuredataset, move up one level to the geodatabase
            env.workspace = os.path.dirname(os.path.dirname(theCatalogPath))

        else:
            env.workspace = os.path.dirname(theCatalogPath)

        AddMsgAndPrint(" \nOutput workspace set to: " + env.workspace)

        # Get total number of features for the input featureclass
        iTotalFeatures = int(arcpy.GetCount_management(theCatalogPath).getOutput(0))

        # Get input layer information and count the number of input features
        if theDataType == "FEATURELAYER":
            # input layer is a FEATURELAYER, get featurelayer specific information
            defQuery = desc['whereClause']
            fids = desc['FIDSet']
            layerName = desc['nameString']

            # get count of number of features being processed
            if fids == None:
                # No selected features in layer
                iSelection = iTotalFeatures

                if defQuery == "":
                    # No query definition and no selection
                    iSelection = iTotalFeatures
                    AddMsgAndPrint(" \nProcessing all " + Number_Format(iTotalFeatures, 0, True) + " polygons in '" + layerName + "'...")

                else:
                    # There is a query definition, so the only option is to use GetCount
                    iSelection = int(arcpy.GetCount_management(inLayer).getOutput(0))  # Use selected features code
                    AddMsgAndPrint(" \nProcessing " + Number_Format(iSelection, 0, True) + " of " + Number_Format(iTotalFeatures, 0, True) + " features...")

            else:
                # featurelayer has a selected set, get count using FIDSet
                iSelection = len(fids.split(";"))
                AddMsgAndPrint(" \nProcessing " + Number_Format(iSelection, 0, True) + " of " + Number_Format(iTotalFeatures, 0, True) + " features...")

        elif theDataType == "FEATURECLASS":
            # input layer is a featureclass, get featureclass specific information
            layerName = desc['baseName']
            defQuery = ""
            fids = ""
            iSelection = iTotalFeatures
            AddMsgAndPrint(" \nProcessing all " + Number_Format(iTotalFeatures, 0, True) + " polygons in '" + layerName + "'...")

        # Make sure that input and output datums are the same, no transformations allowed
        if outputSR.name == '':
            outputSR = inputSR
            outputDatum = inputDatum
            #AddMsgAndPrint(" \nSetting output CS to same as input: " + outputSR.name + " \n" + outputDatum + " \n ")

        else:
            outputDatum = outputSR.GCS.datumName
            #AddMsgAndPrint(" \nOutput datum: '" + outputDatum + "'", 0)

        if inputDatum != outputDatum:
            AddMsgAndPrint("Input and output datums do not match",2)
            exit()

        if outputSR.type.upper() != "PROJECTED":
            if inputDatum in ("D_North_American_1983","D_WGS_1984"):
                # use Web Mercatur as output projection for calculating segment length
                AddMsgAndPrint(" \nInput layer coordinate system is not projected, switching to Web Mercatur (meters)", 1)
                outputSR = CreateWebMercaturSR()

            else:
                AddMsgAndPrint("Unable to handle input coordinate system: " + inputSR.name + " \n" + inputDatum,2)

        else:
            AddMsgAndPrint("\nUsing  output coordinate system: " + outputSR.name)

        theUnits = outputSR.linearUnitName.lower()
        theUnits = theUnits.replace("foot", "feet")
        theUnits = theUnits.replace("meter", "meters")

        if theUnits.startswith("meter"):
            unitAbbrev = "m"
        else:
            unitAbbrev = "ft"

        # run process
        bProcessed = ProcessLayer(inLayer, outputSR, outLayer, minDist, iSelection)

    except:
        errorMsg()

